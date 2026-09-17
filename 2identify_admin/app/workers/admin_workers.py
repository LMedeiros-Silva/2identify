from __future__ import annotations

import logging
from typing import Literal

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.core.session import AdminSession
from app.domain import AdminCredentials, CameraDraft, OperationDraft, RiskAreaDraft
from app.services.admin_alerts_service import AdminAlertsService
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.admin_operations_service import AdminOperationsService
from app.services.errors import (
    AdminServiceError,
    AlertNotFoundError,
    AlertStateConflictError,
    ApiUnavailableError,
    ConfigurationConflictError,
    ConfigurationNotFoundError,
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


class AdminAlertsListWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, service: AdminAlertsService, session: AdminSession) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            result = self._service.list_alerts(session.access_token)
            if not self.isInterruptionRequested():
                self.succeeded.emit(result)
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except (ApiUnavailableError, InvalidApiResponseError):
            self._emit_failure(
                "Não foi possível carregar os alertas. Verifique a conexão.",
                False,
            )
        except AdminServiceError:
            self._emit_failure("Não foi possível carregar os alertas.", False)
        except Exception as error:
            logger.error(
                "Falha inesperada ao carregar alertas",
                extra={"error_type": type(error).__name__},
            )
            self._emit_failure("Não foi possível carregar os alertas.", False)
        finally:
            self._session = None

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class AdminAlertActionWorker(QThread):
    succeeded = Signal(object, str)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminAlertsService,
        session: AdminSession,
        alert_id: int,
        action: Literal["confirm", "close"],
    ) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session
        self._alert_id = alert_id
        self._action = action

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            result = (
                self._service.confirm_alert(session.access_token, self._alert_id)
                if self._action == "confirm"
                else self._service.close_alert(session.access_token, self._alert_id)
            )
            if not self.isInterruptionRequested():
                self.succeeded.emit(result, self._action)
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except AlertNotFoundError:
            self._emit_failure("O alerta não foi encontrado. Atualize a lista.", False)
        except AlertStateConflictError:
            self._emit_failure(
                "O alerta mudou de estado. Atualize a lista e tente novamente.",
                False,
            )
        except (ApiUnavailableError, InvalidApiResponseError):
            self._emit_failure("Não foi possível concluir a ação na API.", False)
        except AdminServiceError:
            self._emit_failure("Não foi possível atualizar o alerta.", False)
        except Exception as error:
            logger.error(
                "Falha inesperada ao atualizar alerta",
                extra={"error_type": type(error).__name__},
            )
            self._emit_failure("Não foi possível atualizar o alerta.", False)
        finally:
            self._session = None

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class AdminOperationsLoadWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, service: AdminOperationsService, session: AdminSession) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            value = self._service.load(session.access_token)
            if not self.isInterruptionRequested():
                self.succeeded.emit(value)
        except SessionExpiredError:
            self._fail("Sua sessão expirou. Entre novamente.", True)
        except AdminServiceError:
            self._fail("Não foi possível carregar as operações e catálogos.", False)
        except Exception as error:
            logger.error("Falha ao carregar operações", extra={"error_type": type(error).__name__})
            self._fail("Não foi possível carregar as operações e catálogos.", False)
        finally:
            self._session = None

    def _fail(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class CameraSaveWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminOperationsService,
        session: AdminSession,
        draft: CameraDraft,
        camera_id: int | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session
        self._draft = draft
        self._camera_id = camera_id

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            value = (
                self._service.create_camera(session.access_token, self._draft)
                if self._camera_id is None
                else self._service.save_camera(session.access_token, self._draft, self._camera_id)
            )
            if not self.isInterruptionRequested():
                self.succeeded.emit(value)
        except SessionExpiredError:
            self._fail("Sua sessão expirou. Entre novamente.", True)
        except ConfigurationNotFoundError:
            self._fail("O setor selecionado não existe mais ou está inativo.", False)
        except ConfigurationConflictError as error:
            self._fail(str(error), False)
        except AdminServiceError:
            self._fail("Não foi possível salvar a câmera.", False)
        except Exception as error:
            logger.error(
                "Falha ao salvar câmera",
                extra={"error_type": type(error).__name__},
            )
            self._fail("Não foi possível salvar a câmera.", False)
        finally:
            self._session = None

    def _fail(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class RiskAreaSaveWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminOperationsService,
        session: AdminSession,
        draft: RiskAreaDraft,
        risk_area_id: int | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session
        self._draft = draft
        self._risk_area_id = risk_area_id

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            value = self._service.save_risk_area(
                session.access_token, self._draft, self._risk_area_id
            )
            if not self.isInterruptionRequested():
                self.succeeded.emit(value)
        except SessionExpiredError:
            self._fail("Sua sessão expirou. Entre novamente.", True)
        except ConfigurationNotFoundError:
            self._fail("A câmera ou área selecionada não existe mais.", False)
        except ConfigurationConflictError as error:
            self._fail(str(error), False)
        except AdminServiceError:
            self._fail("Não foi possível salvar a área de risco.", False)
        except Exception as error:
            logger.error("Falha ao salvar área", extra={"error_type": type(error).__name__})
            self._fail("Não foi possível salvar a área de risco.", False)
        finally:
            self._session = None

    def _fail(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class OperationSaveWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminOperationsService,
        session: AdminSession,
        draft: OperationDraft,
        operation_id: int | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._session: AdminSession | None = session
        self._draft = draft
        self._operation_id = operation_id

    def run(self) -> None:
        try:
            session = self._session
            if session is None or session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            value = self._service.save_operation(
                session.access_token, self._draft, self._operation_id
            )
            if not self.isInterruptionRequested():
                self.succeeded.emit(value)
        except SessionExpiredError:
            self._fail("Sua sessão expirou. Entre novamente.", True)
        except ConfigurationNotFoundError:
            self._fail("Um EPI ou área selecionada não existe mais.", False)
        except ConfigurationConflictError as error:
            self._fail(str(error), False)
        except AdminServiceError:
            self._fail("Não foi possível salvar a operação.", False)
        except Exception as error:
            logger.error("Falha ao salvar operação", extra={"error_type": type(error).__name__})
            self._fail("Não foi possível salvar a operação.", False)
        finally:
            self._session = None

    def _fail(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class CameraFrameWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source.strip()

    def run(self) -> None:
        image = QImage(self._source)
        if not image.isNull():
            self.succeeded.emit(image.copy())
            return
        try:
            import cv2

            source: str | int = int(self._source) if self._source.isdecimal() else self._source
            capture = cv2.VideoCapture()
            try:
                if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                    capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                    capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
                opened = capture.open(source)
                ok, frame = capture.read() if opened else (False, None)
            finally:
                capture.release()
            if not ok or frame is None:
                self.failed.emit("A câmera não forneceu uma imagem.", False)
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            result = QImage(
                rgb.data,
                width,
                height,
                channels * width,
                QImage.Format.Format_RGB888,
            ).copy()
            self.succeeded.emit(result)
        except ModuleNotFoundError:
            self.failed.emit(
                "OpenCV não está instalado. Execute a instalação das dependências do Admin.",
                False,
            )
        except Exception as error:
            logger.error("Falha ao abrir câmera", extra={"error_type": type(error).__name__})
            self.failed.emit("Não foi possível abrir a imagem da câmera.", False)
