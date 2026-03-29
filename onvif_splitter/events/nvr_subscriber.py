from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
from lxml import etree

if TYPE_CHECKING:
    from ..config import NvrConfig
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)

# Map NVR VideoSourceConfigurationToken to channel number
# Token format: "00000" = ch1, "00100" = ch2, "00200" = ch3, etc.
TOKEN_TO_CHANNEL = {f"{i * 256:05x}": i + 1 for i in range(16)}
# Also support decimal format: "00000" = ch1, "00100" = ch2
for i in range(16):
    TOKEN_TO_CHANNEL[f"{i:02d}00{i:01d}"] = i + 1
    TOKEN_TO_CHANNEL[f"{i * 100:05d}"] = i + 1


def _make_ws_security(username: str, password: str) -> str:
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + password.encode()).digest()
    ).decode()
    nonce_b64 = base64.b64encode(nonce).decode()
    return f"""<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
      xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>"""


def _make_motion_event_xml(channel: int, is_motion: bool) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
      xmlns:tns1="http://www.onvif.org/ver10/topics"
      xmlns:tt="http://www.onvif.org/ver10/schema">
      <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/CellMotionDetector/Motion</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="{now}" PropertyOperation="Changed">
          <tt:Source>
            <tt:SimpleItem Name="VideoSourceConfigurationToken" Value="VideoSourceConfig_{channel}"/>
            <tt:SimpleItem Name="VideoAnalyticsConfigurationToken" Value="VideoAnalyticsConfig_{channel}"/>
            <tt:SimpleItem Name="Rule" Value="MyMotionDetectorRule"/>
          </tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="IsMotion" Value="{'true' if is_motion else 'false'}"/>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>"""


class NvrEventSubscriber:
    """Subscribes to NVR events via ONVIF PullPoint and demuxes to virtual devices."""

    def __init__(
        self,
        nvr: NvrConfig,
        channel_map: dict[int, VirtualDevice],
    ):
        self.nvr = nvr
        self.channel_map = channel_map
        self._pullpoint_url: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def run(self):
        backoff = 5
        while True:
            try:
                await self._subscribe_and_poll()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("NVR event subscriber error, retrying in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                backoff = 5

    async def _subscribe_and_poll(self):
        self._session = aiohttp.ClientSession()
        try:
            # Create PullPoint subscription
            self._pullpoint_url = await self._create_subscription()
            if not self._pullpoint_url:
                log.warning("Failed to create PullPoint subscription, falling back to Dahua HTTP events")
                try:
                    await self._poll_dahua_events()
                except Exception:
                    log.warning("Dahua HTTP event fallback also failed, will retry after backoff")
                    raise
                return

            log.info("NVR PullPoint subscription created: %s", self._pullpoint_url)

            # Poll loop
            renew_interval = 50  # renew every 50s (subscription is 60s)
            last_renew = asyncio.get_event_loop().time()

            while True:
                # Pull messages
                messages = await self._pull_messages()
                for channel, is_motion in messages:
                    if channel in self.channel_map:
                        event_xml = _make_motion_event_xml(channel, is_motion)
                        self.channel_map[channel].push_event(event_xml)
                        log.info(
                            "Motion %s on channel %d",
                            "started" if is_motion else "stopped",
                            channel,
                        )

                # Renew if needed
                now = asyncio.get_event_loop().time()
                if now - last_renew > renew_interval:
                    await self._renew_subscription()
                    last_renew = now

        finally:
            if self._session:
                await self._session.close()
                self._session = None

    async def _create_subscription(self) -> str | None:
        auth = _make_ws_security(self.nvr.username, self.nvr.password)
        soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <s:Header>{auth}</s:Header>
  <s:Body>
    <tev:CreatePullPointSubscription>
      <tev:InitialTerminationTime>PT60S</tev:InitialTerminationTime>
    </tev:CreatePullPointSubscription>
  </s:Body>
</s:Envelope>"""

        url = f"http://{self.nvr.host}:{self.nvr.port}/onvif/event_service"
        try:
            async with self._session.post(
                url,
                data=soap,
                headers={"Content-Type": "application/soap+xml"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                # Extract subscription reference address
                match = re.search(
                    r"<[^>]*SubscriptionReference[^>]*>.*?<[^>]*Address[^>]*>([^<]+)",
                    body,
                    re.DOTALL,
                )
                if match:
                    return match.group(1).strip()
                log.warning("No subscription reference in response: %s", body[:500])
                return None
        except Exception:
            log.exception("Failed to create PullPoint subscription")
            return None

    async def _pull_messages(self) -> list[tuple[int, bool]]:
        auth = _make_ws_security(self.nvr.username, self.nvr.password)
        soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
  <s:Header>{auth}</s:Header>
  <s:Body>
    <tev:PullMessages>
      <tev:Timeout>PT10S</tev:Timeout>
      <tev:MessageLimit>100</tev:MessageLimit>
    </tev:PullMessages>
  </s:Body>
</s:Envelope>"""

        results = []
        try:
            async with self._session.post(
                self._pullpoint_url,
                data=soap,
                headers={"Content-Type": "application/soap+xml"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                results = self._parse_events(body)
        except asyncio.TimeoutError:
            pass  # normal — no events during timeout
        except Exception:
            log.exception("PullMessages failed")
            raise

        return results

    def _parse_events(self, xml: str) -> list[tuple[int, bool]]:
        results = []
        try:
            doc = etree.fromstring(xml.encode())
            ns = {
                "tt": "http://www.onvif.org/ver10/schema",
                "wsnt": "http://docs.oasis-open.org/wsn/b-2",
            }
            for msg in doc.iter("{http://www.onvif.org/ver10/schema}Message"):
                source_items = msg.findall(".//tt:Source/tt:SimpleItem", ns)
                data_items = msg.findall(".//tt:Data/tt:SimpleItem", ns)

                channel = None
                is_motion = None

                for item in source_items:
                    name = item.get("Name", "")
                    value = item.get("Value", "")
                    if name == "VideoSourceConfigurationToken":
                        # Map token to channel
                        channel = TOKEN_TO_CHANNEL.get(value)
                        if channel is None:
                            # Try parsing as index * 256
                            try:
                                idx = int(value, 16) // 256
                                channel = idx + 1
                            except (ValueError, TypeError):
                                pass

                for item in data_items:
                    name = item.get("Name", "")
                    value = item.get("Value", "")
                    if name == "IsMotion":
                        is_motion = value.lower() == "true"

                if channel is not None and is_motion is not None:
                    results.append((channel, is_motion))

        except Exception:
            log.debug("Failed to parse events XML", exc_info=True)

        return results

    async def _renew_subscription(self):
        auth = _make_ws_security(self.nvr.username, self.nvr.password)
        soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <s:Header>{auth}</s:Header>
  <s:Body>
    <wsnt:Renew>
      <wsnt:TerminationTime>PT60S</wsnt:TerminationTime>
    </wsnt:Renew>
  </s:Body>
</s:Envelope>"""

        try:
            async with self._session.post(
                self._pullpoint_url,
                data=soap,
                headers={"Content-Type": "application/soap+xml"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    log.debug("Subscription renewed")
                else:
                    log.warning("Subscription renewal failed: %d", resp.status)
                    raise Exception("Renewal failed")
        except Exception:
            log.exception("Subscription renewal error")
            raise

    async def _poll_dahua_events(self):
        """Fallback: poll Dahua HTTP event API if ONVIF PullPoint fails."""
        uri_path = "/cgi-bin/eventManager.cgi?action=attach&codes=[VideoMotion]&heartbeat=5"
        url = f"http://{self.nvr.host}:{self.nvr.port}{uri_path}"
        log.info("Using Dahua HTTP event API fallback")

        # Dahua requires HTTP Digest auth — first request gets the challenge
        async with self._session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as challenge_resp:
            if challenge_resp.status != 401:
                # Maybe basic auth works
                pass
            else:
                www_auth = challenge_resp.headers.get("WWW-Authenticate", "")
                if "Digest" not in www_auth:
                    raise Exception("Dahua event API: expected Digest auth challenge")
                # Compute digest auth
                params = dict(re.findall(r'(\w+)="([^"]*)"', www_auth))
                realm = params.get("realm", "")
                nonce = params.get("nonce", "")
                qop = params.get("qop", "")
                ha1 = hashlib.md5(f"{self.nvr.username}:{realm}:{self.nvr.password}".encode()).hexdigest()
                ha2 = hashlib.md5(f"GET:{uri_path}".encode()).hexdigest()
                if "auth" in qop:
                    nc = "00000001"
                    cnonce = os.urandom(8).hex()
                    response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}".encode()).hexdigest()
                    auth_header = (
                        f'Digest username="{self.nvr.username}", realm="{realm}", nonce="{nonce}", '
                        f'uri="{uri_path}", qop=auth, nc={nc}, cnonce="{cnonce}", response="{response}"'
                    )
                else:
                    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
                    auth_header = (
                        f'Digest username="{self.nvr.username}", realm="{realm}", '
                        f'nonce="{nonce}", uri="{uri_path}", response="{response}"'
                    )

        async with self._session.get(
            url,
            headers={"Authorization": auth_header},
            timeout=aiohttp.ClientTimeout(total=None, sock_read=30),
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Dahua event API returned {resp.status}")
            buffer = b""
            async for chunk in resp.content.iter_any():
                buffer += chunk
                # Parse multipart boundaries
                while b"\r\n\r\n" in buffer:
                    header_end = buffer.index(b"\r\n\r\n")
                    payload_start = header_end + 4

                    # Look for Content-Length
                    header = buffer[:header_end].decode("utf-8", errors="ignore")
                    cl_match = re.search(r"Content-Length:\s*(\d+)", header)
                    if not cl_match:
                        # Skip heartbeats and incomplete headers
                        buffer = buffer[payload_start:]
                        continue

                    content_length = int(cl_match.group(1))
                    if len(buffer) < payload_start + content_length:
                        break  # need more data

                    payload = buffer[payload_start : payload_start + content_length]
                    buffer = buffer[payload_start + content_length :]

                    text = payload.decode("utf-8", errors="ignore")
                    self._handle_dahua_event(text)

    def _handle_dahua_event(self, text: str):
        # Dahua event format: Code=VideoMotion;action=Start;index=0
        code_match = re.search(r"Code=(\w+)", text)
        action_match = re.search(r"action=(\w+)", text)
        index_match = re.search(r"index=(\d+)", text)

        if not (code_match and action_match and index_match):
            return

        code = code_match.group(1)
        action = action_match.group(1)
        channel = int(index_match.group(1)) + 1  # Dahua uses 0-based index

        if code == "VideoMotion":
            is_motion = action == "Start"
            if channel in self.channel_map:
                event_xml = _make_motion_event_xml(channel, is_motion)
                self.channel_map[channel].push_event(event_xml)
                log.info(
                    "Dahua motion %s on channel %d",
                    "started" if is_motion else "stopped",
                    channel,
                )
