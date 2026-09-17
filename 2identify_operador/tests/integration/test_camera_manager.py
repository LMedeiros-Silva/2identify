from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.controllers.camera_manager import CameraManager
from app.core.config import AppSettings
from app.domain.camera_source import CameraFrame, CameraSource, CameraStatus, CameraType
from app.workers.safety_camera_worker import SafetyCameraWorker


class FakeSession:
    def __init__(self, marker: int, *, available: bool = True) -> None:
        self.marker = marker
        self.available = available
        self.opens = 0
        self.closes = 0

    def open(self) -> bool:
        self.opens += 1
        return self.available

    def read(self):
        return True, np.full((32, 48, 3), self.marker, dtype=np.uint8)

    def close(self) -> None:
        self.closes += 1


def _cameras() -> tuple[CameraSource, ...]:
    return (
        CameraSource(1, "Rede A", 7, CameraType.IP, "rtsp://camera-a.local/live"),
        CameraSource(2, "Rede B", 7, CameraType.IP, "http://camera-b.local/mjpeg"),
        CameraSource(3, "USB A", 7, CameraType.USB),
        CameraSource(4, "USB B", 7, CameraType.USB),
        CameraSource(5, "Rede C", 7, CameraType.IP, "https://camera-c.local/live"),
        CameraSource(6, "Rede D", 7, CameraType.IP, "rtsp://camera-d.local/live"),
    )


def _manager(sessions: dict[int, FakeSession], opened: list[tuple[int, int | str]]):
    def new_worker(camera, source, generation):
        opened.append((camera.camera_id, source))
        return SafetyCameraWorker(
            camera_factory=lambda: sessions[camera.camera_id],
            preview_fps=20,
            maximum_failed_reads=2,
            analysis_fps=5,
            camera_id=camera.camera_id,
            generation=generation,
        )

    manager = CameraManager(AppSettings(_env_file=None), worker_factory=new_worker)
    return manager


@pytest.mark.parametrize(
    ("available_count", "selected_count"),
    [(5, 1), (5, 3), (5, 4), (5, 5), (6, 4), (6, 6)],
)
def test_only_selected_ip_and_usb_sources_open_and_close(
    qtbot, monkeypatch, available_count: int, selected_count: int
) -> None:
    monkeypatch.setenv("CAMERA_SOURCE_3", "0")
    monkeypatch.setenv("CAMERA_SOURCE_4", "1")
    cameras = _cameras()
    sessions = {camera.camera_id: FakeSession(camera.camera_id) for camera in cameras}
    opened: list[tuple[int, int | str]] = []
    manager = _manager(sessions, opened)
    frames: list[CameraFrame] = []
    manager.analysis_frame_ready.connect(frames.append)
    selected = cameras[:available_count][:selected_count]
    manager.start(selected)
    qtbot.waitUntil(
        lambda: all(manager.status(camera.camera_id) is CameraStatus.ONLINE for camera in selected),
        timeout=2_000,
    )
    assert manager.selected_camera_ids == tuple(camera.camera_id for camera in selected)
    qtbot.waitUntil(
        lambda: {frame.camera_id for frame in frames}
        == {camera.camera_id for camera in selected},
        timeout=2_000,
    )
    assert all(frame.generation == manager.generation for frame in frames)
    assert "preview_fps" in manager.metrics()[selected[0].camera_id]
    assert manager.system_metrics()["process_ram_mb"] is not None
    assert {camera_id for camera_id, _source in opened} == {
        camera.camera_id for camera in selected
    }
    if selected_count >= 4:
        assert (3, 0) in opened and (4, 1) in opened
    assert manager.stop()
    assert all(sessions[camera.camera_id].closes >= 1 for camera in selected)
    assert all(sessions[camera.camera_id].opens == 0 for camera in cameras[selected_count:])


def test_nonconsecutive_ip_and_usb_subset_does_not_open_other_catalog_cameras(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setenv("CAMERA_SOURCE_3", "0")
    cameras = _cameras()
    sessions = {camera.camera_id: FakeSession(camera.camera_id) for camera in cameras}
    opened: list[tuple[int, int | str]] = []
    manager = _manager(sessions, opened)
    selected = tuple(camera for camera in cameras if camera.camera_id in {1, 2, 3, 5})
    manager.start(selected)
    qtbot.waitUntil(
        lambda: all(manager.status(camera.camera_id) is CameraStatus.ONLINE for camera in selected),
        timeout=2_000,
    )
    assert {camera_id for camera_id, _source in opened} == {1, 2, 3, 5}
    assert (3, 0) in opened
    assert sessions[4].opens == sessions[6].opens == 0
    assert manager.stop()
    assert all(sessions[camera.camera_id].closes >= 1 for camera in selected)


def test_offline_camera_reconnects_without_stopping_other_source(qtbot) -> None:
    cameras = _cameras()[:2]
    sessions = {1: FakeSession(1), 2: FakeSession(2, available=False)}
    manager = _manager(sessions, [])
    manager.start(cameras)
    qtbot.waitUntil(
        lambda: manager.status(1) is CameraStatus.ONLINE
        and manager.status(2) is CameraStatus.OFFLINE,
        timeout=2_000,
    )
    before = manager.metrics()[1]["preview_frames"]
    sessions[2].available = True
    qtbot.waitUntil(lambda: manager.status(2) is CameraStatus.ONLINE, timeout=3_000)
    assert manager.metrics()[1]["preview_frames"] > before
    assert manager.metrics()[2]["reconnects"] >= 1
    assert manager.stop()


def test_new_generation_rejects_late_frames_from_stopped_selection(qtbot) -> None:
    camera = _cameras()[0]
    session = FakeSession(1)
    manager = _manager({1: session}, [])
    emitted: list[CameraFrame] = []
    manager.analysis_frame_ready.connect(emitted.append)
    manager.start((camera,))
    old_generation = manager.generation
    qtbot.waitUntil(lambda: manager.status(1) is CameraStatus.ONLINE, timeout=2_000)
    assert manager.stop()
    manager.start((camera,))
    late = CameraFrame(1, old_generation, datetime.now(UTC), np.zeros((8, 8, 3), dtype=np.uint8))
    count = len(emitted)
    manager._frame(late)
    assert len(emitted) == count
    assert manager.generation != old_generation
    assert manager.stop()
