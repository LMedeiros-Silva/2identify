from datetime import UTC, datetime

import numpy as np
import pytest

from app.domain.camera_source import CameraFrame, CameraSource, CameraType


def test_usb_index_is_resolved_from_this_workstation(monkeypatch) -> None:
    camera = CameraSource(17, "USB local", 3, CameraType.USB)
    monkeypatch.setenv("CAMERA_SOURCE_17", "2")
    assert camera.resolve() == 2


def test_ip_source_accepts_network_locator_and_rejects_wrong_protocol() -> None:
    camera = CameraSource(18, "Rede", 3, CameraType.IP, "rtsp://camera.local/live")
    assert camera.resolve() == "rtsp://camera.local/live"
    assert camera.resolve({18: "https://camera.local/mjpeg"}) == "https://camera.local/mjpeg"
    with pytest.raises(ValueError):
        camera.resolve({18: "file:///tmp/video"})


def test_camera_frame_requires_identity_and_timezone() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    assert CameraFrame(7, 3, datetime.now(UTC), frame).camera_id == 7
    with pytest.raises(ValueError):
        CameraFrame(7, 3, datetime(2026, 9, 16), frame)
