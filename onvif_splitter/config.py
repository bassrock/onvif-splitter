from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class NvrConfig:
    host: str
    port: int = 80
    rtsp_port: int = 554
    username: str = "admin"
    password: str = ""


@dataclass
class ChannelConfig:
    channel: int
    ip: str
    name: str = ""
    port: int = 0  # 0 = use global onvif_port
    device_uuid: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"Camera {self.channel}"
        if not self.device_uuid:
            # Deterministic UUID from channel number
            ns = uuid.UUID("12345678-1234-5678-1234-567812345678")
            self.device_uuid = str(uuid.uuid5(ns, f"onvif-splitter-ch{self.channel}"))


@dataclass
class AppConfig:
    nvr: NvrConfig
    channels: list[ChannelConfig] = field(default_factory=list)
    onvif_port: int = 8080

    @classmethod
    def from_yaml(cls, path: str | Path) -> AppConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)

        nvr = NvrConfig(**raw["nvr"])
        channels = [ChannelConfig(**ch) for ch in raw.get("channels", [])]
        return cls(
            nvr=nvr,
            channels=channels,
            onvif_port=raw.get("onvif_port", 8080),
        )

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load config entirely from environment variables.

        Required:
          NVR_HOST
          NVR_PASSWORD
          CHANNELS  - comma-separated, each entry is channel:ip or channel:ip:name
                      e.g. "1:192.168.2.121:Front Door,2:192.168.2.122:Backyard"

        Optional:
          NVR_PORT       (default 80)
          NVR_RTSP_PORT  (default 554)
          NVR_USERNAME   (default admin)
          ONVIF_PORT     (default 8080)
        """
        nvr = NvrConfig(
            host=os.environ["NVR_HOST"],
            port=int(os.environ.get("NVR_PORT", "80")),
            rtsp_port=int(os.environ.get("NVR_RTSP_PORT", "554")),
            username=os.environ.get("NVR_USERNAME", "admin"),
            password=os.environ["NVR_PASSWORD"],
        )

        channels = []
        for entry in os.environ.get("CHANNELS", "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":", 2)
            ch_num = int(parts[0])
            ip = parts[1]
            name = parts[2] if len(parts) > 2 else ""
            channels.append(ChannelConfig(channel=ch_num, ip=ip, name=name))

        return cls(
            nvr=nvr,
            channels=channels,
            onvif_port=int(os.environ.get("ONVIF_PORT", "8080")),
        )
