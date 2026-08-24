from pathlib import Path

import numpy as np
import pytest

from app.vision.pose import PoseModelUnavailableError, UltralyticsPoseEstimator


class TensorStub:
    def __init__(self, value: list[object]) -> None:
        self._value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self) -> list[object]:
        return self._value


class KeypointsStub:
    data = TensorStub([[[float(i), float(i + 1), 0.9] for i in range(17)]])


class BoxesStub:
    conf = TensorStub([0.93])


class ResultStub:
    keypoints = KeypointsStub()
    boxes = BoxesStub()


class ModelStub:
    def __init__(self) -> None:
        self.received: dict[str, object] | None = None

    def predict(self, **kwargs):
        self.received = kwargs
        return [ResultStub()]


def test_pose_adapter_normalizes_all_coco_keypoints(tmp_path: Path) -> None:
    model_path = tmp_path / "pose.pt"
    model_path.write_bytes(b"pose-checkpoint")
    model = ModelStub()
    estimator = UltralyticsPoseEstimator(
        model_path=model_path,
        confidence_threshold=0.5,
        image_size=640,
        device="cpu",
        model_factory=lambda *_args, **_kwargs: model,
    )
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    poses = estimator.estimate(frame)

    assert len(poses) == 1
    assert poses[0].confidence == pytest.approx(0.93)
    assert len(poses[0].keypoints) == 17
    assert poses[0].keypoints[5].x == 5.0
    assert poses[0].keypoints[5].confidence == pytest.approx(0.9)
    assert model.received is not None
    assert model.received["source"] is frame
    assert model.received["conf"] == 0.5


def test_pose_adapter_fails_closed_for_missing_or_changed_model(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.pt"
    with pytest.raises(PoseModelUnavailableError, match="não foi encontrado"):
        UltralyticsPoseEstimator(
            model_path=missing,
            confidence_threshold=0.5,
            image_size=640,
            device="cpu",
        )

    model_path = tmp_path / "pose.pt"
    model_path.write_bytes(b"pose-checkpoint")
    with pytest.raises(PoseModelUnavailableError, match="integridade"):
        UltralyticsPoseEstimator(
            model_path=model_path,
            confidence_threshold=0.5,
            image_size=640,
            device="cpu",
            expected_sha256="0" * 64,
            model_factory=lambda *_args, **_kwargs: ModelStub(),
        )
