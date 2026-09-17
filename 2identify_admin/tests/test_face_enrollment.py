"""Hardware-free YuNet/SFace enrollment rules."""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

import numpy as np
import pytest
from PySide6.QtTest import QSignalSpy

from app.services.face_enrollment import (
    FaceAngle,
    FaceCaptureError,
    FaceEnrollment,
    FaceObservation,
    validate_face,
)
from app.services.model_artifacts import native_model_path
from app.workers.face_capture_worker import FaceCaptureWorker


def _frame() -> np.ndarray:
    return np.random.default_rng(7).integers(80, 180, (480, 640, 3), dtype=np.uint8)


def _face(yaw: float = 0, *, confidence: float = 0.98) -> FaceObservation:
    return FaceObservation(
        box=(250, 140, 140, 150),
        landmarks=((280, 190), (340, 190), (310 + yaw * 60, 210), (290, 245), (330, 245)),
        confidence=confidence,
        raw=tuple([0.0] * 15),
    )


class _Models:
    def __init__(self, faces: tuple[FaceObservation, ...]) -> None:
        self.faces = faces

    def detect(self, frame):
        del frame
        return self.faces

    def encode(self, frame, face):
        del frame, face
        return np.asarray([1.0] + [0.0] * 127, dtype=np.float32)


def test_three_distinct_angles_produce_normalized_template() -> None:
    models = _Models((_face(),))
    enrollment = FaceEnrollment(models)
    for angle, yaw in (
        (FaceAngle.FRONTAL, 0),
        (FaceAngle.ESQUERDA, -0.35),
        (FaceAngle.DIREITA, 0.35),
    ):
        models.faces = (_face(yaw),)
        enrollment.capture(_frame(), angle)
    template = enrollment.template()
    assert template.model_id == "opencv_sface_2021dec"
    assert len(template.embedding) == 128
    assert np.isclose(np.linalg.norm(template.embedding), 1.0)
    assert "embedding" not in repr(template)


def test_native_model_path_stages_unicode_windows_installation(tmp_path: Path) -> None:
    source = tmp_path / "área" / "modelo.onnx"
    source.parent.mkdir()
    source.write_bytes(b"public model fixture")

    compatible = native_model_path(source)

    assert compatible != source
    assert compatible.read_bytes() == source.read_bytes()
    assert compatible == native_model_path(source)
    compatible.as_posix().encode("ascii")


@pytest.mark.parametrize(
    ("faces", "message"),
    [
        ((), "Nenhum rosto"),
        ((_face(), _face()), "vários rostos"),
        ((_face(confidence=0.2),), "Confiança"),
    ],
)
def test_rejects_missing_multiple_or_low_confidence_faces(faces, message) -> None:
    with pytest.raises(FaceCaptureError, match=message):
        FaceEnrollment(_Models(faces)).capture(_frame(), FaceAngle.FRONTAL)


def test_rejects_blurry_frame_and_wrong_head_orientation() -> None:
    blurred = np.full((480, 640, 3), 120, dtype=np.uint8)
    with pytest.raises(FaceCaptureError, match="nítido"):
        validate_face(blurred, _face(), FaceAngle.FRONTAL)
    with pytest.raises(FaceCaptureError, match="esquerda"):
        validate_face(_frame(), _face(0.4), FaceAngle.ESQUERDA)


def test_template_requires_all_three_angles_and_recapture_replaces_sample() -> None:
    models = _Models((_face(),))
    enrollment = FaceEnrollment(models)
    enrollment.capture(_frame(), FaceAngle.FRONTAL)
    enrollment.capture(_frame(), FaceAngle.FRONTAL)
    assert enrollment.captured == frozenset({FaceAngle.FRONTAL})
    with pytest.raises(FaceCaptureError, match="frontal, esquerda e direita"):
        enrollment.template()


class _Capture:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.released = False

    def isOpened(self):
        return self.available

    def read(self):
        return True, _frame()

    def release(self):
        self.released = True


def _await(qapp, condition) -> None:
    deadline = monotonic() + 3
    while not condition() and monotonic() < deadline:
        qapp.processEvents()
        sleep(0.01)
    assert condition()


def test_capture_worker_uses_fake_webcam_and_releases_it(qapp) -> None:
    camera = _Capture()
    worker = FaceCaptureWorker(
        2,
        Path("fake-yunet"),
        Path("fake-sface"),
        models_factory=lambda *_paths: _Models((_face(),)),
        capture_factory=lambda index: camera if index == 2 else None,
    )
    ready = QSignalSpy(worker.ready)
    captured = QSignalSpy(worker.sample_captured)
    worker.start()
    _await(qapp, lambda: ready.count() > 0)
    worker.request_capture(FaceAngle.FRONTAL)
    _await(qapp, lambda: captured.count() > 0)
    assert captured.at(0)[0] is FaceAngle.FRONTAL
    worker.request_stop()
    assert worker.wait(3000)
    assert camera.released
