from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit


class InvalidWebSocketUrlError(ValueError):
    """A URL configurada não pode originar um canal WebSocket seguro."""


def derive_admin_websocket_url(api_url: str) -> str:
    """Deriva `/ws/admin/alerts` sem transportar credenciais na URL."""

    parsed = urlsplit(api_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidWebSocketUrlError("API_URL deve usar HTTP ou HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidWebSocketUrlError("API_URL não pode conter credenciais.")
    if parsed.query or parsed.fragment:
        raise InvalidWebSocketUrlError("API_URL não pode conter query ou fragmento.")

    websocket_scheme = "wss" if parsed.scheme == "https" else "ws"
    if websocket_scheme == "ws" and not _is_loopback(parsed.hostname):
        raise InvalidWebSocketUrlError(
            "WebSocket sem TLS é permitido somente em loopback."
        )

    base_path = parsed.path.rstrip("/")
    endpoint_path = f"{base_path}/ws/admin/alerts"
    return urlunsplit((websocket_scheme, parsed.netloc, endpoint_path, "", ""))


def _is_loopback(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
