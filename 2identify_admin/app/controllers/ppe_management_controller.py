"""Reconcile HTTP snapshots with events received while the request is running."""

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.core.session import AdminSessionContext
from app.domain.ppe_management import ActiveOperationSnapshot
from app.services.admin_ppe_management_service import AdminPpeManagementService
from app.ui.ppe import PpeManagementPage
from app.workers.ppe_management_worker import PpeManagementWorker


class PpeManagementController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        view: PpeManagementPage,
        service: AdminPpeManagementService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._view = view
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._worker: PpeManagementWorker | None = None
        self._updates: list[ActiveOperationSnapshot] = []
        self._refresh_pending = False
        self._stopped = False
        self._shutdown_pending = False
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self.request_refresh)
        view.refresh_requested.connect(self.request_refresh)

    @property
    def is_loading(self) -> bool:
        return self._worker is not None

    def start(self) -> None:
        self._load_timer.start(0)

    @Slot()
    def request_refresh(self) -> None:
        if self._stopped:
            return
        self._load_timer.stop()
        if self._worker is not None:
            self._refresh_pending = True
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._updates.clear()
        self._view.show_loading()
        worker = PpeManagementWorker(self._service, session)
        self._worker = worker
        worker.succeeded.connect(self._on_snapshot)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        worker.start()

    @Slot(object)
    def apply_update(self, snapshot: ActiveOperationSnapshot) -> None:
        if self._stopped:
            return
        if self._worker is not None:
            self._updates.append(snapshot)
        self._view.apply_update(snapshot)

    @Slot(object)
    def _on_snapshot(self, snapshots: tuple[ActiveOperationSnapshot, ...]) -> None:
        if self._stopped:
            return
        self._view.show_snapshot(snapshots)
        for snapshot in self._updates:
            self._view.apply_update(snapshot)

    @Slot(str, bool)
    def _on_failure(self, message: str, expired: bool) -> None:
        if self._stopped:
            return
        if expired:
            self._refresh_pending = False
            self.session_expired.emit(message)
        else:
            self._view.show_error(message)

    @Slot()
    def _on_finished(self) -> None:
        self._dispose_worker()
        if self._shutdown_pending:
            self._shutdown_pending = False
            self.shutdown_complete.emit()
        elif self._refresh_pending and not self._stopped:
            self._refresh_pending = False
            self._load_timer.start(0)

    def _dispose_worker(self) -> None:
        worker = self._worker
        if worker is not None:
            worker.succeeded.disconnect(self._on_snapshot)
            worker.failed.disconnect(self._on_failure)
            worker.finished.disconnect(self._on_finished)
            worker.deleteLater()
            self._worker = None
        self._updates.clear()

    def shutdown(self) -> bool:
        self._stopped = True
        self._load_timer.stop()
        self._refresh_pending = False
        worker = self._worker
        if worker is not None:
            worker.requestInterruption()
            if not worker.wait(self._shutdown_timeout_ms):
                self._shutdown_pending = True
                return False
            self._dispose_worker()
        self._shutdown_pending = False
        return True
