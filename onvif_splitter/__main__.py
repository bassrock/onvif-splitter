from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from .config import AppConfig
from .virtual_device import VirtualDevice
from .events.nvr_subscriber import NvrEventSubscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("onvif_splitter")


async def main():
    # Try env vars first (for docker-compose inline config), fall back to YAML file
    if os.environ.get("NVR_HOST"):
        cfg = AppConfig.from_env()
        log.info("Loaded config from environment variables: NVR %s, %d channels", cfg.nvr.host, len(cfg.channels))
    else:
        config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
        if not config_path.exists():
            log.error("Config file not found: %s", config_path)
            sys.exit(1)
        cfg = AppConfig.from_yaml(config_path)
        log.info("Loaded config from %s: NVR %s, %d channels", config_path, cfg.nvr.host, len(cfg.channels))

    devices: list[VirtualDevice] = []
    for ch in cfg.channels:
        dev = VirtualDevice(ch, cfg.nvr, ch.port or cfg.onvif_port)
        devices.append(dev)

    # Start all virtual devices
    for dev in devices:
        await dev.start()

    # Start WS-Discovery for each device
    for dev in devices:
        try:
            await dev.start_discovery()
        except Exception:
            log.warning(
                "WS-Discovery failed for %s - device still works without it",
                dev.name,
                exc_info=True,
            )

    # Start NVR event subscriber
    channel_map = {ch.channel: dev for ch, dev in zip(cfg.channels, devices)}
    subscriber = NvrEventSubscriber(cfg.nvr, channel_map)
    subscriber_task = asyncio.create_task(subscriber.run())

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # Cleanup
    log.info("Shutting down...")
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass

    for dev in reversed(devices):
        await dev.stop()

    log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
