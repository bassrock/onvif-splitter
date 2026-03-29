from __future__ import annotations

import hashlib
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
