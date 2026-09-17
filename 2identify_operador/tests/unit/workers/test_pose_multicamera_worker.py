from datetime import UTC, datetime

import numpy as np

from app.domain.camera_source import CameraFrame
from app.workers.pose_inference_worker import PoseInferenceWorker


class PoseEstimatorStub:
    def estimate(self, frame):
        del frame
        return ()


def test_pose_result_keeps_source_camera_and_generation(qtbot) -> None:
    worker = PoseInferenceWorker(estimator_factory=PoseEstimatorStub)
    with qtbot.waitSignal(worker.model_ready, timeout=2_000):
        worker.start()
    with qtbot.waitSignal(worker.poses_ready, timeout=2_000) as emitted:
        worker.submit_frame(
            CameraFrame(2, 9, datetime.now(UTC), np.zeros((24, 32, 3), dtype=np.uint8))
        )
    assert emitted.args[0].camera_id == 2
    assert emitted.args[0].generation == 9
    worker.request_stop()
    assert worker.wait(2_000)
