"""Fetch a selected operation's cameras without blocking the Qt event loop."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.services.operation_service import OperationService, OperationServiceError


class CameraCatalogLoadWorker(QThread):
    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, service: OperationService, operation_id: int) -> None:
        super().__init__()
        self._service = service
        self._operation_id = operation_id

    def run(self) -> None:
        try:
            cameras = self._service.list_cameras_for_operation(self._operation_id)
        except OperationServiceError:
            self.failed.emit(self._operation_id, "Não foi possível carregar câmeras do setor.")
        else:
            self.loaded.emit(self._operation_id, cameras)
