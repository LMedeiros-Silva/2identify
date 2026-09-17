"""One-shot camera capture for the operator risk-area preview."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QImage

from app.core.config import AppSettings
from app.domain.camera_source import CameraType, local_camera_source, parse_source_value
from app.domain.operation import RiskAreaReference
from app.ui.operations import OperationsPage
from app.vision.camera import OpenCVCameraSession
from app.workers.safety_camera_worker import SafetyCameraWorker

logger = logging.getLogger(__name__)

RiskAreaSnapshotWorkerFactory = Callable[[], SafetyCameraWorker]


class RiskAreaSnapshotController(QObject):
    """Capture one owned frame and immediately release the operational camera."""

    def __init__(
        self,
        settings: AppSettings,
        page: OperationsPage,
        worker_factory: RiskAreaSnapshotWorkerFactory | None = None,
    ) -> None:
        super().__init__(page)
        self._page = page
        self._settings = settings
        self._worker_factory = worker_factory
        self._legacy_worker_factory = partial(
            SafetyCameraWorker,
            camera_factory=partial(
                OpenCVCameraSession,
                source=settings.parsed_camera_source,
                width=settings.camera_width,
                height=settings.camera_height,
                open_timeout_ms=settings.camera_open_timeout_ms,
                read_timeout_ms=settings.camera_read_timeout_ms,
            ),
            preview_fps=settings.camera_preview_fps,
            maximum_failed_reads=settings.camera_max_failed_reads,
        )
        self._worker: SafetyCameraWorker | None = None
        self._active_risk_area_id: int | None = None
        self._pending_risk_area: RiskAreaReference | None = None
        self._frame_delivered = False

    @property
    def is_running(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @Slot(object)
    def capture(self, value: object) -> None:
        """Start or replace a pending snapshot request for a validated area."""

        if not isinstance(value, RiskAreaReference) or value.geometry is None:
            logger.warning("risk_area_snapshot_request_ignored_invalid_area")
            return

        self._page.show_risk_area_snapshot_loading(value.risk_area_id)
        worker = self._worker
        if worker is not None and worker.isRunning():
            if self._active_risk_area_id == value.risk_area_id:
                return
            self._pending_risk_area = value
            worker.request_stop()
            return

        self._dispose_finished_worker()
        self._start_capture(value)

    def shutdown(self, wait_timeout_ms: int = 5_000) -> None:
        """Cancel pending work and release the camera before application teardown."""

        self._pending_risk_area = None
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("risk_area_snapshot_worker_shutdown_timeout")
            return
        self._dispose_finished_worker()

    def _start_capture(self, risk_area: RiskAreaReference) -> None:
        try:
            worker = (
                self._worker_factory() if self._worker_factory is not None
                else self._new_worker(risk_area)
            )
        except ValueError:
            self._page.show_risk_area_snapshot_failure(
                risk_area.risk_area_id,
                "Fonte local da câmera desta área não configurada.",
            )
            return
        risk_area_id = risk_area.risk_area_id
        worker.frame_ready.connect(partial(self._handle_frame, worker, risk_area_id))
        worker.camera_failed.connect(partial(self._handle_failure, worker, risk_area_id))
        worker.finished.connect(partial(self._handle_finished, worker))
        self._worker = worker
        self._active_risk_area_id = risk_area_id
        self._frame_delivered = False
        logger.info(
            "risk_area_snapshot_capture_started",
            extra={"risk_area_id": risk_area_id},
        )
        worker.start()

    def _new_worker(self, risk_area: RiskAreaReference) -> SafetyCameraWorker:
        if risk_area.camera_id is None:
            return self._legacy_worker_factory()
        value = local_camera_source(risk_area.camera_id)
        if value is None:
            raise ValueError("fonte de câmera ausente")
        source_type = CameraType.USB if value.strip().isdecimal() else CameraType.IP
        source = parse_source_value(source_type, value)
        settings = self._settings
        return SafetyCameraWorker(
            camera_factory=partial(
                OpenCVCameraSession,
                source=source,
                width=settings.camera_width,
                height=settings.camera_height,
                open_timeout_ms=settings.camera_open_timeout_ms,
                read_timeout_ms=settings.camera_read_timeout_ms,
            ),
            preview_fps=settings.camera_preview_fps,
            maximum_failed_reads=settings.camera_max_failed_reads,
        )

    def _handle_frame(
        self,
        worker: SafetyCameraWorker,
        risk_area_id: int,
        frame: QImage,
    ) -> None:
        if (
            worker is not self._worker
            or risk_area_id != self._active_risk_area_id
            or self._frame_delivered
        ):
            return
        self._frame_delivered = True
        self._page.show_risk_area_snapshot(risk_area_id, frame)
        worker.request_stop()
        logger.info(
            "risk_area_snapshot_captured",
            extra={"risk_area_id": risk_area_id},
        )

    def _handle_failure(
        self,
        worker: SafetyCameraWorker,
        risk_area_id: int,
        message: str,
        unavailable: bool,
    ) -> None:
        del message
        if (
            worker is not self._worker
            or risk_area_id != self._active_risk_area_id
            or self._frame_delivered
        ):
            return
        self._frame_delivered = True
        detail = (
            "Não foi possível acessar a câmera operacional."
            if unavailable
            else "A captura da câmera operacional falhou."
        )
        self._page.show_risk_area_snapshot_failure(risk_area_id, detail)
        logger.warning(
            "risk_area_snapshot_capture_failed",
            extra={"risk_area_id": risk_area_id},
        )

    def _handle_finished(self, worker: SafetyCameraWorker) -> None:
        if worker is not self._worker:
            worker.deleteLater()
            return
        worker.deleteLater()
        self._worker = None
        self._active_risk_area_id = None
        self._frame_delivered = False
        pending = self._pending_risk_area
        self._pending_risk_area = None
        if pending is not None:
            self._start_capture(pending)

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
        self._active_risk_area_id = None
        self._frame_delivered = False


__all__ = ["RiskAreaSnapshotController", "RiskAreaSnapshotWorkerFactory"]
