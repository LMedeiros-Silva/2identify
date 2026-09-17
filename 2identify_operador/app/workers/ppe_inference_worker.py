"""Latest-frame PPE inference worker with bounded memory usage."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic, sleep

from PySide6.QtCore import QThread, Signal

from app.domain.camera_source import CameraFrame
from app.vision.frame_scheduler import LatestFrameScheduler
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

    def __init__(
        self, detector_factory: PpeDetectorFactory, maximum_global_fps: float | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("PpeInferenceWorker")
        self._detector_factory = detector_factory
        self._scheduler: LatestFrameScheduler[Frame | CameraFrame] = LatestFrameScheduler()
        self._minimum_interval = (
            0.0 if maximum_global_fps is None else 1.0 / maximum_global_fps
        )
        self._inference_count: dict[int, int] = {}
        self._last_frame_age_ms: dict[int, float] = {}
        self._inference_times: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=60))
        self._metrics_lock = threading.Lock()
        self._stop_requested = False

    def submit_frame(self, frame: Frame | CameraFrame) -> None:
        """Replace any stale pending frame with a worker-owned camera snapshot."""

        self._scheduler.submit(frame.camera_id if isinstance(frame, CameraFrame) else 0, frame)

    def metrics(self) -> dict[int, dict[str, float | int]]:
        replaced = self._scheduler.metrics()
        with self._metrics_lock:
            return {
                camera_id: {
                    "inferences": count,
                    "inference_fps": self._rate(self._inference_times[camera_id]),
                    "replaced_frames": replaced.get(camera_id, 0),
                    "last_frame_age_ms": self._last_frame_age_ms.get(camera_id, 0.0),
                }
                for camera_id, count in self._inference_count.items()
            }

    @staticmethod
    def _rate(times: deque[float]) -> float:
        if len(times) < 2 or times[-1] <= times[0]:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])

    def request_stop(self) -> None:
        """Request cooperative shutdown and wake a worker waiting for a frame."""

        self._stop_requested = True
        self._scheduler.stop()
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

            next_inference_at = monotonic()
            while not self._should_stop():
                while not self._should_stop() and monotonic() < next_inference_at:
                    sleep(min(0.05, next_inference_at - monotonic()))
                if self._should_stop():
                    break
                item = self._take_latest_frame()
                if item is None:
                    continue
                if isinstance(item, CameraFrame):
                    envelope = item
                    frame = item.frame
                else:
                    envelope = None
                    frame = item
                if envelope is not None:
                    age_ms = (datetime.now(UTC) - envelope.captured_at).total_seconds() * 1_000
                    with self._metrics_lock:
                        self._last_frame_age_ms[envelope.camera_id] = age_ms
                    if age_ms > 2_000:
                        continue
                if frame.ndim != 3 or frame.shape[2] != 3:
                    raise PpeVisionError("A câmera forneceu uma imagem inválida para a IA.")

                started_at = monotonic()
                detections = detector.detect(frame)
                elapsed_ms = (monotonic() - started_at) * 1_000.0
                next_inference_at = monotonic() + self._minimum_interval
                height, width = frame.shape[:2]
                if envelope is not None:
                    with self._metrics_lock:
                        self._inference_count[envelope.camera_id] = (
                            self._inference_count.get(envelope.camera_id, 0) + 1
                        )
                        self._inference_times[envelope.camera_id].append(monotonic())
                self.detections_ready.emit(
                    PpeDetectionBatch(
                        detections=detections,
                        frame_width=int(width),
                        frame_height=int(height),
                        inference_milliseconds=elapsed_ms,
                        camera_id=envelope.camera_id if envelope else None,
                        generation=envelope.generation if envelope else 0,
                        captured_at=envelope.captured_at if envelope else None,
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
            self._scheduler.stop()

    def _take_latest_frame(self) -> Frame | CameraFrame | None:
        return self._scheduler.take()

    def _should_stop(self) -> bool:
        return self._stop_requested or self.isInterruptionRequested()
