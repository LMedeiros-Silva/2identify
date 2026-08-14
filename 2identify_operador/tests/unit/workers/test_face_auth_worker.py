import numpy as np

from app.domain import OperatorIdentity
from app.vision.face_auth.types import FacePipelineDecision, FacePipelineStatus
from app.workers.face_auth_worker import FaceAuthenticationWorker


class CameraStub:
    def __init__(self, opens: bool = True) -> None:
        self.opens = opens
        self.closed = False
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)

    def open(self) -> bool:
        return self.opens

    def read(self):
        return True, self.frame.copy()

    def close(self) -> None:
        self.closed = True


class RecognizingPipelineStub:
    def process(self, frame, timestamp):
        del frame, timestamp
        return FacePipelineDecision(
            FacePipelineStatus.RECOGNIZED,
            "reconhecido",
            OperatorIdentity(operator_id=9, name="Marina Costa", confidence=0.95),
        )


class WaitingPipelineStub:
    def process(self, frame, timestamp):
        del frame, timestamp
        return FacePipelineDecision(FacePipelineStatus.WAITING_FACE, "aguardando")


def _worker(camera, pipeline) -> FaceAuthenticationWorker:
    return FaceAuthenticationWorker(
        camera_factory=lambda: camera,
        pipeline_factory=lambda: pipeline,
        timeout_seconds=2,
        inference_fps=30,
        preview_fps=30,
        maximum_failed_reads=3,
    )


def test_worker_emits_frame_and_recognition_then_releases_camera(qtbot) -> None:
    camera = CameraStub()
    worker = _worker(camera, RecognizingPipelineStub())

    with qtbot.waitSignals(
        [worker.frame_ready, worker.operator_recognized, worker.finished],
        timeout=2_000,
    ):
        worker.start()

    assert camera.closed


def test_worker_reports_unavailable_camera(qtbot) -> None:
    camera = CameraStub(opens=False)
    worker = _worker(camera, WaitingPipelineStub())

    with qtbot.waitSignal(worker.authentication_failed, timeout=2_000) as failure:
        worker.start()
    worker.wait(2_000)

    assert failure.args == ["Não foi possível abrir a câmera de autenticação.", True]
    assert camera.closed


def test_worker_supports_cooperative_cancellation(qtbot) -> None:
    camera = CameraStub()
    worker = _worker(camera, WaitingPipelineStub())

    with qtbot.waitSignal(worker.frame_ready, timeout=2_000):
        worker.start()
    with qtbot.waitSignal(worker.finished, timeout=2_000):
        worker.request_stop()

    assert camera.closed

