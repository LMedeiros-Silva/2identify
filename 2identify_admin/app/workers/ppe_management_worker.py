"""Load the PPE snapshot without blocking the Qt event loop."""

import logging

from PySide6.QtCore import QThread, Signal

from app.core.session import AdminSession
from app.services.admin_ppe_management_service import AdminPpeManagementService
from app.services.errors import AdminServiceError, SessionExpiredError

logger = logging.getLogger(__name__)


class PpeManagementWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, service: AdminPpeManagementService, session: AdminSession) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            snapshot = self._service.load(session.access_token)
            if not self.isInterruptionRequested():
                self.succeeded.emit(snapshot)
        except SessionExpiredError:
            self._fail("Sua sessão expirou. Entre novamente.", True)
        except AdminServiceError:
            self._fail("Não foi possível carregar as operações ativas. Tente atualizar.", False)
        except Exception as error:
            logger.error("Falha ao carregar EPIs", extra={"error_type": type(error).__name__})
            self._fail("Não foi possível carregar as operações ativas.", False)
        finally:
            self._session = None

    def _fail(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)
