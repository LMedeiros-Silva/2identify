"""Latest-frame pose inference worker with bounded memory usage."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic

from PySide6.QtCore import QThread, Signal

from app.domain.camera_source import CameraFrame
from app.vision.frame_scheduler import LatestFrameScheduler
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
        self._scheduler: LatestFrameScheduler[Frame | CameraFrame] = LatestFrameScheduler()
        self._stop_requested = False

    def submit_frame(self, frame: Frame | CameraFrame) -> None:
        self._scheduler.submit(frame.camera_id if isinstance(frame, CameraFrame) else 0, frame)

    def request_stop(self) -> None:
        self._stop_requested = True
        self._scheduler.stop()
        self.requestInterruption()

    def run(self) -> None:
        try:
            estimator = self._estimator_factory()
            if self._should_stop():
                return
            self.model_ready.emit()
            logger.info("pose_model_loaded")
            while not self._should_stop():
                item = self._take_latest_frame()
                if item is None:
                    continue
                if isinstance(item, CameraFrame):
                    envelope = item
                    frame = item.frame
                else:
                    envelope = None
                    frame = item
                if envelope is not None and (
                    datetime.now(UTC) - envelope.captured_at
                ).total_seconds() > 2.0:
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
                        camera_id=envelope.camera_id if envelope else None,
                        generation=envelope.generation if envelope else 0,
                        captured_at=envelope.captured_at if envelope else None,
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
            self._scheduler.stop()

    def _take_latest_frame(self) -> Frame | CameraFrame | None:
        return self._scheduler.take()

    def _should_stop(self) -> bool:
        return self._stop_requested or self.isInterruptionRequested()
