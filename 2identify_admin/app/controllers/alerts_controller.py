"""Coordinate the persistent administrative alert inbox."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.core.session import AdminSessionContext
from app.domain import AdminAlert, AdminAlertPage
from app.services.admin_alerts_service import AdminAlertsService
from app.ui.alerts import AlertsPage
from app.workers import AdminAlertActionWorker, AdminAlertsListWorker


class AlertsController(QObject):
    session_expired = Signal(str)
    alerts_changed = Signal()
    shutdown_complete = Signal()

    def __init__(
        self,
        view: AlertsPage,
        service: AdminAlertsService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._view = view
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._list_worker: AdminAlertsListWorker | None = None
        self._action_worker: AdminAlertActionWorker | None = None
        self._refresh_pending = False
        self._shutdown_requested = False
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(0)
        self._load_timer.timeout.connect(self.request_refresh)
        view.refresh_requested.connect(self.request_refresh)
        view.confirm_requested.connect(self.confirm_alert)
        view.close_requested.connect(self.close_alert)

    def start(self) -> None:
        self._load_timer.start()

    @Slot()
    def request_refresh(self) -> None:
        if self._shutdown_requested:
            return
        if self._list_worker is not None or self._action_worker is not None:
            self._refresh_pending = True
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_loading()
        worker = AdminAlertsListWorker(self._service, session)
        self._list_worker = worker
        worker.succeeded.connect(self._on_list_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_list_finished)
        worker.start()

    @Slot(int)
    def confirm_alert(self, alert_id: int) -> None:
        self._start_action(alert_id, "confirm")

    @Slot(int)
    def close_alert(self, alert_id: int) -> None:
        self._start_action(alert_id, "close")

    def _start_action(
        self,
        alert_id: int,
        action: Literal["confirm", "close"],
    ) -> None:
        if self._shutdown_requested or self._action_worker is not None:
            return
        if self._list_worker is not None:
            self._refresh_pending = True
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_action_loading(action)
        worker = AdminAlertActionWorker(
            self._service,
            session,
            alert_id,
            action,
        )
        self._action_worker = worker
        worker.succeeded.connect(self._on_action_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_action_finished)
        worker.start()

    @Slot(object)
    def _on_list_success(self, value: object) -> None:
        if not isinstance(value, AdminAlertPage):
            self._view.show_error("A API retornou uma lista de alertas inválida.")
            return
        self._view.set_alerts(value)

    @Slot(object, str)
    def _on_action_success(self, value: object, action: str) -> None:
        if not isinstance(value, AdminAlert):
            self._view.show_error("A API retornou um alerta inválido.")
            return
        self._view.update_alert(value)
        self._view.show_action_success(action)
        self._refresh_pending = True
        self.alerts_changed.emit()

    @Slot(str, bool)
    def _on_failure(self, message: str, expired: bool) -> None:
        if expired:
            self._refresh_pending = False
            self.session_expired.emit(message)
        else:
            self._view.show_error(message)

    @Slot()
    def _on_list_finished(self) -> None:
        worker = self._list_worker
        self._list_worker = None
        if worker is not None:
            worker.deleteLater()
        self._continue_or_finish_shutdown()

    @Slot()
    def _on_action_finished(self) -> None:
        worker = self._action_worker
        self._action_worker = None
        if worker is not None:
            worker.deleteLater()
        self._continue_or_finish_shutdown()

    def _continue_or_finish_shutdown(self) -> None:
        if self._shutdown_requested:
            if self._list_worker is None and self._action_worker is None:
                self._shutdown_requested = False
                self.shutdown_complete.emit()
            return
        if self._refresh_pending:
            self._refresh_pending = False
            self._load_timer.start()

    def shutdown(self) -> bool:
        self._load_timer.stop()
        self._refresh_pending = False
        workers = tuple(
            worker
            for worker in (self._list_worker, self._action_worker)
            if worker is not None and worker.isRunning()
        )
        if not workers:
            return True
        self._shutdown_requested = True
        for worker in workers:
            worker.requestInterruption()
        return all(worker.wait(self._shutdown_timeout_ms) for worker in workers)


__all__ = ["AlertsController"]
