from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.domain import AdminCredentials
from app.services.admin_auth_service import AdminAuthService
from app.ui.login.login_window import LoginWindow
from app.workers import AdminLoginWorker


class LoginController(QObject):
    authenticated = Signal(object)

    def __init__(
        self,
        view: LoginWindow,
        service: AdminAuthService,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._view = view
        self._service = service
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._worker: AdminLoginWorker | None = None
        self._view.login_requested.connect(self.authenticate)

    @Slot(object)
    def authenticate(self, credentials: AdminCredentials) -> None:
        if self._worker is not None:
            return

        self._view.set_authenticating(True)
        worker = AdminLoginWorker(self._service, credentials)
        self._worker = worker
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        worker.start()

    @Slot(object)
    def _on_success(self, authentication: object) -> None:
        self._view.set_authenticating(False)
        self._view.clear_password()
        self.authenticated.emit(authentication)

    @Slot(str, bool)
    def _on_failure(self, message: str, _retryable: bool) -> None:
        self._view.set_authenticating(False)
        self._view.clear_password()
        self._view.show_error(message)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def shutdown(self) -> bool:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            return worker.wait(self._shutdown_timeout_ms)
        return True
