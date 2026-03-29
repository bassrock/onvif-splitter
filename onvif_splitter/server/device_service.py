from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiohttp import web
from lxml import etree

if TYPE_CHECKING:
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, device: VirtualDevice):
        self.device = device

    async def get_system_date_time(self, elem: etree._Element, request: web.Request) -> bytes:
        now = datetime.now(timezone.utc)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetSystemDateAndTimeResponse>
      <tds:SystemDateAndTime>
        <tt:DateTimeType>NTP</tt:DateTimeType>
        <tt:DaylightSavings>false</tt:DaylightSavings>
        <tt:TimeZone>
          <tt:TZ>UTC0</tt:TZ>
        </tt:TimeZone>
        <tt:UTCDateTime>
          <tt:Time>
            <tt:Hour>{now.hour}</tt:Hour>
            <tt:Minute>{now.minute}</tt:Minute>
            <tt:Second>{now.second}</tt:Second>
          </tt:Time>
          <tt:Date>
            <tt:Year>{now.year}</tt:Year>
            <tt:Month>{now.month}</tt:Month>
            <tt:Day>{now.day}</tt:Day>
          </tt:Date>
        </tt:UTCDateTime>
      </tds:SystemDateAndTime>
    </tds:GetSystemDateAndTimeResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_device_information(self, elem: etree._Element, request: web.Request) -> bytes:
        d = self.device
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <s:Body>
    <tds:GetDeviceInformationResponse>
      <tds:Manufacturer>ONVIF-Splitter</tds:Manufacturer>
      <tds:Model>Virtual Camera</tds:Model>
      <tds:FirmwareVersion>1.0.0</tds:FirmwareVersion>
      <tds:SerialNumber>{d.serial_number}</tds:SerialNumber>
      <tds:HardwareId>ONVIF-SPLIT-{d.channel_num}</tds:HardwareId>
    </tds:GetDeviceInformationResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_services(self, elem: etree._Element, request: web.Request) -> bytes:
        d = self.device
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetServicesResponse>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>
        <tds:XAddr>{d.service_url("/onvif/device_service")}</tds:XAddr>
        <tds:Version><tt:Major>2</tt:Major><tt:Minor>50</tt:Minor></tds:Version>
      </tds:Service>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>
        <tds:XAddr>{d.service_url("/onvif/media_service")}</tds:XAddr>
        <tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version>
      </tds:Service>
      <tds:Service>
        <tds:Namespace>http://www.onvif.org/ver10/events/wsdl</tds:Namespace>
        <tds:XAddr>{d.service_url("/onvif/event_service")}</tds:XAddr>
        <tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version>
      </tds:Service>
    </tds:GetServicesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_capabilities(self, elem: etree._Element, request: web.Request) -> bytes:
        d = self.device
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetCapabilitiesResponse>
      <tds:Capabilities>
        <tt:Device>
          <tt:XAddr>{d.service_url("/onvif/device_service")}</tt:XAddr>
          <tt:Network><tt:IPFilter>false</tt:IPFilter><tt:ZeroConfiguration>false</tt:ZeroConfiguration><tt:IPVersion6>false</tt:IPVersion6><tt:DynDNS>false</tt:DynDNS></tt:Network>
          <tt:System><tt:DiscoveryResolve>false</tt:DiscoveryResolve><tt:DiscoveryBye>true</tt:DiscoveryBye><tt:RemoteDiscovery>false</tt:RemoteDiscovery><tt:SystemBackup>false</tt:SystemBackup><tt:SystemLogging>false</tt:SystemLogging><tt:FirmwareUpgrade>false</tt:FirmwareUpgrade></tt:System>
          <tt:Security><tt:TLS1.1>false</tt:TLS1.1><tt:TLS1.2>false</tt:TLS1.2><tt:OnboardKeyGeneration>false</tt:OnboardKeyGeneration><tt:AccessPolicyConfig>false</tt:AccessPolicyConfig><tt:X.509Token>false</tt:X.509Token><tt:SAMLToken>false</tt:SAMLToken><tt:KerberosToken>false</tt:KerberosToken><tt:RELToken>false</tt:RELToken></tt:Security>
        </tt:Device>
        <tt:Media>
          <tt:XAddr>{d.service_url("/onvif/media_service")}</tt:XAddr>
          <tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP><tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities>
        </tt:Media>
        <tt:Events>
          <tt:XAddr>{d.service_url("/onvif/event_service")}</tt:XAddr>
          <tt:WSSubscriptionPolicySupport>false</tt:WSSubscriptionPolicySupport>
          <tt:WSPullPointSupport>true</tt:WSPullPointSupport>
        </tt:Events>
      </tds:Capabilities>
    </tds:GetCapabilitiesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_scopes(self, elem: etree._Element, request: web.Request) -> bytes:
        d = self.device
        name_encoded = d.name.replace(" ", "%20")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetScopesResponse>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/type/video_encoder</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/type/Network_Video_Transmitter</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Fixed</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/hardware/ONVIF-Splitter</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Configurable</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/name/{name_encoded}</tt:ScopeItem>
      </tds:Scopes>
      <tds:Scopes>
        <tt:ScopeDef>Configurable</tt:ScopeDef>
        <tt:ScopeItem>onvif://www.onvif.org/location/</tt:ScopeItem>
      </tds:Scopes>
    </tds:GetScopesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_network_interfaces(self, elem: etree._Element, request: web.Request) -> bytes:
        d = self.device
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tds:GetNetworkInterfacesResponse>
      <tds:NetworkInterfaces token="eth0">
        <tt:Enabled>true</tt:Enabled>
        <tt:Info>
          <tt:Name>eth0</tt:Name>
        </tt:Info>
        <tt:IPv4>
          <tt:Enabled>true</tt:Enabled>
          <tt:Config>
            <tt:Manual>
              <tt:Address>{d.ip}</tt:Address>
              <tt:PrefixLength>24</tt:PrefixLength>
            </tt:Manual>
            <tt:DHCP>false</tt:DHCP>
          </tt:Config>
        </tt:IPv4>
      </tds:NetworkInterfaces>
    </tds:GetNetworkInterfacesResponse>
  </s:Body>
</s:Envelope>""".encode()
