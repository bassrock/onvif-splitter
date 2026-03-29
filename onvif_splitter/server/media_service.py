from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from lxml import etree

if TYPE_CHECKING:
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)

NS = {
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
}


class MediaService:
    def __init__(self, device: VirtualDevice):
        self.device = device

    def _profile_token(self, subtype: int = 0) -> str:
        if subtype == 0:
            return f"MainStream_{self.device.channel_num}"
        return f"SubStream_{self.device.channel_num}"

    def _video_source_token(self) -> str:
        return f"VideoSource_{self.device.channel_num}"

    def _video_source_config_token(self) -> str:
        return f"VideoSourceConfig_{self.device.channel_num}"

    def _profile_xml(self, subtype: int) -> str:
        token = self._profile_token(subtype)
        vsc_token = self._video_source_config_token()
        vs_token = self._video_source_token()
        if subtype == 0:
            name = "MainStream"
            width, height, fps, bitrate = 3840, 2160, 7, 4096
            enc_token = f"VideoEncoder_Main_{self.device.channel_num}"
        else:
            name = "SubStream"
            width, height, fps, bitrate = 640, 480, 15, 512
            enc_token = f"VideoEncoder_Sub_{self.device.channel_num}"

        return f"""<trt:Profiles token="{token}" fixed="true">
        <tt:Name>{name}</tt:Name>
        <tt:VideoSourceConfiguration token="{vsc_token}">
          <tt:Name>VideoSourceConfig</tt:Name>
          <tt:UseCount>2</tt:UseCount>
          <tt:SourceToken>{vs_token}</tt:SourceToken>
          <tt:Bounds x="0" y="0" width="1920" height="1080"/>
        </tt:VideoSourceConfiguration>
        <tt:VideoEncoderConfiguration token="{enc_token}">
          <tt:Name>{name}</tt:Name>
          <tt:UseCount>1</tt:UseCount>
          <tt:Encoding>H264</tt:Encoding>
          <tt:Resolution>
            <tt:Width>{width}</tt:Width>
            <tt:Height>{height}</tt:Height>
          </tt:Resolution>
          <tt:Quality>4</tt:Quality>
          <tt:RateControl>
            <tt:FrameRateLimit>{fps}</tt:FrameRateLimit>
            <tt:EncodingInterval>1</tt:EncodingInterval>
            <tt:BitrateLimit>{bitrate}</tt:BitrateLimit>
          </tt:RateControl>
          <tt:H264>
            <tt:GovLength>{fps}</tt:GovLength>
            <tt:H264Profile>Main</tt:H264Profile>
          </tt:H264>
          <tt:Multicast>
            <tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address>
            <tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart>
          </tt:Multicast>
          <tt:SessionTimeout>PT60S</tt:SessionTimeout>
        </tt:VideoEncoderConfiguration>
      </trt:Profiles>"""

    async def get_profiles(self, elem: etree._Element, request: web.Request) -> bytes:
        profiles = self._profile_xml(0) + self._profile_xml(1)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetProfilesResponse>
      {profiles}
    </trt:GetProfilesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_profile(self, elem: etree._Element, request: web.Request) -> bytes:
        token = elem.findtext("{http://www.onvif.org/ver10/media/wsdl}ProfileToken", "")
        subtype = 1 if "Sub" in token else 0
        profile = self._profile_xml(subtype)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetProfileResponse>
      {profile}
    </trt:GetProfileResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_stream_uri(self, elem: etree._Element, request: web.Request) -> bytes:
        token = elem.findtext("{http://www.onvif.org/ver10/media/wsdl}ProfileToken", "")
        subtype = 1 if "Sub" in token else 0
        uri = self.device.rtsp_url(subtype)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetStreamUriResponse>
      <trt:MediaUri>
        <tt:Uri>{uri}</tt:Uri>
        <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
        <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
        <tt:Timeout>PT60S</tt:Timeout>
      </trt:MediaUri>
    </trt:GetStreamUriResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_snapshot_uri(self, elem: etree._Element, request: web.Request) -> bytes:
        uri = self.device.service_url("/onvif/snapshot")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetSnapshotUriResponse>
      <trt:MediaUri>
        <tt:Uri>{uri}</tt:Uri>
        <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
        <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
        <tt:Timeout>PT60S</tt:Timeout>
      </trt:MediaUri>
    </trt:GetSnapshotUriResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_video_sources(self, elem: etree._Element, request: web.Request) -> bytes:
        token = self._video_source_token()
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetVideoSourcesResponse>
      <trt:VideoSources token="{token}">
        <tt:Framerate>30</tt:Framerate>
        <tt:Resolution>
          <tt:Width>3840</tt:Width>
          <tt:Height>2160</tt:Height>
        </tt:Resolution>
      </trt:VideoSources>
    </trt:GetVideoSourcesResponse>
  </s:Body>
</s:Envelope>""".encode()

    async def get_video_source_configurations(self, elem: etree._Element, request: web.Request) -> bytes:
        vsc_token = self._video_source_config_token()
        vs_token = self._video_source_token()
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <trt:GetVideoSourceConfigurationsResponse>
      <trt:Configurations token="{vsc_token}">
        <tt:Name>VideoSourceConfig</tt:Name>
        <tt:UseCount>2</tt:UseCount>
        <tt:SourceToken>{vs_token}</tt:SourceToken>
        <tt:Bounds x="0" y="0" width="1920" height="1080"/>
      </trt:Configurations>
    </trt:GetVideoSourceConfigurationsResponse>
  </s:Body>
</s:Envelope>""".encode()
