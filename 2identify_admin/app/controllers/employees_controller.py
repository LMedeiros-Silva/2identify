"""Coordinate the Admin employee screen and API workers."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.core.session import AdminSession, AdminSessionContext
from app.domain.employees import EmployeeDraft, EmployeeRecord, FaceTemplateDraft
from app.services.admin_employees_service import AdminEmployeesService
from app.services.errors import AdminServiceError, ConfigurationConflictError, SessionExpiredError
from app.ui.employees import EmployeesPage

logger = logging.getLogger(__name__)


class EmployeeLoadWorker(QThread):
    succeeded = Signal(object, object)
    failed = Signal(str, bool)

    def __init__(self, service: AdminEmployeesService, session: AdminSession) -> None:
        super().__init__()
        self._service = service
        self._session = session

    def run(self) -> None:
        try:
            if self._session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            records, sectors = self._service.load(self._session.access_token)
            if not self.isInterruptionRequested():
                self.succeeded.emit(records, sectors)
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except AdminServiceError:
            self._emit_failure("Não foi possível carregar os funcionários.", False)
        except Exception as error:
            logger.error("employee_load_failed", extra={"error_type": type(error).__name__})
            self._emit_failure("Não foi possível carregar os funcionários.", False)

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class EmployeeSaveWorker(QThread):
    employee_saved = Signal(object)
    face_saved = Signal()
    failed = Signal(str, bool)

    def __init__(
        self,
        service: AdminEmployeesService,
        session: AdminSession,
        draft: EmployeeDraft,
        employee_id: int | None,
        face: FaceTemplateDraft | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._session = session
        self._draft = draft
        self._employee_id = employee_id
        self._face = face

    def run(self) -> None:
        try:
            if self._session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            employee = self._service.save_employee(
                self._session.access_token, self._draft, self._employee_id
            )
            if self.isInterruptionRequested():
                return
            self.employee_saved.emit(employee)
            if self._face is not None:
                self._service.save_face_template(
                    self._session.access_token, employee.id, self._face
                )
                if not self.isInterruptionRequested():
                    self.face_saved.emit()
        except SessionExpiredError:
            self._emit_failure("Sua sessão expirou. Entre novamente.", True)
        except ConfigurationConflictError as error:
            self._emit_failure(str(error), False)
        except AdminServiceError:
            self._emit_failure("Falha ao salvar funcionário ou Face ID pela API.", False)
        except Exception as error:
            logger.error("employee_save_failed", extra={"error_type": type(error).__name__})
            self._emit_failure("Falha ao salvar funcionário ou Face ID pela API.", False)

    def _emit_failure(self, message: str, expired: bool) -> None:
        if not self.isInterruptionRequested():
            self.failed.emit(message, expired)


class EmployeesController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        page: EmployeesPage,
        service: AdminEmployeesService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._page = page
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._worker: EmployeeLoadWorker | EmployeeSaveWorker | None = None
        self._shutdown_requested = False
        self._refresh_pending = False
        page.refresh_requested.connect(self.refresh)
        page.save_requested.connect(self.save)

    def start(self) -> None:
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        if self._shutdown_requested:
            return
        if self._worker is not None:
            self._refresh_pending = True
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._page.show_loading()
        worker = EmployeeLoadWorker(self._service, session)
        self._worker = worker
        worker.succeeded.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        worker.start()

    @Slot(object, object, object)
    def save(self, draft: object, employee_id: object, face: object) -> None:
        if self._shutdown_requested or self._worker is not None:
            return
        if (
            not isinstance(draft, EmployeeDraft)
            or (employee_id is not None and not isinstance(employee_id, int))
            or (face is not None and not isinstance(face, FaceTemplateDraft))
        ):
            self._page.show_error("Cadastro ou Face ID inválido.")
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._page.show_loading("Salvando funcionário pela API...")
        worker = EmployeeSaveWorker(self._service, session, draft, employee_id, face)
        self._worker = worker
        worker.employee_saved.connect(self._employee_saved)
        worker.face_saved.connect(self._page.face_saved)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        worker.start()

    @Slot(object, object)
    def _loaded(self, records: object, sectors: object) -> None:
        if isinstance(records, tuple) and isinstance(sectors, tuple):
            self._page.set_data(records, sectors)

    @Slot(object)
    def _employee_saved(self, value: object) -> None:
        if isinstance(value, EmployeeRecord):
            self._page.employee_saved(value)

    @Slot(str, bool)
    def _failed(self, message: str, expired: bool) -> None:
        if expired:
            self.session_expired.emit(message)
        else:
            self._page.show_error(message)

    @Slot()
    def _finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._shutdown_requested:
            self._shutdown_requested = False
            self.shutdown_complete.emit()
        elif self._refresh_pending:
            self._refresh_pending = False
            self.refresh()

    def shutdown(self) -> bool:
        worker = self._worker
        self._refresh_pending = False
        if worker is None or not worker.isRunning():
            return True
        self._shutdown_requested = True
        worker.requestInterruption()
        return worker.wait(self._shutdown_timeout_ms)


__all__ = ["EmployeesController"]
