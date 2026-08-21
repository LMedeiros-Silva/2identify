from __future__ import annotations

import json
import time
from collections.abc import Callable

import httpx
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from app.api import AdminApiClient
from app.controllers.realtime_controller import RealtimeController
from app.core.config import Settings
from app.core.session import AdminSessionContext
from app.domain import AdminAuthentication, AdminCredentials, Administrator
from app.services.admin_auth_service import AdminAuthService
from app.ui.main.main_window import MainWindow


class FakeWebSocket(QWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.fake_state = QAbstractSocket.SocketState.UnconnectedState
        self.requests: list[QNetworkRequest] = []
        self.close_calls: list[tuple[object, str]] = []
        self.abort_count = 0
        self.fake_error = ""

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

    def simulate_connected(self) -> None:
        self.fake_state = QAbstractSocket.SocketState.ConnectedState
        self.connected.emit()

    def simulate_disconnected(self) -> None:
        self.fake_state = QAbstractSocket.SocketState.UnconnectedState
        self.disconnected.emit()


class StaticProvider:
    def __init__(self, administrator: Administrator, *, delay: float = 0) -> None:
        self.administrator = administrator
        self.delay = delay
        self.revalidation_calls = 0

    def login(self, _credentials: AdminCredentials) -> AdminAuthentication:
        raise AssertionError("login não deveria ser chamado")

    def get_current_administrator(self, _access_token: str) -> Administrator:
        self.revalidation_calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.administrator


def settings(*, connect_timeout_seconds: float = 3.0) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        API_URL="https://api.example.test",
        API_CONNECT_TIMEOUT_SECONDS=connect_timeout_seconds,
    )


def administrator() -> Administrator:
    return Administrator(
        id=1,
        name="Admin",
        username="admin",
        profile="administrador",
    )


def session_context() -> AdminSessionContext:
    context = AdminSessionContext()
    context.open(
        AdminAuthentication(
            administrator=administrator(),
            access_token="secret.jwt.value",
            expires_in=300,
        )
    )
    return context


def wait_until(qapp, predicate: Callable[[], bool], timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("A condição Qt não foi atendida dentro do prazo.")


def event(event_type: str, payload: dict[str, object], *, event_id: int) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "event_id": f"12345678-1234-4234-8234-{event_id:012d}",
            "event_type": event_type,
            "occurred_at": "2026-08-20T12:00:00Z",
            "payload": payload,
        }
    )


def ready_event() -> str:
    return event(
        "connection.ready",
        {"status": "awaiting_alert_ingestion"},
        event_id=1,
    )


def alert_event(event_id: int) -> str:
    return event(
        "alert.created",
        {
            "alert_id": event_id,
            "occurrence_id": 10 + event_id,
            "level": "critical",
            "status": "nao_lido",
            "summary": "<b>Capacete ausente</b>",
            "detected_at": "2026-08-20T11:59:59Z",
            "camera_id": 2,
        },
        event_id=event_id,
    )


def build_controller(
    *,
    socket: FakeWebSocket,
    context: AdminSessionContext,
    view: MainWindow,
    refresh: Callable[[], None],
    auth_service: AdminAuthService | None = None,
    watchdog_timeout_ms: int = 45_000,
    refresh_debounce_ms: int = 30,
    connect_timeout_seconds: float = 3.0,
) -> RealtimeController:
    service = auth_service or AdminAuthService(StaticProvider(administrator()))
    return RealtimeController(
        settings(connect_timeout_seconds=connect_timeout_seconds),
        context,
        service,
        view,
        refresh,
        socket_factory=lambda: socket,
        random_uniform=lambda _low, _high: 1.0,
        watchdog_timeout_ms=watchdog_timeout_ms,
        refresh_debounce_ms=refresh_debounce_ms,
    )


