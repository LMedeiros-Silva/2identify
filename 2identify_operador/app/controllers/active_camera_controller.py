"""Camera lifecycle controller for an active WorkSession."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.core.config import AppSettings
from app.ui.active import ActiveOperationPage
from app.vision.camera import OpenCVCameraSession
from app.workers.safety_camera_worker import SafetyCameraWorker

logger = logging.getLogger(__name__)

ActiveCameraWorkerFactory = Callable[[], SafetyCameraWorker]


class ActiveCameraController(QObject):
    """Capture continuous operational frames without blocking the UI thread."""

    analysis_frame_ready = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: ActiveOperationPage,
        worker_factory: ActiveCameraWorkerFactory | None = None,
    ) -> None:
        super().__init__(page)
        self._page = page
        self._worker_factory = worker_factory or partial(
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
            analysis_fps=settings.ppe_inference_fps,
        )
        self._worker: SafetyCameraWorker | None = None
        self._automatic_retries_remaining = 3
        self._restart_after_finish = False
        page.monitoring_start_requested.connect(self.start)
        page.monitoring_stop_requested.connect(self.stop)

    @property
    def is_running(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @Slot()
    def start(self) -> None:
        if not self._page.is_monitoring_active:
            return
        worker = self._worker
        if worker is not None and worker.isRunning():
            if worker.isInterruptionRequested():
                self._restart_after_finish = True
            return
        self._dispose_finished_worker()
        worker = self._worker_factory()
        worker.camera_ready.connect(self._handle_camera_ready)
        worker.frame_ready.connect(self._page.update_monitoring_frame)
        worker.analysis_frame_ready.connect(self.analysis_frame_ready.emit)
        worker.camera_failed.connect(self._handle_camera_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("active_monitoring_camera_started")
        worker.start()

    @Slot()
    def stop(self) -> None:
        self._restart_after_finish = False
        self._automatic_retries_remaining = 3
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 5_000) -> None:
        self._restart_after_finish = False
        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("active_monitoring_camera_shutdown_timeout")
            return
        self._dispose_finished_worker()

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("active_monitoring_camera_finished")
        self._dispose_finished_worker()
        if self._restart_after_finish and self._page.is_monitoring_active:
            self._restart_after_finish = False
            QTimer.singleShot(300, self.start)

    @Slot()
    def _handle_camera_ready(self) -> None:
        self._automatic_retries_remaining = 3
        self._page.show_monitoring_camera_ready()

    @Slot(str, bool)
    def _handle_camera_failure(self, message: str, unavailable: bool) -> None:
        self._page.show_monitoring_camera_failure(message, unavailable)
        if unavailable and self._automatic_retries_remaining > 0:
            self._automatic_retries_remaining -= 1
            self._restart_after_finish = True

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
