from __future__ import annotations

import asyncio
import logging
import socket
import struct
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..virtual_device import VirtualDevice

log = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 3702

WSD_NS = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
WSA_NS = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
ONVIF_TYPES = "dn:NetworkVideoTransmitter"
ONVIF_DN_NS = "http://www.onvif.org/ver10/network/wsdl"


class WsDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, device: VirtualDevice):
        self.device = device
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        try:
            text = data.decode("utf-8", errors="ignore")
            if "Probe" in text and "ProbeMatch" not in text:
                self._handle_probe(text, addr)
        except Exception:
            log.debug("Error handling WS-Discovery packet", exc_info=True)

    def _handle_probe(self, text: str, addr: tuple[str, int]):
        # Extract MessageID for RelatesTo
        msg_id = ""
        if "<wsa:MessageID>" in text:
            start = text.index("<wsa:MessageID>") + len("<wsa:MessageID>")
            end = text.index("</wsa:MessageID>", start)
            msg_id = text[start:end].strip()
        elif "<a:MessageID>" in text:
            start = text.index("<a:MessageID>") + len("<a:MessageID>")
            end = text.index("</a:MessageID>", start)
            msg_id = text[start:end].strip()

        d = self.device
        response = self._probe_match_xml(msg_id)
        if self.transport:
            self.transport.sendto(response.encode(), addr)
            log.debug("Sent ProbeMatch for %s to %s", d.name, addr)

    def _probe_match_xml(self, relates_to: str) -> str:
        d = self.device
        msg_uuid = f"urn:uuid:{uuid.uuid4()}"
        device_uuid = f"urn:uuid:{d.device_uuid}"
        xaddr = d.service_url("/onvif/device_service")
        name_encoded = d.name.replace(" ", "%20")

        scopes = (
            "onvif://www.onvif.org/type/video_encoder "
            "onvif://www.onvif.org/type/Network_Video_Transmitter "
            "onvif://www.onvif.org/hardware/ONVIF-Splitter "
            f"onvif://www.onvif.org/name/{name_encoded}"
        )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="{ONVIF_DN_NS}">
  <s:Header>
    <wsa:MessageID>{msg_uuid}</wsa:MessageID>
    <wsa:RelatesTo>{relates_to}</wsa:RelatesTo>
    <wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
    <d:AppSequence InstanceId="1" MessageNumber="1"/>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <wsa:EndpointReference><wsa:Address>{device_uuid}</wsa:Address></wsa:EndpointReference>
        <d:Types>{ONVIF_TYPES}</d:Types>
        <d:Scopes>{scopes}</d:Scopes>
        <d:XAddrs>{xaddr}</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>"""

    def hello_xml(self) -> str:
        d = self.device
        msg_uuid = f"urn:uuid:{uuid.uuid4()}"
        device_uuid = f"urn:uuid:{d.device_uuid}"
        xaddr = d.service_url("/onvif/device_service")
        name_encoded = d.name.replace(" ", "%20")

        scopes = (
            "onvif://www.onvif.org/type/video_encoder "
            "onvif://www.onvif.org/type/Network_Video_Transmitter "
            "onvif://www.onvif.org/hardware/ONVIF-Splitter "
            f"onvif://www.onvif.org/name/{name_encoded}"
        )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="{ONVIF_DN_NS}">
  <s:Header>
    <wsa:MessageID>{msg_uuid}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Hello</wsa:Action>
    <d:AppSequence InstanceId="1" MessageNumber="1"/>
  </s:Header>
  <s:Body>
    <d:Hello>
      <wsa:EndpointReference><wsa:Address>{device_uuid}</wsa:Address></wsa:EndpointReference>
      <d:Types>{ONVIF_TYPES}</d:Types>
      <d:Scopes>{scopes}</d:Scopes>
      <d:XAddrs>{xaddr}</d:XAddrs>
      <d:MetadataVersion>1</d:MetadataVersion>
    </d:Hello>
  </s:Body>
</s:Envelope>"""

    def bye_xml(self) -> str:
        msg_uuid = f"urn:uuid:{uuid.uuid4()}"
        device_uuid = f"urn:uuid:{self.device.device_uuid}"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <s:Header>
    <wsa:MessageID>{msg_uuid}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Bye</wsa:Action>
    <d:AppSequence InstanceId="1" MessageNumber="1"/>
  </s:Header>
  <s:Body>
    <d:Bye>
      <wsa:EndpointReference><wsa:Address>{device_uuid}</wsa:Address></wsa:EndpointReference>
    </d:Bye>
  </s:Body>
</s:Envelope>"""


class WsDiscovery:
    def __init__(self, device: VirtualDevice):
        self.device = device
        self._protocol: WsDiscoveryProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self):
        loop = asyncio.get_running_loop()

        # Create UDP socket for multicast
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass

        sock.bind(("", MULTICAST_PORT))

        # Join multicast group on the device's IP
        group = socket.inet_aton(MULTICAST_GROUP)
        local = socket.inet_aton(self.device.ip)
        mreq = struct.pack("4s4s", group, local)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Set outgoing multicast interface
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, local)

        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: WsDiscoveryProtocol(self.device),
            sock=sock,
        )

        # Send Hello
        hello = self._protocol.hello_xml()
        self._transport.sendto(hello.encode(), (MULTICAST_GROUP, MULTICAST_PORT))
        log.info("WS-Discovery started for %s on %s", self.device.name, self.device.ip)

    async def stop(self):
        if self._protocol and self._transport:
            bye = self._protocol.bye_xml()
            self._transport.sendto(bye.encode(), (MULTICAST_GROUP, MULTICAST_PORT))
            self._transport.close()
            log.info("WS-Discovery stopped for %s", self.device.name)