def test_ready_alert_ui_and_dashboard_refresh_are_debounced(qapp) -> None:
    socket = FakeWebSocket()
    context = session_context()
    view = MainWindow(administrator())
    refreshes: list[None] = []
    controller = build_controller(
        socket=socket,
        context=context,
        view=view,
        refresh=lambda: refreshes.append(None),
    )
    controller.start()
    socket.simulate_connected()
    assert not controller.connect_timeout_is_active
    socket.textMessageReceived.emit(ready_event())

    assert (
        view.alerts.connection_status.text()
        == "Conectado — aguardando integração de alertas."
    )

    socket.textMessageReceived.emit(alert_event(7))
    socket.textMessageReceived.emit(alert_event(8))
    socket.textMessageReceived.emit(alert_event(8))

    assert view.alerts.alert_list.count() == 2
    assert view.dashboard.card_alertas.valor_label.text() == "—"  # type: ignore[attr-defined]
    assert view.alerts.alert_banner_text.textFormat().name == "PlainText"
    assert view.dashboard.realtime_alert_banner.textFormat().name == "PlainText"
    assert "<b>Capacete ausente</b>" in view.alerts.alert_banner_text.text()
    wait_until(qapp, lambda: len(refreshes) == 1)
    assert len(refreshes) == 1

    controller.shutdown()
    assert not controller.has_active_timers
    assert not controller.validation_is_active
    assert socket.fake_state == QAbstractSocket.SocketState.UnconnectedState
    view.close()


def test_disconnect_reconnects_with_backoff_and_keeps_session(qapp) -> None:
    del qapp
    socket = FakeWebSocket()
    context = session_context()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=context,
        view=view,
        refresh=lambda: None,
    )
    controller.start()
    socket.simulate_connected()
    socket.simulate_disconnected()

    assert controller.reconnect_is_active
    assert controller.reconnect_interval_ms == 1000
    assert context.current() is not None
    assert "tentando reconectar" in view.alerts.connection_status.text()

    controller.shutdown()
    assert not controller.reconnect_is_active
    assert not controller.has_active_timers
    assert context.current() is not None
    view.close()


def test_accept_and_drop_without_ready_increases_backoff(qapp) -> None:
    del qapp
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=session_context(),
        view=view,
        refresh=lambda: None,
    )
    controller.start()
    socket.simulate_connected()
    socket.simulate_disconnected()
    assert controller.reconnect_interval_ms == 1000

    controller._reconnect_timer.stop()  # type: ignore[attr-defined]
    controller._client.connect_now()  # type: ignore[attr-defined]
    socket.simulate_connected()
    socket.simulate_disconnected()
    assert controller.reconnect_interval_ms == 2000

    controller._reconnect_timer.stop()  # type: ignore[attr-defined]
    controller._client.connect_now()  # type: ignore[attr-defined]
    socket.simulate_connected()
    socket.textMessageReceived.emit(ready_event())
    socket.simulate_disconnected()
    assert controller.reconnect_interval_ms == 1000
    controller.shutdown()
    view.close()


def test_watchdog_forces_reconnect_when_ready_or_heartbeat_stops(qapp) -> None:
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=session_context(),
        view=view,
        refresh=lambda: None,
        watchdog_timeout_ms=20,
    )
    controller.start()
    socket.simulate_connected()

    wait_until(qapp, lambda: controller.reconnect_is_active)

    assert socket.abort_count == 1
    assert socket.close_calls[-1][1] == "heartbeat timeout"
    assert "sem heartbeat" in view.alerts.connection_status.text()
    controller.shutdown()
    view.close()


def test_connecting_socket_times_out_aborts_and_uses_backoff(qapp) -> None:
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=session_context(),
        view=view,
        refresh=lambda: None,
        connect_timeout_seconds=0.02,
    )

    controller.start()
    assert controller.connect_timeout_is_active
    assert socket.fake_state == QAbstractSocket.SocketState.ConnectingState
    wait_until(qapp, lambda: controller.reconnect_is_active)

    assert socket.abort_count == 1
    assert socket.fake_state == QAbstractSocket.SocketState.UnconnectedState
    assert not controller.connect_timeout_is_active
    assert controller.reconnect_interval_ms == 1000
    controller.shutdown()
    assert not controller.has_active_timers
    assert socket.fake_state == QAbstractSocket.SocketState.UnconnectedState
    view.close()


