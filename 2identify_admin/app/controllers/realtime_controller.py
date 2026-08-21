from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from random import uniform
from typing import Literal
from uuid import UUID

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWebSockets import QWebSocket

from app.core.config import Settings
from app.core.session import AdminSessionContext
from app.domain import ConnectionReadyEvent, HeartbeatEvent
from app.realtime import (
    AdminWebSocketClient,
    InvalidRealtimeEventError,
    derive_admin_websocket_url,
    parse_realtime_event,
)
from app.services.admin_auth_service import AdminAuthService
from app.ui.main.main_window import MainWindow
from app.workers import AdminSessionValidationWorker

logger = logging.getLogger(__name__)
_REFRESH_DEBOUNCE_MS = 750
_WATCHDOG_TIMEOUT_MS = 45_000
_MAX_DEDUPLICATION_IDS = 512


class RealtimeController(QObject):
    """Coordena conexão, backoff, autenticação e efeitos passivos na UI."""

    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        settings: Settings,
        session_context: AdminSessionContext,
        auth_service: AdminAuthService,
        view: MainWindow,
        refresh_dashboard: Callable[[], None],
        *,
        socket_factory: Callable[[], QWebSocket] | None = None,
        random_uniform: Callable[[float, float], float] = uniform,
        refresh_debounce_ms: int = _REFRESH_DEBOUNCE_MS,
        watchdog_timeout_ms: int = _WATCHDOG_TIMEOUT_MS,
    ) -> None:
        super().__init__()
        if refresh_debounce_ms <= 0 or watchdog_timeout_ms <= 0:
            raise ValueError("Os intervalos do canal em tempo real devem ser positivos.")
        self._session_context = session_context
        self._auth_service = auth_service
        self._view = view
        self._refresh_dashboard = refresh_dashboard
        self._random_uniform = random_uniform
        self._shutdown_timeout_ms = settings.worker_shutdown_timeout_ms
        self._running = False
        self._ready_received = False
        self._reconnect_attempt = 0
        self._validation_worker: AdminSessionValidationWorker | None = None
        self._shutdown_requested = False
        self._validation_result: Literal["valid", "expired", "offline"] | None = None
        self._validation_message = ""
        self._seen_event_ids: set[UUID] = set()
        self._event_id_order: deque[UUID] = deque()

        endpoint_url = derive_admin_websocket_url(str(settings.api_url))
        session_context = self._session_context

        def current_access_token() -> str | None:
            session = session_context.current()
            return session.access_token if session is not None else None

        self._client = AdminWebSocketClient(
            endpoint_url,
            current_access_token,
            socket_factory=socket_factory,
            parent=self,
        )
        self._client.connected.connect(self._on_connected)
        self._client.disconnected.connect(self._on_disconnected)
        self._client.message_received.connect(self._on_message)
        self._client.authorization_rejected.connect(
            self._on_authorization_rejected
        )
        self._client.transport_failed.connect(self._on_transport_failed)
        self._client.protocol_failed.connect(self._on_protocol_failed)

        self._connect_timeout_timer = QTimer(self)
        self._connect_timeout_timer.setSingleShot(True)
        self._connect_timeout_timer.setInterval(
            max(1, round(settings.api_connect_timeout_seconds * 1000))
        )
        self._connect_timeout_timer.timeout.connect(self._on_connect_timeout)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._connect_now)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(refresh_debounce_ms)
        self._refresh_timer.timeout.connect(self._refresh_dashboard_if_running)
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.setInterval(watchdog_timeout_ms)
        self._watchdog_timer.timeout.connect(self._on_watchdog_timeout)

    @property
    def endpoint_url(self) -> str:
        return self._client.endpoint_url

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def reconnect_interval_ms(self) -> int:
        return self._reconnect_timer.interval()

    @property
    def reconnect_is_active(self) -> bool:
        return self._reconnect_timer.isActive()

    @property
    def has_active_timers(self) -> bool:
        return any(
            timer.isActive()
            for timer in (
                self._connect_timeout_timer,
                self._reconnect_timer,
                self._refresh_timer,
                self._watchdog_timer,
            )
        )

    @property
    def validation_is_active(self) -> bool:
        worker = self._validation_worker
        return worker is not None and worker.isRunning()

    @property
    def watchdog_remaining_ms(self) -> int:
        return self._watchdog_timer.remainingTime()

    @property
    def connect_timeout_is_active(self) -> bool:
        return self._connect_timeout_timer.isActive()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._shutdown_requested = False
        self._set_status("Conectando canal em tempo real...", state="connecting")
        self._connect_timeout_timer.start()
        self._client.start()

    def shutdown(self) -> bool:
        self._running = False
        self._ready_received = False
        self._connect_timeout_timer.stop()
        self._reconnect_timer.stop()
        self._refresh_timer.stop()
        self._watchdog_timer.stop()
        self._client.stop()

        worker = self._validation_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            if not worker.wait(self._shutdown_timeout_ms):
                self._shutdown_requested = True
                return False
            self._dispose_validation_worker(worker)
            self._shutdown_requested = False
            return True
        if worker is not None:
            self._dispose_validation_worker(worker)
        self._shutdown_requested = False
        return True

    @Slot()
    def _on_connected(self) -> None:
        if not self._running:
            return
        self._connect_timeout_timer.stop()
        self._reconnect_timer.stop()
        self._ready_received = False
        self._watchdog_timer.start()
        self._set_status("Canal conectado; validando contrato...", state="connecting")

    @Slot()
    def _on_disconnected(self) -> None:
        self._connect_timeout_timer.stop()
        if not self._running or self._validation_worker is not None:
            return
        self._ready_received = False
        self._watchdog_timer.stop()
        self._set_status(
            "Tempo real indisponível — tentando reconectar.",
            state="offline",
        )
        self._schedule_reconnect()

    @Slot()
    def _on_transport_failed(self) -> None:
        self._on_disconnected()

    @Slot(str)
    def _on_protocol_failed(self, _message: str) -> None:
        if self._running:
            self._set_status(
                "Canal em tempo real recebeu uma mensagem incompatível.",
                state="offline",
            )

    @Slot(str)
    def _on_message(self, raw_message: str) -> None:
        if not self._running:
            return
        try:
            event = parse_realtime_event(raw_message)
        except InvalidRealtimeEventError:
            logger.warning("Evento WebSocket rejeitado pelo contrato")
            self._client.reject_current_message()
            self._set_status(
                "Canal em tempo real recebeu uma mensagem incompatível.",
                state="offline",
            )
            return

        if isinstance(event, ConnectionReadyEvent):
            self._ready_received = True
            self._reconnect_attempt = 0
            self._watchdog_timer.start()
            self._set_status(
                "Conectado — aguardando integração de alertas.",
                state="connected",
            )
            return
        if isinstance(event, HeartbeatEvent):
            if self._ready_received:
                self._watchdog_timer.start()
            return
        if not self._ready_received:
            logger.warning("Evento de alerta recebido antes de connection.ready")
            self._client.reject_current_message()
            return
        if self._is_duplicate(event.event_id):
            return

        self._watchdog_timer.start()
        self._view.show_realtime_alert(event)
        self._refresh_timer.start()

    @Slot()
    def _on_authorization_rejected(self) -> None:
        if not self._running or self._validation_worker is not None:
            return
        self._connect_timeout_timer.stop()
        self._reconnect_timer.stop()
        self._watchdog_timer.stop()
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return

        self._set_status("Revalidando sessão administrativa...", state="connecting")
        worker = AdminSessionValidationWorker(self._auth_service, session)
        self._validation_worker = worker
        self._validation_result = None
        self._validation_message = ""
        worker.succeeded.connect(self._on_validation_succeeded)
        worker.failed.connect(self._on_validation_failed)
        worker.finished.connect(self._on_validation_finished)
        worker.start()

    @Slot()
    def _on_validation_succeeded(self) -> None:
        self._validation_result = "valid"

    @Slot(str, bool)
    def _on_validation_failed(self, message: str, expired: bool) -> None:
        self._validation_result = "expired" if expired else "offline"
        self._validation_message = message

    @Slot()
    def _on_validation_finished(self) -> None:
        worker = self._validation_worker
        self._validation_worker = None
        if worker is not None:
            worker.deleteLater()

        if self._shutdown_requested:
            self._shutdown_requested = False
            self.shutdown_complete.emit()
            return
        if not self._running:
            return
        if self._validation_result == "expired":
            self.session_expired.emit(
                self._validation_message or "Sua sessão expirou. Entre novamente."
            )
            return

        self._set_status(
            "Tempo real indisponível — tentando reconectar.",
            state="offline",
        )
        self._schedule_reconnect()

    @Slot()
    def _on_watchdog_timeout(self) -> None:
        if not self._running:
            return
        self._ready_received = False
        self._client.disconnect_for_retry()
        self._set_status(
            "Tempo real sem heartbeat — tentando reconectar.",
            state="offline",
        )
        self._schedule_reconnect()

    @Slot()
    def _on_connect_timeout(self) -> None:
        if not self._running or not self._client.abort_pending_connection():
            return
        self._ready_received = False
        self._set_status(
            "Tempo real não respondeu — tentando reconectar.",
            state="offline",
        )
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if not self._running or self._reconnect_timer.isActive():
            return
        self._reconnect_attempt += 1
        base_seconds = min(30.0, float(2 ** min(self._reconnect_attempt - 1, 5)))
        jitter_factor = self._random_uniform(0.8, 1.2)
        delay_seconds = min(30.0, max(1.0, base_seconds * jitter_factor))
        self._reconnect_timer.start(round(delay_seconds * 1000))

    @Slot()
    def _connect_now(self) -> None:
        if not self._running:
            return
        self._connect_timeout_timer.start()
        self._client.connect_now()

    @Slot()
    def _refresh_dashboard_if_running(self) -> None:
        if self._running:
            self._refresh_dashboard()

    def _set_status(self, message: str, *, state: str) -> None:
        self._view.set_realtime_status(message, state=state)

    def _is_duplicate(self, event_id: UUID) -> bool:
        if event_id in self._seen_event_ids:
            return True
        self._seen_event_ids.add(event_id)
        self._event_id_order.append(event_id)
        while len(self._event_id_order) > _MAX_DEDUPLICATION_IDS:
            oldest = self._event_id_order.popleft()
            self._seen_event_ids.discard(oldest)
        return False

    def _dispose_validation_worker(
        self,
        worker: AdminSessionValidationWorker,
    ) -> None:
        for signal, slot in (
            (worker.succeeded, self._on_validation_succeeded),
            (worker.failed, self._on_validation_failed),
            (worker.finished, self._on_validation_finished),
        ):
            try:
                signal.disconnect(slot)
            except RuntimeError:
                pass
        if self._validation_worker is worker:
            self._validation_worker = None
        worker.deleteLater()
