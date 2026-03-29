from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiohttp import web

from .config import ChannelConfig, NvrConfig
from .server.soap_handler import SoapHandler
from .events.pullpoint import PullPointManager
from .rtsp_proxy import start_rtsp_proxy

if TYPE_CHECKING:
    from .discovery.ws_discovery import WsDiscovery

log = logging.getLogger(__name__)

RTSP_PROXY_PORT = 554


class VirtualDevice:
    def __init__(
        self,
        channel: ChannelConfig,
        nvr: NvrConfig,
        onvif_port: int,
    ):
        self.channel = channel
        self.nvr = nvr
        self.onvif_port = onvif_port
        self.pullpoint_manager = PullPointManager()
        self.soap_handler = SoapHandler(self)
        self._runner: web.AppRunner | None = None
        self._discovery: WsDiscovery | None = None
        self._rtsp_server: asyncio.Server | None = None

    @property
    def ip(self) -> str:
        return self.channel.ip

    @property
    def device_uuid(self) -> str:
        return self.channel.device_uuid

    @property
    def name(self) -> str:
        return self.channel.name

    @property
    def channel_num(self) -> int:
        return self.channel.channel

    @property
    def serial_number(self) -> str:
        return f"ONVIFSPLIT{self.channel_num:04d}"

    def service_url(self, path: str) -> str:
        return f"http://{self.ip}:{self.onvif_port}{path}"

    def rtsp_url(self, subtype: int = 0) -> str:
        # Point to this virtual device's own RTSP proxy
        return (
            f"rtsp://{self.ip}:{RTSP_PROXY_PORT}"
            f"/cam/realmonitor?channel={self.channel_num}&amp;subtype={subtype}"
            f"&amp;unicast=true&amp;proto=Onvif"
        )

    async def start(self):
        app = web.Application()
        app.router.add_post("/onvif/device_service", self.soap_handler.handle)
        app.router.add_post("/onvif/media_service", self.soap_handler.handle)
        app.router.add_post("/onvif/event_service", self.soap_handler.handle)
        app.router.add_post(
            "/onvif/subscription/{subscription_id}", self.soap_handler.handle
        )
        app.router.add_get("/onvif/snapshot", self.soap_handler.handle_snapshot)
        app.router.add_post("/internal/event", self._handle_event_push)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.ip, self.onvif_port)
        await site.start()
        log.info(
            "Virtual device %s (ch%d) listening on %s:%d",
            self.name,
            self.channel_num,
            self.ip,
            self.onvif_port,
        )

        # Start RTSP TCP proxy
        self._rtsp_server = await start_rtsp_proxy(
            self.ip,
            RTSP_PROXY_PORT,
            self.nvr.host,
            self.nvr.rtsp_port,
        )

    async def start_discovery(self):
        from .discovery.ws_discovery import WsDiscovery

        self._discovery = WsDiscovery(self)
        await self._discovery.start()

    async def stop(self):
        if self._discovery:
            await self._discovery.stop()
        if self._rtsp_server:
            self._rtsp_server.close()
            await self._rtsp_server.wait_closed()
        self.pullpoint_manager.shutdown()
        if self._runner:
            await self._runner.cleanup()
        log.info("Virtual device %s stopped", self.name)

    async def _handle_event_push(self, request: web.Request) -> web.Response:
        """Internal endpoint for coordinator to push events."""
        event_xml = await request.text()
        self.pullpoint_manager.push_event(event_xml)
        return web.Response(text="ok")

    def push_event(self, event_xml: str):
        self.pullpoint_manager.push_event(event_xml)
