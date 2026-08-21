"""Canal WebSocket autenticado e parser estrito de eventos administrativos."""

from app.realtime.protocol import (
    MAX_REALTIME_MESSAGE_BYTES,
    InvalidRealtimeEventError,
    parse_realtime_event,
)
from app.realtime.url import InvalidWebSocketUrlError, derive_admin_websocket_url
from app.realtime.websocket_client import AdminWebSocketClient

__all__ = [
    "AdminWebSocketClient",
    "InvalidRealtimeEventError",
    "InvalidWebSocketUrlError",
    "MAX_REALTIME_MESSAGE_BYTES",
    "derive_admin_websocket_url",
    "parse_realtime_event",
]
