"""QThread boundary for blocking operation-catalog retrieval."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.services.operation_service import OperationService, OperationServiceError

logger = logging.getLogger(__name__)


class OperationLoadWorker(QThread):
    """Fetch operations outside the Qt UI thread."""

    operations_loaded = Signal(object)
    load_failed = Signal(str)

    def __init__(self, service: OperationService) -> None:
        super().__init__()
        self.setObjectName("OperationLoadWorker")
        self._service = service

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            operations = self._service.list_available_operations()
        except OperationServiceError as error:
            if not self.isInterruptionRequested():
                self.load_failed.emit(str(error))
        except Exception:
            logger.exception("operation_load_worker_failed")
            if not self.isInterruptionRequested():
                self.load_failed.emit(
                    "Não foi possível consultar as operações. Tente novamente mais tarde."
                )
        else:
            if not self.isInterruptionRequested():
                self.operations_loaded.emit(operations)
