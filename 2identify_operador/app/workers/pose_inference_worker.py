"""Latest-frame pose inference worker with bounded memory usage."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from time import monotonic

from PySide6.QtCore import QThread, Signal

from app.vision.pose import (
    PoseDetectionBatch,
    PoseEstimator,
    PoseModelUnavailableError,
    PoseVisionError,
)
from app.vision.types import Frame

logger = logging.getLogger(__name__)

PoseEstimatorFactory = Callable[[], PoseEstimator]


class PoseInferenceWorker(QThread):
    """Load a pose model and process only the newest submitted frame."""

    model_ready = Signal()
    poses_ready = Signal(object)
    inference_failed = Signal(str, bool)

    def __init__(self, estimator_factory: PoseEstimatorFactory) -> None:
        super().__init__()
        self.setObjectName("PoseInferenceWorker")
        self._estimator_factory = estimator_factory
        self._condition = threading.Condition()
        self._latest_frame: Frame | None = None
        self._stop_requested = False

    def submit_frame(self, frame: Frame) -> None:
        with self._condition:
            if self._stop_requested:
                return
            self._latest_frame = frame
            self._condition.notify()

    def request_stop(self) -> None:
        with self._condition:
            self._stop_requested = True
            self._latest_frame = None
            self._condition.notify_all()
        self.requestInterruption()

    def run(self) -> None:
        try:
            estimator = self._estimator_factory()
            if self._should_stop():
                return
            self.model_ready.emit()
            logger.info("pose_model_loaded")
            while not self._should_stop():
                frame = self._take_latest_frame()
                if frame is None:
                    continue
                if frame.ndim != 3 or frame.shape[2] != 3:
                    raise PoseVisionError(
                        "A câmera forneceu uma imagem inválida para a ergonomia."
                    )
                started_at = monotonic()
                poses = estimator.estimate(frame)
                elapsed_ms = (monotonic() - started_at) * 1_000.0
                height, width = frame.shape[:2]
                self.poses_ready.emit(
                    PoseDetectionBatch(
                        poses=poses,
                        frame_width=int(width),
                        frame_height=int(height),
                        inference_milliseconds=elapsed_ms,
                    )
                )
        except PoseVisionError as error:
            unavailable = isinstance(error, PoseModelUnavailableError)
            logger.warning(
                "pose_inference_unavailable",
                extra={"reason": str(error), "model_unavailable": unavailable},
            )
            self.inference_failed.emit(str(error), unavailable)
        except Exception:
            logger.exception("pose_inference_worker_failed")
            self.inference_failed.emit(
                "Falha inesperada durante a análise ergonômica.",
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
