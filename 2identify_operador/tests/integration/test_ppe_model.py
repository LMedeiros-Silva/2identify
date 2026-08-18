import numpy as np
import pytest

from app.core.config import AppSettings
from app.vision.ppe import UltralyticsPpeDetector


def test_configured_ppe_checkpoint_loads_expected_classes(
    tmp_path,
    monkeypatch,
) -> None:
    settings = AppSettings(_env_file=None)
    if not settings.ppe_model_path.is_file():
        pytest.skip("checkpoint PPE local não instalado")

    monkeypatch.setenv("YOLO_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path))
    monkeypatch.setenv("YOLO_OFFLINE", "true")
    detector = UltralyticsPpeDetector(
        model_path=settings.ppe_model_path,
        expected_sha256=settings.ppe_model_sha256,
        confidence_threshold=settings.ppe_confidence_threshold,
        iou_threshold=settings.ppe_iou_threshold,
        image_size=settings.ppe_inference_image_size,
        device=settings.ppe_inference_device,
    )

    assert detector.class_names == (
        "bota",
        "capacete",
        "colete_refletivo",
        "luva",
        "mangote",
        "mao_sem_luva",
        "mascara",
        "oculos",
        "protetor_headset",
        "protetor_intra",
        "tronco_sem_colete",
    )
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert detector.detect(blank_frame) == ()
