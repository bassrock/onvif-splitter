from __future__ import annotations

import base64
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from lxml import etree

from .device_service import DeviceService
from .media_service import MediaService
from .events_service import EventsService

if TYPE_CHECKING:
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)

NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tev": "http://www.onvif.org/ver10/events/wsdl",
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
}

# Actions that don't require authentication (ONVIF spec)
UNAUTHENTICATED_ACTIONS = {
    "{http://www.onvif.org/ver10/device/wsdl}GetSystemDateAndTime",
}

CLOCK_SKEW_SECONDS = 300  # 5 minutes


class SoapHandler:
    def __init__(self, device: VirtualDevice):
        self.device = device
        self.device_service = DeviceService(device)
        self.media_service = MediaService(device)
        self.events_service = EventsService(device)

    async def handle(self, request: web.Request) -> web.Response:
        try:
            body = await request.read()
            doc = etree.fromstring(body)
        except Exception:
            log.warning("Invalid SOAP XML from %s", request.remote)
            return self._fault_response("sender", "InvalidXML", "Could not parse SOAP envelope")

        # Extract action from SOAP body
        soap_body = doc.find("s:Body", NS)
        if soap_body is None or len(soap_body) == 0:
            return self._fault_response("sender", "EmptyBody", "SOAP body is empty")

        action_elem = soap_body[0]
        action = f"{{{action_elem.nsmap.get(action_elem.prefix, '')}}}{etree.QName(action_elem).localname}"
        action_local = etree.QName(action_elem).localname
        action_ns = etree.QName(action_elem).namespace

        log.debug("SOAP action: %s from %s", action_local, request.remote)

        # Check auth (skip for unauthenticated actions)
        full_action = f"{{{action_ns}}}{action_local}"
        if full_action not in UNAUTHENTICATED_ACTIONS:
            if not self._validate_auth(doc):
                log.warning("Auth failed for %s from %s", action_local, request.remote)
                return self._fault_response(
                    "sender",
                    "NotAuthorized",
                    "Authentication failed",
                    status=401,
                )

        # Check if this is a subscription endpoint request
        subscription_id = request.match_info.get("subscription_id")

        # Route to service handler
        handler = self._resolve_handler(action_ns, action_local, subscription_id)
        if handler is None:
            log.warning("Unknown action: %s::%s", action_ns, action_local)
            return self._fault_response(
                "sender", "ActionNotSupported", f"Action {action_local} not supported"
            )

        try:
            response_xml = await handler(action_elem, request)
            return web.Response(
                body=response_xml,
                content_type="application/soap+xml",
                charset="utf-8",
            )
        except Exception:
            log.exception("Error handling %s", action_local)
            return self._fault_response("receiver", "InternalError", "Internal server error")

    def _resolve_handler(self, ns: str, action: str, subscription_id: str | None):
        # Subscription endpoint actions
        if subscription_id:
            return {
                "PullMessages": lambda elem, req: self.events_service.pull_messages(elem, req, subscription_id),
                "Renew": lambda elem, req: self.events_service.renew(elem, req, subscription_id),
                "Unsubscribe": lambda elem, req: self.events_service.unsubscribe(elem, req, subscription_id),
            }.get(action)

        # Device service
        if ns == "http://www.onvif.org/ver10/device/wsdl":
            return {
                "GetSystemDateAndTime": self.device_service.get_system_date_time,
                "GetDeviceInformation": self.device_service.get_device_information,
                "GetServices": self.device_service.get_services,
                "GetCapabilities": self.device_service.get_capabilities,
                "GetScopes": self.device_service.get_scopes,
                "GetNetworkInterfaces": self.device_service.get_network_interfaces,
            }.get(action)

        # Media service
        if ns == "http://www.onvif.org/ver10/media/wsdl":
            return {
                "GetProfiles": self.media_service.get_profiles,
                "GetProfile": self.media_service.get_profile,
                "GetStreamUri": self.media_service.get_stream_uri,
                "GetSnapshotUri": self.media_service.get_snapshot_uri,
                "GetVideoSources": self.media_service.get_video_sources,
                "GetVideoSourceConfigurations": self.media_service.get_video_source_configurations,
            }.get(action)

        # Event service
        if ns == "http://www.onvif.org/ver10/events/wsdl":
            return {
                "GetEventProperties": self.events_service.get_event_properties,
                "CreatePullPointSubscription": self.events_service.create_pullpoint_subscription,
                "GetServiceCapabilities": self.events_service.get_service_capabilities,
            }.get(action)

        # WSN actions on event service
        if ns == "http://docs.oasis-open.org/wsn/b-2":
            return {
                "Subscribe": self.events_service.subscribe,
            }.get(action)

        return None

    def _validate_auth(self, doc: etree._Element) -> bool:
        header = doc.find("s:Header", NS)
        if header is None:
            return False

        security = header.find("wsse:Security", NS)
        if security is None:
            return False

        token = security.find("wsse:UsernameToken", NS)
        if token is None:
            return False

        username_elem = token.find("wsse:Username", NS)
        password_elem = token.find("wsse:Password", NS)
        nonce_elem = token.find("wsse:Nonce", NS)
        created_elem = token.find("wsu:Created", NS)

        if username_elem is None or password_elem is None:
            return False

        username = username_elem.text or ""
        if username != self.device.nvr.username:
            return False

        password_type = password_elem.get("Type", "")

        if "PasswordDigest" in password_type:
            # WS-Security PasswordDigest: Base64(SHA1(nonce + created + password))
            if nonce_elem is None or created_elem is None:
                return False

            nonce = base64.b64decode(nonce_elem.text or "")
            created = (created_elem.text or "").encode()
            expected_digest = base64.b64encode(
                hashlib.sha1(nonce + created + self.device.nvr.password.encode()).digest()
            ).decode()

            received = password_elem.text or ""
            if received != expected_digest:
                return False

            # Check clock skew
            try:
                created_time = datetime.fromisoformat(
                    created_elem.text.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                delta = abs((now - created_time).total_seconds())
                if delta > CLOCK_SKEW_SECONDS:
                    log.warning("Clock skew too large: %.0fs", delta)
                    return False
            except (ValueError, TypeError):
                pass

        elif "PasswordText" in password_type or not password_type:
            # Plain text password
            if (password_elem.text or "") != self.device.nvr.password:
                return False
        else:
            return False

        return True

    async def handle_snapshot(self, request: web.Request) -> web.Response:
        url = (
            f"http://{self.device.nvr.host}:{self.device.nvr.port}"
            f"/cgi-bin/snapshot.cgi?channel={self.device.channel_num}"
        )
        auth = aiohttp.BasicAuth(self.device.nvr.username, self.device.nvr.password)
        try:
            async with aiohttp.ClientSession(auth=auth) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        return web.Response(
                            body=data,
                            content_type=resp.content_type or "image/jpeg",
                        )
                    return web.Response(status=502, text="Snapshot failed")
        except Exception:
            log.exception("Snapshot proxy failed for ch%d", self.device.channel_num)
            return web.Response(status=502, text="Snapshot proxy error")

    def _fault_response(
        self, code: str, subcode: str, reason: str, status: int = 500
    ) -> web.Response:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <s:Fault>
      <s:Code>
        <s:Value>s:{code}</s:Value>
        <s:Subcode><s:Value>{subcode}</s:Value></s:Subcode>
      </s:Code>
      <s:Reason><s:Text xml:lang="en">{reason}</s:Text></s:Reason>
    </s:Fault>
  </s:Body>
</s:Envelope>"""
        return web.Response(
            body=xml,
            content_type="application/soap+xml",
            charset="utf-8",
            status=status,
        )
