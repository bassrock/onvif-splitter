from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from aiohttp import web
from lxml import etree

if TYPE_CHECKING:
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)


def _parse_duration_seconds(duration: str) -> float:
    """Parse ISO 8601 duration like PT60S, PT1M, PT10S."""
    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", duration or ""
    )
    if not match:
        return 60
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


class EventsService:
    def __init__(self, device: VirtualDevice):
        self.device = device

    async def get_event_properties(self, elem: etree._Element, request: web.Request) -> bytes:
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
  xmlns:wstop="http://docs.oasis-open.org/wsn/t-1"
  xmlns:tns1="http://www.onvif.org/ver10/topics"
  xmlns:tt="http://www.onvif.org/ver10/schema"
  xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <s:Body>
    <tev:GetEventPropertiesResponse>
      <tev:TopicNamespaceLocation>http://www.onvif.org/onvif/ver10/topics/topicns.xml</tev:TopicNamespaceLocation>
      <wsnt:FixedTopicSet>true</wsnt:FixedTopicSet>
      <wstop:TopicSet>
        <tns1:RuleEngine>
          <CellMotionDetector>
            <Motion wstop:topic="true">
              <tt:MessageDescription IsProperty="true">
                <tt:Source>
                  <tt:SimpleItemDescription Name="VideoSourceConfigurationToken" Type="tt:ReferenceToken"/>
                  <tt:SimpleItemDescription Name="VideoAnalyticsConfigurationToken" Type="tt:ReferenceToken"/>
                  <tt:SimpleItemDescription Name="Rule" Type="xs:string"/>
                </tt:Source>
                <tt:Data>
                  <tt:SimpleItemDescription Name="IsMotion" Type="xs:boolean"/>
                </tt:Data>
              </tt:MessageDescription>
            </Motion>
          </CellMotionDetector>
        </tns1:RuleEngine>
      </wstop:TopicSet>
      <wsnt:TopicExpressionDialect>http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet</wsnt:TopicExpressionDialect>
      <tev:MessageContentFilterDialect>http://www.onvif.org/ver10/tev/messageContentFilter/ItemFilter</tev:MessageContentFilterDialect>
      <tev:MessageContentSchemaLocation>http://www.onvif.org/onvif/ver10/schema/onvif.xsd</tev:MessageContentSchemaLocation>
    </tev:GetEventPropertiesResponse>
  </s:Body>
</s:Envelope>"""

    async def get_service_capabilities(self, elem: etree._Element, request: web.Request) -> bytes:
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
  <s:Body>
    <tev:GetServiceCapabilitiesResponse>
      <tev:Capabilities
        WSSubscriptionPolicySupport="false"
        WSPullPointSupport="true"
        WSPausableSubscriptionManagerInterfaceSupport="false"
        MaxNotificationProducers="10"
        MaxPullPoints="10"/>
    </tev:GetServiceCapabilitiesResponse>
  </s:Body>
</s:Envelope>"""

    async def create_pullpoint_subscription(
        self, elem: etree._Element, request: web.Request
    ) -> bytes:
        # Parse requested TTL
        ttl_elem = elem.find(
            "{http://www.onvif.org/ver10/events/wsdl}InitialTerminationTime"
        )
        ttl = 60.0
        if ttl_elem is not None and ttl_elem.text:
            ttl = _parse_duration_seconds(ttl_elem.text)

        sub = self.device.pullpoint_manager.create_subscription(ttl)
        d = self.device

        now = datetime.now(timezone.utc)
        term_time = now + timedelta(seconds=sub.ttl)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        term_str = term_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        sub_url = d.service_url(f"/onvif/subscription/{sub.id}")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
  xmlns:wsa5="http://www.w3.org/2005/08/addressing">
  <s:Body>
    <tev:CreatePullPointSubscriptionResponse>
      <tev:SubscriptionReference>
        <wsa5:Address>{sub_url}</wsa5:Address>
      </tev:SubscriptionReference>
      <wsnt:CurrentTime>{now_str}</wsnt:CurrentTime>
      <wsnt:TerminationTime>{term_str}</wsnt:TerminationTime>
    </tev:CreatePullPointSubscriptionResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def pull_messages(
        self,
        elem: etree._Element,
        request: web.Request,
        subscription_id: str,
    ) -> bytes:
        # Parse timeout and message limit
        timeout_elem = elem.find("{http://www.onvif.org/ver10/events/wsdl}Timeout")
        limit_elem = elem.find("{http://www.onvif.org/ver10/events/wsdl}MessageLimit")

        timeout = 10.0
        if timeout_elem is not None and timeout_elem.text:
            timeout = _parse_duration_seconds(timeout_elem.text)
        max_messages = 100
        if limit_elem is not None and limit_elem.text:
            try:
                max_messages = int(limit_elem.text)
            except ValueError:
                pass

        messages = await self.device.pullpoint_manager.pull_messages(
            subscription_id, timeout, max_messages
        )

        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        term_str = (now + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

        messages_xml = "\n".join(messages)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <s:Body>
    <tev:PullMessagesResponse>
      <tev:CurrentTime>{now_str}</tev:CurrentTime>
      <tev:TerminationTime>{term_str}</tev:TerminationTime>
      {messages_xml}
    </tev:PullMessagesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def renew(
        self,
        elem: etree._Element,
        request: web.Request,
        subscription_id: str,
    ) -> bytes:
        ttl_elem = elem.find("{http://docs.oasis-open.org/wsn/b-2}TerminationTime")
        ttl = 60.0
        if ttl_elem is not None and ttl_elem.text:
            ttl = _parse_duration_seconds(ttl_elem.text)

        sub = self.device.pullpoint_manager.get_subscription(subscription_id)
        if sub:
            sub.renew(ttl)

        now = datetime.now(timezone.utc)
        term_str = (now + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <s:Body>
    <wsnt:RenewResponse>
      <wsnt:TerminationTime>{term_str}</wsnt:TerminationTime>
      <wsnt:CurrentTime>{now_str}</wsnt:CurrentTime>
    </wsnt:RenewResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def unsubscribe(
        self,
        elem: etree._Element,
        request: web.Request,
        subscription_id: str,
    ) -> bytes:
        self.device.pullpoint_manager.remove_subscription(subscription_id)
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <s:Body>
    <wsnt:UnsubscribeResponse/>
  </s:Body>
</s:Envelope>"""

    async def subscribe(self, elem: etree._Element, request: web.Request) -> bytes:
        # Basic WSN Subscribe - redirect to PullPoint
        return await self.create_pullpoint_subscription(elem, request)
