"""QThread boundary for blocking credential authentication."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.domain.auth import LoginCredentials
from app.services.auth_service import (
    AuthenticationUnavailableError,
    AuthService,
    CredentialsRejectedError,
)

logger = logging.getLogger(__name__)


class CredentialAuthenticationWorker(QThread):
    """Execute the remote authentication call without blocking the UI thread."""

    authentication_succeeded = Signal(object)
    authentication_failed = Signal(str, bool)

    def __init__(self, auth_service: AuthService, credentials: LoginCredentials) -> None:
        super().__init__()
        self.setObjectName("CredentialAuthenticationWorker")
        self._auth_service = auth_service
        self._credentials: LoginCredentials | None = credentials

    def run(self) -> None:
        credentials = self._credentials
        if credentials is None or self.isInterruptionRequested():
            return

        try:
            result = self._auth_service.authenticate_credentials(credentials)
            if not self.isInterruptionRequested():
                self.authentication_succeeded.emit(result)
        except CredentialsRejectedError as error:
            self.authentication_failed.emit(str(error), False)
        except AuthenticationUnavailableError as error:
            self.authentication_failed.emit(str(error), True)
        except Exception:
            logger.exception("credential_authentication_worker_failed")
            self.authentication_failed.emit(
                "Falha inesperada durante a autenticação.",
                False,
            )
        finally:
            # Do not retain the password on a long-lived QThread wrapper.
            self._credentials = None
