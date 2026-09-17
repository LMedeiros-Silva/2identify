"""Dedicated camera-preview thread for pre-operation safety verification."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.domain.camera_source import CameraFrame
from app.vision.camera import CameraSession
from app.vision.qt_image import frame_to_qimage

logger = logging.getLogger(__name__)


class SafetyCameraWorker(QThread):
    """Capture preview frames without touching widgets or running PPE inference."""

    camera_ready = Signal()
    frame_ready = Signal(QImage)
    analysis_frame_ready = Signal(object)
    camera_failed = Signal(str, bool)
    identified_frame_ready = Signal(object)
    identified_preview_ready = Signal(int, int, QImage)
    identified_ready = Signal(int, int)
    identified_failed = Signal(int, int)

    def __init__(
        self,
        camera_factory: Callable[[], CameraSession],
        preview_fps: float,
        maximum_failed_reads: int,
        analysis_fps: float | None = None,
        camera_id: int | None = None,
        generation: int = 0,
    ) -> None:
        super().__init__()
        self.setObjectName("SafetyCameraWorker")
        self._camera_factory = camera_factory
        self._preview_interval = 1.0 / preview_fps
        self._analysis_interval = None if analysis_fps is None else 1.0 / analysis_fps
        self._maximum_failed_reads = maximum_failed_reads
        self._stop_requested = threading.Event()
        self._camera_id = camera_id
        self._generation = generation

    def request_stop(self) -> None:
        """Request cooperative shutdown from any thread."""

        self._stop_requested.set()
        self.requestInterruption()

    def run(self) -> None:
        camera: CameraSession | None = None
        try:
            if self._should_stop():
                return
            camera = self._camera_factory()
            if not camera.open():
                if self._camera_id is not None:
                    self.identified_failed.emit(self._camera_id, self._generation)
                self.camera_failed.emit(
                    "Não foi possível abrir a câmera de verificação.",
                    True,
                )
                return

            logger.info("safety_camera_connected")
            self.camera_ready.emit()
            if self._camera_id is not None:
                self.identified_ready.emit(self._camera_id, self._generation)
            next_preview_at = monotonic()
            next_analysis_at = next_preview_at
            failed_reads = 0

            while not self._should_stop():
                success, frame = camera.read()
                if not success or frame is None:
                    failed_reads += 1
                    if failed_reads >= self._maximum_failed_reads:
                        if self._camera_id is not None:
                            self.identified_failed.emit(self._camera_id, self._generation)
                        self.camera_failed.emit(
                            "A câmera de verificação parou de fornecer imagens.",
                            True,
                        )
                        return
                    self.msleep(10)
                    continue

                failed_reads = 0
                now = monotonic()
                if now >= next_preview_at:
                    image = frame_to_qimage(frame)
                    if self._camera_id is not None:
                        self.identified_preview_ready.emit(self._camera_id, self._generation, image)
                    else:
                        self.frame_ready.emit(image)
                    next_preview_at = now + self._preview_interval
                if (
                    self._analysis_interval is not None
                    and now >= next_analysis_at
                ):
                    owned = frame.copy()
                    if self._camera_id is not None:
                        self.identified_frame_ready.emit(
                            CameraFrame(self._camera_id, self._generation, datetime.now(UTC), owned)
                        )
                    else:
                        self.analysis_frame_ready.emit(owned)
                    next_analysis_at = now + self._analysis_interval
                self.msleep(1)
        except Exception as error:
            logger.error(
                "safety_camera_worker_failed",
                extra={"error_type": type(error).__name__, "camera_id": self._camera_id},
            )
            if self._camera_id is not None:
                self.identified_failed.emit(self._camera_id, self._generation)
            self.camera_failed.emit(
                "Falha inesperada durante a captura da câmera.",
                False,
            )
        finally:
            if camera is not None:
                camera.close()
                logger.info("safety_camera_released")

    def _should_stop(self) -> bool:
        return self._stop_requested.is_set() or self.isInterruptionRequested()
