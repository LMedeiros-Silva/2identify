"""Single Admin-side parser for camera registration sources."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit


class CameraSourceType(StrEnum):
    IP = "ip"
    USB = "usb"


def parse_camera_source(value: str) -> CameraSourceType:
    source = value.strip()
    if source.isdecimal():
        return CameraSourceType.USB
    parsed = urlsplit(source)
    if parsed.scheme.casefold() not in {"rtsp", "http", "https"} or not parsed.hostname:
        raise ValueError("informe índice USB ou URL RTSP/HTTP(S) válida")
    if parsed.fragment:
        raise ValueError("a URL da câmera não pode conter fragmento (#)")
    return CameraSourceType.IP


MASKED_PASSWORD = "***"


def has_masked_password(value: str) -> bool:
    """True when the API returned this locator with its password hidden."""

    return urlsplit(value.strip()).password == MASKED_PASSWORD
