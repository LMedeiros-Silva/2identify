"""Run authenticated XLSX export off the Qt UI thread."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from app.core.session import AdminSession, AdminSessionContext
from app.services.admin_reports_service import AdminReportsService, ReportFilters
from app.services.errors import AdminServiceError, SessionExpiredError
from app.ui.reports import ReportsPage

logger = logging.getLogger(__name__)


class ReportExportWorker(QThread):
    succeeded = Signal(bytes)
    failed = Signal(str, bool)

    def __init__(
        self, service: AdminReportsService, session: AdminSession, filters: ReportFilters
    ) -> None:
        super().__init__()
        self._service = service
        self._session = session
        self._filters = filters

    def run(self) -> None:
        try:
            if self._session.is_expired():
                raise SessionExpiredError("Sua sessão expirou.")
            content = self._service.export_xlsx(self._session.access_token, self._filters)
            if not self.isInterruptionRequested():
                self.succeeded.emit(content)
        except SessionExpiredError:
            if not self.isInterruptionRequested():
                self.failed.emit("Sua sessão expirou. Entre novamente.", True)
        except AdminServiceError:
            if not self.isInterruptionRequested():
                self.failed.emit("Não foi possível carregar os dados do relatório.", False)
        except Exception as error:
            logger.error("report_export_failed", extra={"error_type": type(error).__name__})
            if not self.isInterruptionRequested():
                self.failed.emit("Não foi possível gerar o relatório.", False)


class ReportsController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        page: ReportsPage,
        service: AdminReportsService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._page = page
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._worker: ReportExportWorker | None = None
        self._shutdown_requested = False
        page.export_requested.connect(self.export)

    @Slot(object)
    def export(self, value: object) -> None:
        if self._shutdown_requested or self._worker is not None:
            return
        if not isinstance(value, ReportFilters):
            self._page.show_error("Filtros de relatório inválidos.")
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._page.show_loading()
        worker = ReportExportWorker(self._service, session, value)
        self._worker = worker
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_finished)
        worker.start()

    @Slot(bytes)
    def _on_success(self, content: bytes) -> None:
        if self._shutdown_requested:
            return
        suggested = f"2identify-relatorio-{date.today().isoformat()}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self._page, "Salvar relatório Excel", suggested, "Planilha Excel (*.xlsx)"
        )
        if not path:
            self._page.show_cancelled()
            return
        target = Path(path)
        if target.suffix.casefold() != ".xlsx":
            target = target.with_suffix(".xlsx")
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                prefix=".2identify-report-", suffix=".tmp", dir=target.parent,
                delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(content)
            os.replace(temporary, target)
        except OSError as error:
            logger.error("report_save_failed", extra={"error_type": type(error).__name__})
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self._page.show_error("Não foi possível salvar o arquivo Excel.")
            return
        self._page.show_success(str(target))

    @Slot(str, bool)
    def _on_failure(self, message: str, expired: bool) -> None:
        if expired:
            self.session_expired.emit(message)
        else:
            self._page.show_error(message)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._shutdown_requested:
            self._shutdown_requested = False
            self.shutdown_complete.emit()

    def shutdown(self) -> bool:
        worker = self._worker
        if worker is None or not worker.isRunning():
            return True
        self._shutdown_requested = True
        worker.requestInterruption()
        return worker.wait(self._shutdown_timeout_ms)


__all__ = ["ReportsController"]
