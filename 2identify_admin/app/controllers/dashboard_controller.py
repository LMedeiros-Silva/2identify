from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.core.session import AdminSessionContext
from app.domain import DashboardSummary
from app.services.admin_dashboard_service import AdminDashboardService
from app.ui.dashboard.dashboard_page import DashboardPage
from app.workers import DashboardSummaryWorker


class DashboardController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        view: DashboardPage,
        service: AdminDashboardService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._view = view
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._worker: DashboardSummaryWorker | None = None
        self._shutdown_requested = False
        self._refresh_pending = False
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(0)
        self._load_timer.timeout.connect(self.request_refresh)
        self._view.refresh_requested.connect(self.request_refresh)

    def start(self) -> None:
        self._load_timer.start()

    @Slot()
    def load(self) -> None:
        """Compatibilidade interna: agenda uma atualização sem perdê-la."""
        self.request_refresh()

    @Slot()
    def request_refresh(self) -> None:
        if self._shutdown_requested:
            return
        if self._worker is not None:
            self._refresh_pending = True
            return

        session = self._session_context.current()
        if session is None:
            self._refresh_pending = False
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return

        self._view.show_loading()
        worker = DashboardSummaryWorker(self._service, session)
        self._worker = worker
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        worker.start()

    @Slot(object)
    def _on_success(self, summary: object) -> None:
        if not isinstance(summary, DashboardSummary):
            self._view.show_error("A API retornou indicadores inválidos.")
            return
        self._view.show_summary(summary)

    @Slot(str, bool)
    def _on_failure(self, message: str, expired: bool) -> None:
        if expired:
            self._refresh_pending = False
            self.session_expired.emit(message)
        else:
            self._view.show_error(message)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._shutdown_requested:
            self._refresh_pending = False
            self._shutdown_requested = False
            self.shutdown_complete.emit()
            return
        if self._refresh_pending:
            self._refresh_pending = False
            self._load_timer.start()

    def shutdown(self) -> bool:
        self._load_timer.stop()
        self._refresh_pending = False
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._shutdown_requested = True
            worker.requestInterruption()
            return worker.wait(self._shutdown_timeout_ms)
        return True
