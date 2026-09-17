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
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("credenciais devem ficar no .env local do Operator")
    return CameraSourceType.IP
