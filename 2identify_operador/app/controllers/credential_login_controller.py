"""Lifecycle controller for credential-based login."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.domain.auth import CredentialAuthenticationResult, LoginCredentials
from app.services.auth_service import AuthService
from app.ui.login import LoginWindow
from app.workers.credential_auth_worker import CredentialAuthenticationWorker

logger = logging.getLogger(__name__)


class CredentialLoginController(QObject):
    """Own one remote login attempt and its worker lifecycle."""

    operator_authenticated = Signal(object)

    def __init__(self, auth_service: AuthService, window: LoginWindow) -> None:
        super().__init__(window)
        self._auth_service = auth_service
        self._window = window
        self._worker: CredentialAuthenticationWorker | None = None
        self._window.credential_login_requested.connect(self.start)

    @Slot(object)
    def start(self, request: object) -> None:
        if not isinstance(request, LoginCredentials):
            logger.error("invalid_credential_login_request_type")
            self._window.show_credential_authentication_error(
                "Não foi possível processar a solicitação."
            )
            return

        worker = self._worker
        if worker is not None and worker.isRunning():
            self._window.show_credential_authentication_error(
                "A autenticação anterior ainda está em andamento."
            )
            return

        self._dispose_finished_worker()
        self._window.set_credential_authenticating(True)
        worker = CredentialAuthenticationWorker(self._auth_service, request)
        worker.authentication_succeeded.connect(self._handle_success)
        worker.authentication_failed.connect(self._handle_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("credential_authentication_attempt_started")
        worker.start()

    def shutdown(self, wait_timeout_ms: int = 15_000) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.requestInterruption()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("credential_authentication_worker_shutdown_timeout")
        self._dispose_finished_worker()

    @Slot(object)
    def _handle_success(self, result: object) -> None:
        if not isinstance(result, CredentialAuthenticationResult):
            self._handle_failure("A API retornou uma identidade inválida.", True)
            return

        self._window.show_credential_authentication_success(
            f"Acesso autorizado. Bem-vindo, {result.name}."
        )
        self.operator_authenticated.emit(result)

    @Slot(str, bool)
    def _handle_failure(self, message: str, unavailable: bool) -> None:
        self._window.show_credential_authentication_error(message)
        logger.warning(
            "credential_authentication_attempt_failed",
            extra={"unavailable": unavailable},
        )

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("credential_authentication_attempt_finished")

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
