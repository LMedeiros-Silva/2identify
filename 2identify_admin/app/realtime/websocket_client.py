from __future__ import annotations

import logging
import re
from collections.abc import Callable

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from app.realtime.protocol import MAX_REALTIME_MESSAGE_BYTES

logger = logging.getLogger(__name__)
_UNAUTHORIZED_STATUS = re.compile(r"(?:^|\D)(?:401|403)(?:\D|$)")


class AdminWebSocketClient(QObject):
    """Adaptador Qt que abre um WebSocket sem persistir ou expor o bearer."""

    connected = Signal()
    disconnected = Signal()
    message_received = Signal(str)
    authorization_rejected = Signal()
    transport_failed = Signal()
    protocol_failed = Signal(str)

    def __init__(
        self,
        endpoint_url: str,
        token_provider: Callable[[], str | None],
        *,
        socket_factory: Callable[[], QWebSocket] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._endpoint_url = endpoint_url
        self._token_provider = token_provider
        self._enabled = False
        self._authorization_notified = False
        if socket_factory is None:
            self._socket = QWebSocket()
            self._socket.setParent(self)
        else:
            # O chamador mantém ownership de sockets injetados. Reparentear uma
            # subclasse Python de QObject cria ownership duplo no PySide6.
            self._socket = socket_factory()
        self._socket.setMaxAllowedIncomingFrameSize(MAX_REALTIME_MESSAGE_BYTES)
        self._socket.setMaxAllowedIncomingMessageSize(MAX_REALTIME_MESSAGE_BYTES)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_text_message)
        self._socket.binaryMessageReceived.connect(self._on_binary_message)
        self._socket.errorOccurred.connect(self._on_error)
        self._socket.sslErrors.connect(self._on_ssl_errors)

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        self._enabled = True
        self.connect_now()

    def connect_now(self) -> None:
        if not self._enabled:
            return
        if self._socket.state() in {
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
            QAbstractSocket.SocketState.HostLookupState,
        }:
            return

        token = self._token_provider()
        if token is None or not token.strip():
            self._notify_authorization_rejected()
            return
        try:
            authorization = f"Bearer {token.strip()}".encode("ascii")
        except UnicodeEncodeError:
            self._notify_authorization_rejected()
            return

        request = QNetworkRequest(QUrl(self._endpoint_url))
        request.setRawHeader(b"Authorization", authorization)
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"User-Agent", b"2Identify-Admin/0.4.0")
        self._authorization_notified = False
        self._socket.open(request)

    def stop(self) -> None:
        self._enabled = False
        self._authorization_notified = False
        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeNormal,
                "client shutdown",
            )
            self._socket.abort()

    def disconnect_for_retry(self) -> None:
        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeGoingAway,
                "heartbeat timeout",
            )
            self._socket.abort()

    def abort_pending_connection(self) -> bool:
        if self._socket.state() not in {
            QAbstractSocket.SocketState.HostLookupState,
            QAbstractSocket.SocketState.ConnectingState,
        }:
            return False
        self._socket.abort()
        return True

    def reject_current_message(self) -> None:
        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeProtocolError,
                "invalid event envelope",
            )

    @Slot()
    def _on_connected(self) -> None:
        if self._enabled:
            self._authorization_notified = False
            self.connected.emit()

    @Slot()
    def _on_disconnected(self) -> None:
        if not self._enabled:
            return
        if self._closed_as_unauthorized():
            self._notify_authorization_rejected()
        else:
            self.disconnected.emit()

    @Slot(str)
    def _on_text_message(self, message: str) -> None:
        if not self._enabled:
            return
        try:
            message_size = len(message.encode("utf-8", errors="strict"))
        except UnicodeError:
            message_size = MAX_REALTIME_MESSAGE_BYTES + 1
        if message_size > MAX_REALTIME_MESSAGE_BYTES:
            self.protocol_failed.emit("Mensagem em tempo real excedeu o limite seguro.")
            self._socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeTooMuchData,
                "message too large",
            )
            return
        self.message_received.emit(message)

    @Slot(bytes)
    def _on_binary_message(self, _message: bytes) -> None:
        if not self._enabled:
            return
        self.protocol_failed.emit("O canal recebeu um formato não suportado.")
        self._socket.close(
            QWebSocketProtocol.CloseCode.CloseCodeDatatypeNotSupported,
            "text events required",
        )

    @Slot(object)
    def _on_error(self, error: object) -> None:
        if not self._enabled:
            return
        error_text = self._socket.errorString().casefold()
        if _UNAUTHORIZED_STATUS.search(error_text) or any(
            marker in error_text
            for marker in ("unauthorized", "forbidden", "não autorizado")
        ):
            self._notify_authorization_rejected()
            return
        error_value = getattr(error, "value", None)
        logger.warning(
            "Falha no transporte WebSocket",
            extra={"socket_error": error_value},
        )
        self.transport_failed.emit()

    @Slot(object)
    def _on_ssl_errors(self, errors: object) -> None:
        error_count = len(errors) if isinstance(errors, list | tuple) else 1
        logger.error(
            "Conexão WebSocket rejeitada por erro TLS",
            extra={"ssl_error_count": error_count},
        )
        self._socket.abort()
        if self._enabled:
            self.transport_failed.emit()

    def _closed_as_unauthorized(self) -> bool:
        close_code = self._socket.closeCode()
        code_value = getattr(close_code, "value", None)
        reason = self._socket.closeReason().casefold()
        return code_value in {4001, 4401} or any(
            marker in reason for marker in ("unauthorized", "forbidden", "401", "403")
        )

    def _notify_authorization_rejected(self) -> None:
        if not self._authorization_notified:
            self._authorization_notified = True
            self.authorization_rejected.emit()
