import numpy as np

from app.workers.safety_camera_worker import SafetyCameraWorker


class CameraStub:
    def __init__(
        self,
        *,
        opens: bool = True,
        successful_reads: bool = True,
    ) -> None:
        self.opens = opens
        self.successful_reads = successful_reads
        self.closed = False
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)

    def open(self) -> bool:
        return self.opens

    def read(self):
        if not self.successful_reads:
            return False, None
        return True, self.frame.copy()

    def close(self) -> None:
        self.closed = True


def _worker(camera: CameraStub) -> SafetyCameraWorker:
    return SafetyCameraWorker(
        camera_factory=lambda: camera,
        preview_fps=30,
        maximum_failed_reads=3,
    )


def test_safety_camera_worker_streams_owned_preview_and_releases_camera(qtbot) -> None:
    camera = CameraStub()
    worker = _worker(camera)

    with qtbot.waitSignals(
        [worker.camera_ready, worker.frame_ready],
        timeout=2_000,
    ):
        worker.start()
    with qtbot.waitSignal(worker.finished, timeout=2_000):
        worker.request_stop()

    assert camera.closed


def test_safety_camera_worker_reports_unavailable_source(qtbot) -> None:
    camera = CameraStub(opens=False)
    worker = _worker(camera)

    with qtbot.waitSignal(worker.camera_failed, timeout=2_000) as failure:
        worker.start()
    worker.wait(2_000)

    assert failure.args == ["Não foi possível abrir a câmera de verificação.", True]
    assert camera.closed


def test_safety_camera_worker_limits_consecutive_read_failures(qtbot) -> None:
    camera = CameraStub(successful_reads=False)
    worker = _worker(camera)

    with qtbot.waitSignal(worker.camera_failed, timeout=2_000) as failure:
        worker.start()
    worker.wait(2_000)

    assert failure.args == [
        "A câmera de verificação parou de fornecer imagens.",
        True,
    ]
    assert camera.closed


def test_safety_camera_worker_publishes_owned_analysis_frames(qtbot) -> None:
    camera = CameraStub()
    worker = SafetyCameraWorker(
        camera_factory=lambda: camera,
        preview_fps=30,
        maximum_failed_reads=3,
        analysis_fps=10,
    )

    with qtbot.waitSignal(worker.analysis_frame_ready, timeout=2_000) as emitted:
        worker.start()

    analysis_frame = emitted.args[0]
    assert analysis_frame is not camera.frame
    assert analysis_frame.shape == camera.frame.shape
    with qtbot.waitSignal(worker.finished, timeout=2_000):
        worker.request_stop()
