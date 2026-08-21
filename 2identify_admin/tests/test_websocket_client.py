from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from app.realtime import MAX_REALTIME_MESSAGE_BYTES, AdminWebSocketClient


class FakeWebSocket(QWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.fake_state = QAbstractSocket.SocketState.UnconnectedState
        self.requests: list[QNetworkRequest] = []
        self.abort_count = 0
        self.close_calls: list[tuple[object, str]] = []
        self.fake_error = ""
        self.fake_close_code = 1000
        self.fake_close_reason = ""

    def state(self) -> QAbstractSocket.SocketState:
        return self.fake_state

    def open(self, request: QNetworkRequest) -> None:
        self.requests.append(QNetworkRequest(request))
        self.fake_state = QAbstractSocket.SocketState.ConnectingState

    def close(
        self,
        close_code: QWebSocketProtocol.CloseCode = (
            QWebSocketProtocol.CloseCode.CloseCodeNormal
        ),
        reason: str = "",
    ) -> None:
        self.close_calls.append((close_code, reason))
        self.fake_state = QAbstractSocket.SocketState.ClosingState

    def abort(self) -> None:
        self.abort_count += 1
        self.fake_state = QAbstractSocket.SocketState.UnconnectedState

    def errorString(self) -> str:
        return self.fake_error

    def closeCode(self) -> object:
        return SimpleNamespace(value=self.fake_close_code)

    def closeReason(self) -> str:
        return self.fake_close_reason


def test_authorization_header_is_not_leaked_to_url_or_repr(qapp) -> None:
    del qapp
    token = "secret.jwt.value"
    socket = FakeWebSocket()
    client = AdminWebSocketClient(
        "wss://api.example.test/ws/admin/alerts",
        lambda: token,
        socket_factory=lambda: socket,
    )

    assert socket.parent() is None
    client.start()

    assert len(socket.requests) == 1
    request = socket.requests[0]
    assert bytes(request.rawHeader("Authorization")) == b"Bearer secret.jwt.value"
    assert request.url().toString() == "wss://api.example.test/ws/admin/alerts"
    assert token not in request.url().toString()
    assert token not in repr(client)
    assert socket.maxAllowedIncomingFrameSize() == MAX_REALTIME_MESSAGE_BYTES
    assert socket.maxAllowedIncomingMessageSize() == MAX_REALTIME_MESSAGE_BYTES
    client.stop()


def test_binary_and_oversized_messages_are_closed(qapp) -> None:
    del qapp
    socket = FakeWebSocket()
    client = AdminWebSocketClient(
        "wss://api.example.test/ws/admin/alerts",
        lambda: "token",
        socket_factory=lambda: socket,
    )
    client.start()
    socket.fake_state = QAbstractSocket.SocketState.ConnectedState

    socket.binaryMessageReceived.emit(b"binary")
    assert socket.close_calls[-1][0] == (
        QWebSocketProtocol.CloseCode.CloseCodeDatatypeNotSupported
    )

    socket.fake_state = QAbstractSocket.SocketState.ConnectedState
    socket.textMessageReceived.emit("x" * (MAX_REALTIME_MESSAGE_BYTES + 1))
    assert socket.close_calls[-1][0] == (
        QWebSocketProtocol.CloseCode.CloseCodeTooMuchData
    )
    client.stop()


def test_ssl_errors_abort_without_ignoring_them(qapp) -> None:
    del qapp
    socket = FakeWebSocket()
    client = AdminWebSocketClient(
        "wss://api.example.test/ws/admin/alerts",
        lambda: "token",
        socket_factory=lambda: socket,
    )
    client.start()
    socket.fake_state = QAbstractSocket.SocketState.ConnectedState

    client._on_ssl_errors([])

    assert socket.abort_count == 1
    client.stop()


def test_custom_4401_close_is_treated_as_authorization_rejection(qapp) -> None:
    socket = FakeWebSocket()
    client = AdminWebSocketClient(
        "wss://api.example.test/ws/admin/alerts",
        lambda: "token",
        socket_factory=lambda: socket,
    )
    spy = QSignalSpy(client.authorization_rejected)
    client.start()
    socket.fake_close_code = 4401
    socket.fake_state = QAbstractSocket.SocketState.UnconnectedState
    socket.disconnected.emit()
    qapp.processEvents()

    assert spy.count() == 1
    client.stop()
