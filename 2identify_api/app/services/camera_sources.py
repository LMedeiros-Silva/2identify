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


MASKED_PASSWORD = "***"


class CameraPasswordRequiredError(ValueError):
    """The masked password placeholder cannot be matched to a stored one."""


def public_camera_source(value: str) -> str | None:
    """Return the full network locator, credentials included, for the Operator.

    The Admin registers the complete camera URL; the Operator needs it to open
    the stream without any workstation .env entry.
    """

    source_type = classify_camera_source(value)
    if source_type is CameraSourceType.USB:
        # USB numbering belongs to the workstation, not the shared catalog.
        return None
    return value.strip()


def sanitized_admin_source(value: str) -> str:
    """Return the stored locator with only its URL password masked."""

    if classify_camera_source(value) is CameraSourceType.USB:
        return value.strip()
    parsed = urlsplit(value.strip())
    if parsed.password is None:
        return value.strip()
    return urlunsplit(parsed._replace(netloc=_masked_netloc(parsed)))


def restore_masked_password(submitted: str, stored: str | None) -> str:
    """Keep the stored password when the Admin sends back the masked locator."""

    if classify_camera_source(submitted) is CameraSourceType.USB:
        return submitted
    new = urlsplit(submitted)
    if new.password != MASKED_PASSWORD:
        return submitted
    old = urlsplit((stored or "").strip())
    if old.password is None or old.username != new.username:
        raise CameraPasswordRequiredError("informe a senha da câmera na URL")
    userinfo = old.netloc.rpartition("@")[0]
    host = new.netloc.rpartition("@")[2]
    return urlunsplit(new._replace(netloc=f"{userinfo}@{host}"))


def _masked_netloc(parsed) -> str:  # noqa: ANN001 - urllib SplitResult
    userinfo, _, host = parsed.netloc.rpartition("@")
    user = userinfo.split(":", 1)[0]
    return f"{user}:{MASKED_PASSWORD}@{host}"
