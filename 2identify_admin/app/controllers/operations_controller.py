"""Coordinate operation CRUD, camera capture and normalized risk-area editing."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog

from app.core.session import AdminSessionContext
from app.domain import (
    CameraDraft,
    CameraOption,
    ManagedCamera,
    OperationCatalog,
    OperationConfiguration,
    OperationDraft,
    RiskArea,
    RiskAreaDraft,
)
from app.services.admin_operations_service import AdminOperationsService
from app.ui.operations import OperationsPage, RiskAreaEditorDialog
from app.workers import (
    AdminOperationsLoadWorker,
    CameraFrameWorker,
    CameraSaveWorker,
    OperationSaveWorker,
    RiskAreaSaveWorker,
)


class OperationsController(QObject):
    session_expired = Signal(str)
    shutdown_complete = Signal()

    def __init__(
        self,
        view: OperationsPage,
        service: AdminOperationsService,
        session_context: AdminSessionContext,
        *,
        shutdown_timeout_ms: int,
    ) -> None:
        super().__init__()
        self._view = view
        self._service = service
        self._session_context = session_context
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._load_worker: AdminOperationsLoadWorker | None = None
        self._camera_worker: CameraFrameWorker | None = None
        self._save_worker: CameraSaveWorker | RiskAreaSaveWorker | OperationSaveWorker | None = None
        self._pending_camera: CameraOption | None = None
        self._pending_area: RiskArea | None = None
        self._shutdown_requested = False
        self._refresh_after_save = False
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(0)
        self._load_timer.timeout.connect(self.request_refresh)
        view.refresh_requested.connect(self.request_refresh)
        view.camera_save_requested.connect(self.save_camera)
        view.camera_update_requested.connect(self.update_camera)
        view.risk_area_configuration_requested.connect(self.configure_risk_area)
        view.operation_save_requested.connect(self.save_operation)

    def start(self) -> None:
        self._load_timer.start()

    @Slot()
    def request_refresh(self) -> None:
        if (
            self._shutdown_requested
            or self._load_worker is not None
            or self._save_worker is not None
        ):
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_loading()
        worker = AdminOperationsLoadWorker(self._service, session)
        self._load_worker = worker
        worker.succeeded.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._load_finished)
        worker.start()

    @Slot(object, object)
    def configure_risk_area(self, camera_value: object, area_value: object) -> None:
        if self._shutdown_requested or self._camera_worker is not None:
            return
        if not isinstance(camera_value, CameraOption):
            self._view.show_error("A câmera selecionada é inválida.")
            return
        area = area_value if isinstance(area_value, RiskArea) else None
        self._pending_camera = camera_value
        self._pending_area = area
        self._view.show_loading("Abrindo uma imagem atual da câmera...")
        worker = CameraFrameWorker(camera_value.stream_source, camera_id=camera_value.id)
        self._camera_worker = worker
        worker.succeeded.connect(self._camera_loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._camera_finished)
        worker.start()

    @Slot(object)
    def save_camera(self, draft_value: object) -> None:
        self._start_camera_save(draft_value, None)

    @Slot(object, int)
    def update_camera(self, draft_value: object, camera_id: int) -> None:
        self._start_camera_save(draft_value, camera_id)

    def _start_camera_save(self, draft_value: object, camera_id: int | None) -> None:
        if self._shutdown_requested or self._save_worker is not None:
            return
        if not isinstance(draft_value, CameraDraft):
            self._view.show_error("Os dados da câmera são inválidos.")
            return
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_loading("Salvando câmera pela API...")
        worker = CameraSaveWorker(self._service, session, draft_value, camera_id)
        self._save_worker = worker
        worker.succeeded.connect(self._camera_saved)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._save_finished)
        worker.start()

    @Slot(object, object)
    def save_operation(self, draft_value: object, operation_id_value: object) -> None:
        if self._shutdown_requested or self._save_worker is not None:
            return
        if not isinstance(draft_value, OperationDraft):
            self._view.show_error("Os dados da operação são inválidos.")
            return
        operation_id = operation_id_value if isinstance(operation_id_value, int) else None
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_loading("Salvando operação pela API...")
        worker = OperationSaveWorker(self._service, session, draft_value, operation_id)
        self._save_worker = worker
        worker.succeeded.connect(self._operation_saved)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._save_finished)
        worker.start()

    @Slot(object)
    def _loaded(self, value: object) -> None:
        if not isinstance(value, tuple) or len(value) != 4:
            self._view.show_error("A API retornou configurações inválidas.")
            return
        catalog, areas, operations, cameras = value
        if (
            not isinstance(catalog, OperationCatalog)
            or not isinstance(areas, tuple)
            or not isinstance(operations, tuple)
            or not isinstance(cameras, tuple)
            or not all(isinstance(area, RiskArea) for area in areas)
            or not all(isinstance(item, OperationConfiguration) for item in operations)
            or not all(isinstance(item, ManagedCamera) for item in cameras)
        ):
            self._view.show_error("A API retornou configurações inválidas.")
            return
        self._view.set_data(catalog, areas, operations, cameras)

    @Slot(object)
    def _camera_loaded(self, value: object) -> None:
        camera = self._pending_camera
        if camera is None or not isinstance(value, QImage) or value.isNull():
            self._view.show_error("A câmera não retornou uma imagem válida.")
            return
        dialog = RiskAreaEditorDialog(camera, value, self._pending_area, self._view)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_draft is not None:
            self._start_area_save(dialog.result_draft, self._pending_area)
        else:
            self._view.show_ready()

    def _start_area_save(self, draft: RiskAreaDraft, existing: RiskArea | None) -> None:
        session = self._session_context.current()
        if session is None:
            self.session_expired.emit("Sua sessão expirou. Entre novamente.")
            return
        self._view.show_loading("Salvando área de risco pela API...")
        worker = RiskAreaSaveWorker(
            self._service, session, draft, existing.id if existing else None
        )
        self._save_worker = worker
        worker.succeeded.connect(self._area_saved)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._save_finished)
        worker.start()

    @Slot(object)
    def _area_saved(self, value: object) -> None:
        if isinstance(value, RiskArea):
            self._view.upsert_risk_area(value)
        else:
            self._view.show_error("A API retornou uma área de risco inválida.")

    @Slot(object)
    def _camera_saved(self, value: object) -> None:
        if isinstance(value, CameraOption):
            self._refresh_after_save = True
        else:
            self._view.show_error("A API retornou uma câmera inválida.")

    @Slot(object)
    def _operation_saved(self, value: object) -> None:
        if isinstance(value, OperationConfiguration):
            self._view.upsert_operation(value)
        else:
            self._view.show_error("A API retornou uma operação inválida.")

    @Slot(str, bool)
    def _failed(self, message: str, expired: bool) -> None:
        if expired:
            self.session_expired.emit(message)
        else:
            self._view.show_error(message)

    @Slot()
    def _load_finished(self) -> None:
        self._dispose_worker("_load_worker")

    @Slot()
    def _camera_finished(self) -> None:
        self._dispose_worker("_camera_worker")
        self._pending_camera = None
        self._pending_area = None

    @Slot()
    def _save_finished(self) -> None:
        self._dispose_worker("_save_worker")
        if self._refresh_after_save and not self._shutdown_requested:
            self._refresh_after_save = False
            self.request_refresh()

    def _dispose_worker(self, attribute: str) -> None:
        worker = getattr(self, attribute)
        setattr(self, attribute, None)
        if worker is not None:
            worker.deleteLater()
        if self._shutdown_requested and not self._running_workers():
            self._shutdown_requested = False
            self.shutdown_complete.emit()

    def _running_workers(self) -> tuple[QThread, ...]:
        return tuple(
            worker
            for worker in (self._load_worker, self._camera_worker, self._save_worker)
            if worker is not None and worker.isRunning()
        )

    def shutdown(self) -> bool:
        self._load_timer.stop()
        workers = self._running_workers()
        if not workers:
            return True
        self._shutdown_requested = True
        for worker in workers:
            worker.requestInterruption()
        return all(worker.wait(self._shutdown_timeout_ms) for worker in workers)


__all__ = ["OperationsController"]
