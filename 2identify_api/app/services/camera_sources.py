"""One validation and sanitization boundary for catalog camera locators."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit


class CameraSourceType(StrEnum):
    IP = "ip"
    USB = "usb"


def classify_camera_source(value: str) -> CameraSourceType:
    source = value.strip()
    if source.isdecimal():
        return CameraSourceType.USB
    parsed = urlsplit(source)
    if parsed.scheme.casefold() in {"rtsp", "http", "https"} and parsed.hostname:
        return CameraSourceType.IP
    raise ValueError("fonte de câmera deve ser índice USB ou URL RTSP/HTTP(S)")


def public_camera_source(value: str) -> str | None:
    """Return a locator only when it contains no embedded credentials."""

    source_type = classify_camera_source(value)
    if source_type is CameraSourceType.USB:
        # USB numbering belongs to the workstation, not the shared catalog.
        return None
    parsed = urlsplit(value.strip())
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return urlunsplit(parsed)


def sanitized_admin_source(value: str) -> str:
    """Preserve a useful locator without returning stored URL userinfo."""

    if classify_camera_source(value) is CameraSourceType.USB:
        return value.strip()
    parsed = urlsplit(value.strip())
    if (
        parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    ):
        return value.strip()
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
