"""Coordinator mode: subscribes to NVR events and pushes to camera containers."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import aiohttp

from .config import AppConfig, NvrConfig
from .events.nvr_subscriber import NvrEventSubscriber, _make_motion_event_xml

log = logging.getLogger(__name__)


class EventForwarder:
    """Receives events from NVR subscriber and forwards to camera containers via HTTP."""

    def __init__(self, channel_urls: dict[int, str]):
        # channel_num -> "http://ip:port"
        self.channel_urls = channel_urls
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )

    async def stop(self):
        if self._session:
            await self._session.close()

    def push_event(self, event_xml: str):
        """Called by NvrEventSubscriber — non-async, fires and forgets."""
        if self._session:
            asyncio.create_task(self._forward_all(event_xml))

    async def _forward_all(self, event_xml: str):
        """Forward event to all camera containers (they'll ignore if not relevant)."""
        tasks = []
        for channel, url in self.channel_urls.items():
            tasks.append(self._forward(channel, url, event_xml))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _forward(self, channel: int, url: str, event_xml: str):
        try:
            async with self._session.post(
                f"{url}/internal/event", data=event_xml
            ) as resp:
                if resp.status != 200:
                    log.warning("Event push to ch%d failed: %d", channel, resp.status)
        except Exception:
            log.debug("Event push to ch%d failed", channel, exc_info=True)


class CoordinatorDevice:
    """Fake device that the NvrEventSubscriber can push events to.
    Forwards to the real camera container via HTTP."""

    def __init__(self, channel: int, forwarder: EventForwarder):
        self.channel = channel
        self._forwarder = forwarder

    def push_event(self, event_xml: str):
        self._forwarder.push_event(event_xml)


async def run_coordinator():
    cfg = AppConfig.from_env()
    log.info(
        "Coordinator mode: NVR %s, forwarding to %d channels",
        cfg.nvr.host,
        len(cfg.channels),
    )

    # Build channel -> URL map from CHANNELS config
    channel_urls = {}
    for ch in cfg.channels:
        channel_urls[ch.channel] = f"http://{ch.ip}:{cfg.onvif_port}"

    forwarder = EventForwarder(channel_urls)
    await forwarder.start()

    # Build channel_map with CoordinatorDevices
    channel_map = {
        ch.channel: CoordinatorDevice(ch.channel, forwarder)
        for ch in cfg.channels
    }

    subscriber = NvrEventSubscriber(cfg.nvr, channel_map)
    subscriber_task = asyncio.create_task(subscriber.run())

    # Wait for shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    log.info("Coordinator shutting down...")
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    await forwarder.stop()
    log.info("Coordinator stopped")
