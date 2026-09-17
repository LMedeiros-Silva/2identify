"""Lifecycle owner for the selected cameras of one monitoring generation."""

from __future__ import annotations

import logging
import sys
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from functools import partial
from time import monotonic, process_time

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from app.core.config import AppSettings
from app.domain.camera_source import CameraFrame, CameraSource, CameraStatus
from app.vision.camera import OpenCVCameraSession
from app.workers.safety_camera_worker import SafetyCameraWorker

logger = logging.getLogger(__name__)
CameraWorkerFactory = Callable[[CameraSource, int | str, int], SafetyCameraWorker]


class CameraManager(QObject):
    """Open only selected sources; isolate failure and reject stale generations."""

    preview_ready = Signal(int, object)
    analysis_frame_ready = Signal(object)
    status_changed = Signal(int, object)

    def __init__(
        self,
        settings: AppSettings,
        parent: QObject | None = None,
        worker_factory: CameraWorkerFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker_factory = worker_factory or self._new_worker
        self._generation = 0
        self._selected: dict[int, CameraSource] = {}
        self._workers: dict[int, SafetyCameraWorker] = {}
        self._worker_identity: dict[SafetyCameraWorker, tuple[int, int]] = {}
        self._retiring_workers: set[SafetyCameraWorker] = set()
        self._statuses: dict[int, CameraStatus] = {}
        self._retry_count: dict[int, int] = defaultdict(int)
        self._reconnect_count: dict[int, int] = defaultdict(int)
        self._preview_count: dict[int, int] = defaultdict(int)
        self._preview_times: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=60))
        self._latest_preview: dict[int, QImage] = {}
        self._started_at = monotonic()
        self._cpu_started_at = process_time()
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(50)
        self._preview_timer.timeout.connect(self._flush_preview)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def selected_camera_ids(self) -> tuple[int, ...]:
        return tuple(self._selected)

    def status(self, camera_id: int) -> CameraStatus | None:
        return self._statuses.get(camera_id)

    def metrics(self) -> dict[int, dict[str, float | int]]:
        return {
            camera_id: {
                "preview_frames": self._preview_count[camera_id],
                "preview_fps": self._rate(self._preview_times[camera_id]),
                "reconnects": self._reconnect_count[camera_id],
            }
            for camera_id in self._selected
        }

    def system_metrics(self) -> dict[str, float | None]:
        elapsed = max(monotonic() - self._started_at, 0.001)
        values: dict[str, float | None] = {
            "process_cpu_percent": 100.0 * (process_time() - self._cpu_started_at) / elapsed,
            "process_ram_mb": None,
            "gpu_allocated_mb": None,
        }
        try:
            import psutil  # type: ignore[import-untyped]

            values["process_ram_mb"] = psutil.Process().memory_info().rss / 1_048_576
        except (ImportError, OSError):
            pass
        torch = sys.modules.get("torch")
        if torch is not None:
            try:
                if torch.cuda.is_available():
                    values["gpu_allocated_mb"] = torch.cuda.memory_allocated() / 1_048_576
            except (AttributeError, RuntimeError):
                pass
        return values

    @staticmethod
    def _rate(times: deque[float]) -> float:
        if len(times) <= 1 or times[-1] <= times[0]:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])

    def start(self, cameras: Sequence[CameraSource]) -> None:
        selected = tuple(cameras)
        if not selected or len({item.camera_id for item in selected}) != len(selected):
            raise ValueError("selecione uma ou mais câmeras sem duplicidades")
        if not self.stop():
            raise RuntimeError("captura anterior ainda não liberou as câmeras")
        self._selected = {item.camera_id: item for item in selected}
        self._started_at = monotonic()
        self._cpu_started_at = process_time()
        self._preview_count.clear()
        self._preview_times.clear()
        self._reconnect_count.clear()
        self._preview_timer.start()
        for camera_id in self._selected:
            self._open(camera_id, self._generation)

    def stop(self, wait_timeout_ms: int = 5_000) -> bool:
        self._generation += 1
        self._preview_timer.stop()
        self._latest_preview.clear()
        workers = tuple(set(self._workers.values()) | self._retiring_workers)
        self._workers.clear()
        self._worker_identity.clear()
        self._retiring_workers.clear()
        self._selected.clear()
        self._statuses.clear()
        self._retry_count.clear()
        for worker in workers:
            worker.request_stop()
        deadline = monotonic() + wait_timeout_ms / 1_000
        released = True
        for worker in workers:
            remaining = max(0, round((deadline - monotonic()) * 1_000))
            if worker.isRunning() and not worker.wait(remaining):
                logger.error("camera_worker_shutdown_timeout")
                self._retiring_workers.add(worker)
                released = False
            else:
                worker.deleteLater()
        return released

    def _new_worker(
        self, camera: CameraSource, source: int | str, generation: int
    ) -> SafetyCameraWorker:
        settings = self._settings
        pose_ids = settings.parsed_pose_camera_ids
        pose_selected = settings.pose_estimation_enabled and (
            pose_ids is None or camera.camera_id in pose_ids
        )
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
            analysis_fps=max(
                settings.ppe_inference_fps,
                settings.pose_inference_fps if pose_selected else 0.0,
            ),
            maximum_failed_reads=settings.camera_max_failed_reads,
            camera_id=camera.camera_id,
            generation=generation,
        )

    def _open(self, camera_id: int, generation: int) -> None:
        if generation != self._generation or camera_id not in self._selected:
            return
        camera = self._selected[camera_id]
        self._set_status(
            camera_id,
            (
                CameraStatus.CONNECTING
                if self._retry_count[camera_id] == 0
                else CameraStatus.RECONNECTING
            ),
        )
        try:
            source = camera.resolve()
        except ValueError:
            logger.warning("camera_local_source_invalid", extra={"camera_id": camera_id})
            self._failed(camera_id, generation)
            return
        worker = self._worker_factory(camera, source, generation)
        self._workers[camera_id] = worker
        self._worker_identity[worker] = camera_id, generation
        worker.identified_ready.connect(self._ready)
        worker.identified_preview_ready.connect(self._preview)
        worker.identified_frame_ready.connect(self._frame)
        worker.identified_failed.connect(self._failed)
        worker.finished.connect(self._finished)
        worker.start()

    @Slot(int, int)
    def _ready(self, camera_id: int, generation: int) -> None:
        if generation != self._generation:
            return
        self._retry_count[camera_id] = 0
        self._set_status(camera_id, CameraStatus.ONLINE)

    @Slot(int, int, QImage)
    def _preview(self, camera_id: int, generation: int, image: QImage) -> None:
        if generation == self._generation and camera_id in self._selected:
            self._latest_preview[camera_id] = image
            self._preview_count[camera_id] += 1
            self._preview_times[camera_id].append(monotonic())

    def _flush_preview(self) -> None:
        pending, self._latest_preview = self._latest_preview, {}
        for camera_id, image in pending.items():
            self.preview_ready.emit(camera_id, image)

    @Slot(object)
    def _frame(self, value: object) -> None:
        if (
            isinstance(value, CameraFrame)
            and value.generation == self._generation
            and value.camera_id in self._selected
        ):
            self.analysis_frame_ready.emit(value)

    @Slot(int, int)
    def _failed(self, camera_id: int, generation: int) -> None:
        if generation != self._generation or camera_id not in self._selected:
            return
        self._set_status(camera_id, CameraStatus.OFFLINE)
        self._retry_count[camera_id] += 1
        self._reconnect_count[camera_id] += 1
        delay_ms = min(30_000, 500 * 2 ** min(self._retry_count[camera_id] - 1, 6))
        QTimer.singleShot(delay_ms, partial(self._retry, camera_id, generation))

    def _retry(self, camera_id: int, generation: int) -> None:
        if generation != self._generation or camera_id not in self._selected:
            return
        worker = self._workers.get(camera_id)
        if worker is not None and worker.isRunning():
            QTimer.singleShot(250, partial(self._retry, camera_id, generation))
            return
        self._open(camera_id, generation)

    @Slot()
    def _finished(self) -> None:
        worker = self.sender()
        if not isinstance(worker, SafetyCameraWorker):
            return
        if worker in self._retiring_workers:
            self._retiring_workers.discard(worker)
            worker.deleteLater()
            return
        identity = self._worker_identity.pop(worker, None)
        if identity is None:
            worker.deleteLater()
            return
        camera_id, generation = identity
        if self._workers.get(camera_id) is worker:
            self._workers.pop(camera_id)
        worker.deleteLater()
        if (
            generation == self._generation
            and camera_id in self._selected
            and self._statuses.get(camera_id) is CameraStatus.ONLINE
        ):
            self._failed(camera_id, generation)

    def _set_status(self, camera_id: int, status: CameraStatus) -> None:
        self._statuses[camera_id] = status
        self.status_changed.emit(camera_id, status)