def test_heartbeat_only_refreshes_watchdog_after_ready(qapp) -> None:
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=session_context(),
        view=view,
        refresh=lambda: None,
        watchdog_timeout_ms=500,
    )
    controller.start()
    socket.simulate_connected()
    time.sleep(0.1)
    qapp.processEvents()
    remaining_before_early_heartbeat = controller.watchdog_remaining_ms
    socket.textMessageReceived.emit(
        event("connection.heartbeat", {}, event_id=90)
    )
    remaining_after_early_heartbeat = controller.watchdog_remaining_ms
    assert remaining_after_early_heartbeat <= remaining_before_early_heartbeat + 30

    socket.textMessageReceived.emit(ready_event())
    time.sleep(0.1)
    qapp.processEvents()
    remaining_before_valid_heartbeat = controller.watchdog_remaining_ms
    socket.textMessageReceived.emit(
        event("connection.heartbeat", {}, event_id=91)
    )
    assert controller.watchdog_remaining_ms > remaining_before_valid_heartbeat + 50
    controller.shutdown()
    view.close()


def test_websocket_401_revalidates_admin_me_and_returns_to_login(qapp) -> None:
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        return httpx.Response(401, json={"detail": "expired"})

    api_client = AdminApiClient(
        settings(),
        transport=httpx.MockTransport(handler),
    )
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=session_context(),
        view=view,
        refresh=lambda: None,
        auth_service=AdminAuthService(api_client),
    )
    expired_spy = QSignalSpy(controller.session_expired)
    controller.start()
    socket.fake_error = "Handshake failed with HTTP status 401"
    socket.errorOccurred.emit(QAbstractSocket.SocketError.ConnectionRefusedError)

    wait_until(qapp, lambda: expired_spy.count() == 1)

    assert observed_paths == ["/admin/me"]
    controller.shutdown()
    api_client.close()
    view.close()


def test_websocket_401_offline_preserves_session_and_retries(qapp) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    api_client = AdminApiClient(
        settings(),
        transport=httpx.MockTransport(handler),
    )
    context = session_context()
    socket = FakeWebSocket()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=context,
        view=view,
        refresh=lambda: None,
        auth_service=AdminAuthService(api_client),
    )
    controller.start()
    socket.fake_error = "HTTP 401"
    socket.errorOccurred.emit(QAbstractSocket.SocketError.ConnectionRefusedError)

    wait_until(qapp, lambda: controller.reconnect_is_active)

    assert context.current() is not None
    controller.shutdown()
    api_client.close()
    view.close()


def test_shutdown_waits_for_active_revalidation_worker(qapp) -> None:
    provider = StaticProvider(administrator(), delay=0.05)
    socket = FakeWebSocket()
    context = session_context()
    view = MainWindow(administrator())
    controller = build_controller(
        socket=socket,
        context=context,
        view=view,
        refresh=lambda: None,
        auth_service=AdminAuthService(provider),
    )
    controller.start()
    socket.fake_error = "HTTP 401"
    socket.errorOccurred.emit(QAbstractSocket.SocketError.ConnectionRefusedError)
    wait_until(
        qapp,
        lambda: controller._validation_worker is not None  # type: ignore[attr-defined]
        and controller._validation_worker.isRunning(),  # type: ignore[attr-defined]
    )

    assert controller.shutdown()
    assert not controller.is_running
    assert not controller.has_active_timers
    assert not controller.validation_is_active
    assert socket.fake_state == QAbstractSocket.SocketState.UnconnectedState
    assert context.current() is not None
    view.close()
