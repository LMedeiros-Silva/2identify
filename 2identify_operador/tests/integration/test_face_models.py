import pytest

from app.core.config import AppSettings
from app.vision.face_auth.opencv_models import SFaceEncoder, YuNetFaceDetector


def test_configured_opencv_face_models_load() -> None:
    settings = AppSettings()
    if not settings.face_detector_model_path.is_file():
        pytest.skip("YuNet model is not installed")
    if not settings.face_recognition_model_path.is_file():
        pytest.skip("SFace model is not installed")

    YuNetFaceDetector(
        settings.face_detector_model_path,
        settings.face_auth_detection_threshold,
    )
    SFaceEncoder(settings.face_recognition_model_path)

