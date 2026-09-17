from datetime import UTC, datetime

import numpy as np

from app.domain.camera_source import CameraFrame
from app.vision.ppe import DetectionBox, PpeDetection, PpeModelUnavailableError
from app.workers.ppe_inference_worker import PpeInferenceWorker


class DetectorStub:
    class_names = ("bota", "capacete")

    def detect(self, frame):
        del frame
        return (
            PpeDetection(
                1,
                "capacete",
                0.91,
                DetectionBox(10, 20, 80, 100),
            ),
        )


def test_ppe_worker_loads_model_and_processes_latest_frame(qtbot) -> None:
    worker = PpeInferenceWorker(detector_factory=DetectorStub)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    with qtbot.waitSignal(worker.model_ready, timeout=2_000) as ready:
        worker.start()
    with qtbot.waitSignal(worker.detections_ready, timeout=2_000) as emitted:
        worker.submit_frame(frame)

    batch = emitted.args[0]
    assert ready.args == [("bota", "capacete")]
    assert batch.frame_width == 160
    assert batch.frame_height == 120
    assert batch.observed_classes == frozenset({"capacete"})
    with qtbot.waitSignal(worker.finished, timeout=2_000):
        worker.request_stop()


def test_ppe_worker_reports_model_unavailability(qtbot) -> None:
    def unavailable_detector():
        raise PpeModelUnavailableError("Modelo ausente para teste.")

    worker = PpeInferenceWorker(detector_factory=unavailable_detector)

    with qtbot.waitSignal(worker.inference_failed, timeout=2_000) as failure:
        worker.start()
    worker.wait(2_000)

    assert failure.args == ["Modelo ausente para teste.", True]


def test_one_ppe_model_serves_identified_frames_from_two_cameras(qtbot) -> None:
    loads = []

    def detector_factory():
        loads.append(1)
        return DetectorStub()

    worker = PpeInferenceWorker(detector_factory=detector_factory, maximum_global_fps=20)
    batches = []
    worker.detections_ready.connect(batches.append)
    with qtbot.waitSignal(worker.model_ready, timeout=2_000):
        worker.start()
    for camera_id in (1, 2):
        worker.submit_frame(
            CameraFrame(
                camera_id,
                7,
                datetime.now(UTC),
                np.zeros((32, 48, 3), dtype=np.uint8),
            )
        )
    qtbot.waitUntil(lambda: len(batches) == 2, timeout=2_000)
    assert loads == [1]
    assert {batch.camera_id for batch in batches} == {1, 2}
    assert {batch.generation for batch in batches} == {7}
    assert worker.metrics()[1]["inferences"] == 1
    assert worker.metrics()[2]["last_frame_age_ms"] >= 0
    worker.request_stop()
    assert worker.wait(2_000)
