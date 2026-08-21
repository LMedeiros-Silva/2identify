from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.core.session import AdminSession
from app.domain import AdminCredentials
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.errors import (
    AdminServiceError,
    ApiUnavailableError,
    InvalidApiResponseError,
    InvalidCredentialsError,
    SessionExpiredError,
)

logger = logging.getLogger(__name__)


class AdminLoginWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminAuthService,
        credentials: AdminCredentials,
    ) -> None:
        super().__init__()
        self._service = service
        self._credentials: AdminCredentials | None = credentials

    def run(self) -> None:
        try:
            credentials = self._credentials
            if credentials is None:
                return
            result = self._service.authenticate(credentials)
            if not self.isInterruptionRequested():
                self.succeeded.emit(result)
        except InvalidCredentialsError:
            self._emit_failure("Usuário ou senha inválidos.", False)
        except (ApiUnavailableError, InvalidApiResponseError):
            self._emit_failure(
                "Não foi possível acessar a API. Verifique a conexão e tente novamente.",
                True,
            )
        except AdminServiceError:
            self._emit_failure("Não foi possível concluir o login.", True)
        except Exception as error:
            logger.error(
                "Falha inesperada no worker de login",
                extra={"error_type": type(error).__name__},
            )
            self._emit_failure("Não foi possível concluir o login.", True)
        finally:
            self._credentials = None

    def _emit_failure(self, message: str, retryable: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, retryable)


class DashboardSummaryWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminDashboardService,
        session: AdminSession,
    ) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            summary = self._service.get_summary(session.access_token)
            if not self.isInterruptionRequested():
                self.succeeded.emit(summary)
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except (ApiUnavailableError, InvalidApiResponseError):
            self._emit_failure(
                "Dashboard indisponível. Verifique a conexão e tente novamente.",
                False,
            )
        except AdminServiceError:
            self._emit_failure("Não foi possível atualizar o dashboard.", False)
        except Exception as error:
            logger.error(
                "Falha inesperada no worker do dashboard",
                extra={"error_type": type(error).__name__},
            )
            self._emit_failure("Não foi possível atualizar o dashboard.", False)
        finally:
            self._session = None

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class AdminSessionValidationWorker(QThread):
    """Revalida em background um bearer rejeitado no handshake WebSocket."""

    succeeded = Signal()
    failed = Signal(str, bool)

    def __init__(self, service: AdminAuthService, session: AdminSession) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            self._service.revalidate(session)
            if not self.isInterruptionRequested():
                self.succeeded.emit()
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except (ApiUnavailableError, InvalidApiResponseError):
            self._emit_failure(
                "Não foi possível revalidar a sessão agora. Tentaremos novamente.",
                False,
            )
        except AdminServiceError:
            self._emit_failure(
                "Não foi possível revalidar a sessão agora. Tentaremos novamente.",
                False,
            )
        except Exception as error:
            logger.error(
                "Falha inesperada na revalidação administrativa",
                extra={"error_type": type(error).__name__},
            )
            self._emit_failure(
                "Não foi possível revalidar a sessão agora. Tentaremos novamente.",
                False,
            )
        finally:
            self._session = None

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)
