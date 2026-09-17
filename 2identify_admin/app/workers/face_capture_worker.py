"""Own a webcam and YuNet/SFace enrollment off the Qt main thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock
from time import sleep

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.services.face_enrollment import (
    FaceAngle,
    FaceCaptureError,
    FaceEnrollment,
    FaceModels,
    OpenCvFaceModels,
)

logger = logging.getLogger(__name__)


class FaceCaptureWorker(QThread):
    ready = Signal()
    preview_ready = Signal(object)
    sample_captured = Signal(object, object)
    status = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        camera_index: int,
        detector_path: Path,
        recognizer_path: Path,
        *,
        models_factory: Callable[[Path, Path], FaceModels] = OpenCvFaceModels,
        capture_factory: Callable[[int], object] = cv2.VideoCapture,
    ) -> None:
        super().__init__()
        self.setObjectName("FaceCaptureWorker")
        self._camera_index = camera_index
        self._detector_path = detector_path
        self._recognizer_path = recognizer_path
        self._models_factory = models_factory
        self._capture_factory = capture_factory
        self._stop = Event()
        self._lock = Lock()
        self._pending: FaceAngle | None = None

    def request_capture(self, angle: FaceAngle) -> None:
        with self._lock:
            self._pending = angle

    def request_stop(self) -> None:
        self._stop.set()
        self.requestInterruption()

    def run(self) -> None:
        camera = None
        try:
            models = self._models_factory(self._detector_path, self._recognizer_path)
            enrollment = FaceEnrollment(models)
            camera = self._capture_factory(self._camera_index)
            if not camera.isOpened():
                raise FaceCaptureError("Não foi possível abrir a webcam selecionada.")
            self.ready.emit()
            while not self._stop.is_set() and not self.isInterruptionRequested():
                ok, frame = camera.read()
                if not ok or frame is None:
                    raise FaceCaptureError("A webcam deixou de fornecer imagens.")
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width = rgb.shape[:2]
                preview = QImage(
                    rgb.data, width, height, 3 * width,
                    QImage.Format.Format_RGB888,
                ).copy()
                self.preview_ready.emit(preview)
                with self._lock:
                    pending, self._pending = self._pending, None
                if pending is not None:
                    try:
                        embedding = enrollment.capture(frame, pending)
                    except FaceCaptureError as error:
                        self.status.emit(str(error))
                    else:
                        self.sample_captured.emit(
                            pending, tuple(float(value) for value in embedding)
                        )
                sleep(0.05)
        except FaceCaptureError as error:
            self.failed.emit(str(error))
        except Exception as error:
            logger.error("face_capture_failed", extra={"error_type": type(error).__name__})
            self.failed.emit("Falha inesperada na captura facial.")
        finally:
            if camera is not None:
                camera.release()


__all__ = ["FaceCaptureWorker"]
