"""Latest-frame PPE inference worker with bounded memory usage."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from time import monotonic

from PySide6.QtCore import QThread, Signal

from app.vision.ppe import (
    PpeDetectionBatch,
    PpeDetector,
    PpeModelUnavailableError,
    PpeVisionError,
)
from app.vision.types import Frame

logger = logging.getLogger(__name__)

PpeDetectorFactory = Callable[[], PpeDetector]


class PpeInferenceWorker(QThread):
    """Load YOLO and process only the newest camera frame off the UI thread."""

    model_ready = Signal(object)
    detections_ready = Signal(object)
    inference_failed = Signal(str, bool)

    def __init__(self, detector_factory: PpeDetectorFactory) -> None:
        super().__init__()
        self.setObjectName("PpeInferenceWorker")
        self._detector_factory = detector_factory
        self._condition = threading.Condition()
        self._latest_frame: Frame | None = None
        self._stop_requested = False

    def submit_frame(self, frame: Frame) -> None:
        """Replace any stale pending frame with a worker-owned camera snapshot."""

        with self._condition:
            if self._stop_requested:
                return
            self._latest_frame = frame
            self._condition.notify()

    def request_stop(self) -> None:
        """Request cooperative shutdown and wake a worker waiting for a frame."""

        with self._condition:
            self._stop_requested = True
            self._latest_frame = None
            self._condition.notify_all()
        self.requestInterruption()

    def run(self) -> None:
        try:
            detector = self._detector_factory()
            if self._should_stop():
                return
            self.model_ready.emit(detector.class_names)
            logger.info(
                "ppe_model_loaded",
                extra={"class_count": len(detector.class_names)},
            )

            while not self._should_stop():
                frame = self._take_latest_frame()
                if frame is None:
                    continue
                if frame.ndim != 3 or frame.shape[2] != 3:
                    raise PpeVisionError("A câmera forneceu uma imagem inválida para a IA.")

                started_at = monotonic()
                detections = detector.detect(frame)
                elapsed_ms = (monotonic() - started_at) * 1_000.0
                height, width = frame.shape[:2]
                self.detections_ready.emit(
                    PpeDetectionBatch(
                        detections=detections,
                        frame_width=int(width),
                        frame_height=int(height),
                        inference_milliseconds=elapsed_ms,
                    )
                )
        except PpeVisionError as error:
            unavailable = isinstance(error, PpeModelUnavailableError)
            logger.warning(
                "ppe_inference_unavailable",
                extra={"reason": str(error), "model_unavailable": unavailable},
            )
            self.inference_failed.emit(str(error), unavailable)
        except Exception:
            logger.exception("ppe_inference_worker_failed")
            self.inference_failed.emit(
                "Falha inesperada durante a detecção de EPIs.",
                False,
            )
        finally:
            with self._condition:
                self._latest_frame = None

    def _take_latest_frame(self) -> Frame | None:
        with self._condition:
            while self._latest_frame is None and not self._stop_requested:
                self._condition.wait(timeout=0.25)
            if self._stop_requested:
                return None
            frame = self._latest_frame
            self._latest_frame = None
            return frame

    def _should_stop(self) -> bool:
        return self._stop_requested or self.isInterruptionRequested()
