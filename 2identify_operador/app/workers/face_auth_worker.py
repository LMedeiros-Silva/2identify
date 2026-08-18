"""Dedicated QThread for blocking camera capture and facial inference."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from time import monotonic

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.vision.camera import CameraSession
from app.vision.face_auth.errors import FaceAuthenticationError
from app.vision.face_auth.pipeline import FaceAuthenticationPipeline
from app.vision.face_auth.types import FacePipelineDecision
from app.vision.qt_image import frame_to_qimage

logger = logging.getLogger(__name__)


class FaceAuthenticationWorker(QThread):
    """Capture and infer without ever accessing a widget from the worker thread."""

    frame_ready = Signal(QImage)
    pipeline_status_changed = Signal(str, str)
    operator_recognized = Signal(object)
    authentication_failed = Signal(str, bool)

    def __init__(
        self,
        camera_factory: Callable[[], CameraSession],
        pipeline_factory: Callable[[], FaceAuthenticationPipeline],
        timeout_seconds: float,
        inference_fps: float,
        preview_fps: float,
        maximum_failed_reads: int,
    ) -> None:
        super().__init__()
        self.setObjectName("FaceAuthenticationWorker")
        self._camera_factory = camera_factory
        self._pipeline_factory = pipeline_factory
        self._timeout_seconds = timeout_seconds
        self._inference_interval = 1.0 / inference_fps
        self._preview_interval = 1.0 / preview_fps
        self._maximum_failed_reads = maximum_failed_reads
        self._stop_requested = threading.Event()
        self._last_status: tuple[str, str] | None = None

    def request_stop(self) -> None:
        """Thread-safe cooperative cancellation callable from the UI thread."""

        self._stop_requested.set()
        self.requestInterruption()

    def run(self) -> None:
        camera: CameraSession | None = None
        try:
            pipeline = self._pipeline_factory()
            if self._stop_requested.is_set():
                return

            camera = self._camera_factory()
            if not camera.open():
                self.authentication_failed.emit(
                    "Não foi possível abrir a câmera de autenticação.",
                    True,
                )
                return

            logger.info("face_auth_camera_connected")
            started_at = monotonic()
            next_preview_at = started_at
            next_inference_at = started_at
            failed_reads = 0

            while not self._should_stop():
                now = monotonic()
                if now - started_at >= self._timeout_seconds:
                    self.authentication_failed.emit(
                        "Tempo de reconhecimento esgotado. Tente novamente.",
                        False,
                    )
                    return

                success, frame = camera.read()
                if not success or frame is None:
                    failed_reads += 1
                    if failed_reads >= self._maximum_failed_reads:
                        self.authentication_failed.emit(
                            "A câmera parou de fornecer imagens.",
                            True,
                        )
                        return
                    self.msleep(10)
                    continue

                failed_reads = 0
                now = monotonic()
                if now >= next_preview_at:
                    self.frame_ready.emit(frame_to_qimage(frame))
                    next_preview_at = now + self._preview_interval

                if now >= next_inference_at:
                    decision = pipeline.process(frame, now)
                    self._emit_decision(decision)
                    next_inference_at = now + self._inference_interval
                    if decision.identity is not None:
                        self.operator_recognized.emit(decision.identity)
                        return

                self.msleep(1)
        except FaceAuthenticationError as error:
            logger.warning("face_auth_unavailable", extra={"reason": str(error)})
            self.authentication_failed.emit(str(error), True)
        except Exception:
            logger.exception("face_auth_worker_failed")
            self.authentication_failed.emit(
                "Falha inesperada durante o reconhecimento facial.",
                False,
            )
        finally:
            if camera is not None:
                camera.close()
                logger.info("face_auth_camera_released")

    def _should_stop(self) -> bool:
        return self._stop_requested.is_set() or self.isInterruptionRequested()

    def _emit_decision(self, decision: FacePipelineDecision) -> None:
        status = (decision.status.value, decision.message)
        if status == self._last_status:
            return
        self._last_status = status
        self.pipeline_status_changed.emit(*status)

