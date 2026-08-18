"""Lifecycle controller for the pre-operation camera preview."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, Signal, Slot

from app.core.config import AppSettings
from app.ui.safety import SafetyVerificationPage
from app.vision.camera import OpenCVCameraSession
from app.workers.safety_camera_worker import SafetyCameraWorker

logger = logging.getLogger(__name__)

SafetyCameraWorkerFactory = Callable[[], SafetyCameraWorker]


class SafetyCameraController(QObject):
    """Own one operational preview worker and guarantee cooperative shutdown."""

    analysis_frame_ready = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        page: SafetyVerificationPage,
        worker_factory: SafetyCameraWorkerFactory | None = None,
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
        page.camera_start_requested.connect(self.start)
        page.camera_stop_requested.connect(self.stop)

    @property
    def is_running(self) -> bool:
        worker = self._worker
        return worker is not None and worker.isRunning()

    @Slot()
    def start(self) -> None:
        """Start a new preview attempt unless one is still active."""

        worker = self._worker
        if worker is not None and worker.isRunning():
            self._page.show_camera_failure(
                "A captura anterior ainda está sendo finalizada. Tente novamente em instantes.",
                False,
            )
            return

        self._dispose_finished_worker()
        worker = self._worker_factory()
        worker.camera_ready.connect(self._page.show_camera_ready)
        worker.frame_ready.connect(self._page.update_camera_frame)
        worker.analysis_frame_ready.connect(self.analysis_frame_ready.emit)
        worker.camera_failed.connect(self._page.show_camera_failure)
        worker.finished.connect(self._handle_finished)
        self._worker = worker
        logger.info("safety_camera_attempt_started")
        worker.start()

    @Slot()
    def stop(self) -> None:
        """Request non-blocking camera shutdown when leaving the safety route."""

        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()

    def shutdown(self, wait_timeout_ms: int = 5_000) -> None:
        """Release the camera before application or authenticated-session teardown."""

        worker = self._worker
        if worker is None:
            return
        worker.request_stop()
        if worker.isRunning() and not worker.wait(wait_timeout_ms):
            logger.error("safety_camera_worker_shutdown_timeout")
            return
        self._dispose_finished_worker()

    @Slot()
    def _handle_finished(self) -> None:
        logger.info("safety_camera_attempt_finished")
        self._dispose_finished_worker()

    def _dispose_finished_worker(self) -> None:
        worker = self._worker
        if worker is None or worker.isRunning():
            return
        worker.deleteLater()
        self._worker = None
