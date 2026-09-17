"""Camera identity and workstation-local source resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from dotenv import dotenv_values

from app.core.constants import PROJECT_ROOT
from app.vision.types import Frame


class CameraType(StrEnum):
    IP = "ip"
    USB = "usb"


class CameraStatus(StrEnum):
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    RECONNECTING = "RECONNECTING"


@dataclass(frozen=True, slots=True)
class CameraSource:
    camera_id: int
    name: str
    sector_id: int
    source_type: CameraType
    source_hint: str | None = None

    def __post_init__(self) -> None:
        if self.camera_id <= 0 or self.sector_id <= 0 or not self.name.strip():
            raise ValueError("identidade da câmera inválida")
        if not isinstance(self.source_type, CameraType):
            raise ValueError("tipo de câmera inválido")

    def resolve(self, local_sources: dict[int, str] | None = None) -> int | str:
        """Prefer a station-local override; never log or display its value."""

        value = (local_sources or {}).get(self.camera_id)
        if value is None:
            value = local_camera_source(self.camera_id)
        if value is None:
            value = self.source_hint
        if value is None:
            raise ValueError(f"fonte local não configurada para câmera {self.camera_id}")
        return parse_source_value(self.source_type, value)


def parse_source_value(source_type: CameraType, value: str) -> int | str:
    """Convert a local locator into the OpenCV source expected for its type."""

    value = value.strip()
    if source_type is CameraType.USB:
        if not value.isdecimal():
            raise ValueError("fonte USB deve ser índice OpenCV local não negativo")
        return int(value)
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in {"rtsp", "http", "https"} or not parsed.hostname:
        raise ValueError("fonte IP deve ser URL RTSP, HTTP ou HTTPS válida")
    return value


def local_camera_source(camera_id: int) -> str | None:
    """Read a camera-specific source only from workstation-local configuration."""

    key = f"CAMERA_SOURCE_{camera_id}"
    return os.environ.get(key) or dotenv_values(PROJECT_ROOT / ".env").get(key)


@dataclass(frozen=True, slots=True)
class CameraFrame:
    camera_id: int
    generation: int
    captured_at: datetime
    frame: Frame

    def __post_init__(self) -> None:
        if self.camera_id <= 0 or self.generation < 0:
            raise ValueError("identidade do frame inválida")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at deve ter fuso horário")
        object.__setattr__(self, "captured_at", self.captured_at.astimezone(UTC))
