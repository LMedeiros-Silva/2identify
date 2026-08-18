from pathlib import Path

import numpy as np
import pytest

from app.vision.ppe import PpeModelUnavailableError, UltralyticsPpeDetector


class TensorStub:
    def __init__(self, value: list[object]) -> None:
        self._value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self) -> list[object]:
        return self._value


class BoxesStub:
    xyxy = TensorStub([[10.0, 20.0, 80.0, 100.0]])
    cls = TensorStub([1.0])
    conf = TensorStub([0.91])


class ResultStub:
    boxes = BoxesStub()


class ModelStub:
    names = {0: "bota", 1: "capacete"}

    def __init__(self) -> None:
        self.received: dict[str, object] | None = None

    def predict(self, **kwargs):
        self.received = kwargs
        return [ResultStub()]


def _detector(model_path: Path, model: ModelStub) -> UltralyticsPpeDetector:
    return UltralyticsPpeDetector(
        model_path=model_path,
        confidence_threshold=0.5,
        iou_threshold=0.45,
        image_size=640,
        device="cpu",
        model_factory=lambda *_args, **_kwargs: model,
    )


def test_ultralytics_adapter_normalizes_model_results(tmp_path: Path) -> None:
    model_path = tmp_path / "best.pt"
    model_path.write_bytes(b"checkpoint-test")
    model = ModelStub()
    detector = _detector(model_path, model)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    detections = detector.detect(frame)

    assert detector.class_names == ("bota", "capacete")
    assert len(detections) == 1
    assert detections[0].class_id == 1
    assert detections[0].class_name == "capacete"
    assert detections[0].confidence == pytest.approx(0.91)
    assert model.received is not None
    assert model.received["source"] is frame
    assert model.received["conf"] == 0.5
    assert model.received["device"] == "cpu"


def test_ultralytics_adapter_fails_closed_for_missing_model(tmp_path: Path) -> None:
    with pytest.raises(PpeModelUnavailableError, match="não foi encontrado"):
        _detector(tmp_path / "missing.pt", ModelStub())


def test_ultralytics_adapter_rejects_checkpoint_with_wrong_checksum(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "best.pt"
    model_path.write_bytes(b"checkpoint-test")

    with pytest.raises(PpeModelUnavailableError, match="integridade"):
        UltralyticsPpeDetector(
            model_path=model_path,
            expected_sha256="0" * 64,
            confidence_threshold=0.5,
            iou_threshold=0.45,
            image_size=640,
            device="cpu",
            model_factory=lambda *_args, **_kwargs: ModelStub(),
        )
