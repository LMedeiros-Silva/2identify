"""Offline Ultralytics pose adapter isolated from Qt and ergonomics rules."""

from __future__ import annotations

import os
from collections.abc import Callable
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any

from app.vision.pose.errors import PoseInferenceError, PoseModelUnavailableError
from app.vision.pose.types import COCO_KEYPOINT_COUNT, PersonPose, PoseKeypoint
from app.vision.types import Frame

ModelFactory = Callable[..., Any]


class UltralyticsPoseEstimator:
    """Load one local COCO pose checkpoint and normalize its keypoints."""

    def __init__(
        self,
        model_path: Path,
        confidence_threshold: float,
        image_size: int,
        device: str,
        expected_sha256: str | None = None,
        config_directory: Path | None = None,
        model_factory: ModelFactory | None = None,
    ) -> None:
        if not model_path.is_file() or model_path.suffix.casefold() != ".pt":
            raise PoseModelUnavailableError(
                "O modelo de pose para ergonomia não foi encontrado."
            )
        if expected_sha256 is not None and (
            _file_sha256(model_path) != expected_sha256.casefold()
        ):
            raise PoseModelUnavailableError(
                "A verificação de integridade do modelo de pose falhou."
            )
        if not 0.0 < confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold deve estar entre 0 e 1")
        if image_size <= 0:
            raise ValueError("image_size deve ser positivo")
        if not device.strip():
            raise ValueError("device não pode ser vazio")

        try:
            _configure_runtime(config_directory)
            factory = model_factory or import_module("ultralytics").YOLO
            self._model = factory(str(model_path), task="pose")
        except PoseModelUnavailableError:
            raise
        except Exception as error:
            raise PoseModelUnavailableError(
                "Não foi possível carregar o modelo de pose para ergonomia."
            ) from error

        self._confidence_threshold = confidence_threshold
        self._image_size = image_size
        self._device = device.strip()

    def estimate(self, frame: Frame) -> tuple[PersonPose, ...]:
        try:
            results = self._model.predict(
                source=frame,
                conf=self._confidence_threshold,
                imgsz=self._image_size,
                device=self._device,
                verbose=False,
            )
            if not results or results[0].keypoints is None:
                return ()
            raw_keypoints = results[0].keypoints.data.detach().cpu().tolist()
            boxes = results[0].boxes
            raw_confidences = (
                boxes.conf.detach().cpu().tolist()
                if boxes is not None and boxes.conf is not None
                else [1.0] * len(raw_keypoints)
            )
        except Exception as error:
            raise PoseInferenceError(
                "O modelo de pose falhou ao processar a imagem da câmera."
            ) from error

        poses: list[PersonPose] = []
        for raw_pose, raw_confidence in zip(
            raw_keypoints,
            raw_confidences,
            strict=True,
        ):
            if len(raw_pose) != COCO_KEYPOINT_COUNT:
                raise PoseInferenceError(
                    "O modelo de pose retornou um esqueleto incompatível."
                )
            keypoints = tuple(_keypoint_from_row(row) for row in raw_pose)
            poses.append(
                PersonPose(
                    confidence=float(raw_confidence),
                    keypoints=keypoints,
                )
            )
        return tuple(poses)


def _keypoint_from_row(row: object) -> PoseKeypoint:
    if not isinstance(row, (list, tuple)) or len(row) not in {2, 3}:
        raise PoseInferenceError("O modelo de pose retornou keypoints inválidos.")
    confidence = float(row[2]) if len(row) == 3 else 1.0
    try:
        return PoseKeypoint(float(row[0]), float(row[1]), confidence)
    except (TypeError, ValueError) as error:
        raise PoseInferenceError(
            "O modelo de pose retornou keypoints inválidos."
        ) from error


def _configure_runtime(config_directory: Path | None) -> None:
    if config_directory is None:
        return
    try:
        config_directory.mkdir(parents=True, exist_ok=True)
        matplotlib_directory = config_directory / "matplotlib"
        matplotlib_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PoseModelUnavailableError(
            "Não foi possível preparar o runtime local do modelo de pose."
        ) from error
    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_directory))
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_directory))
    os.environ.setdefault("YOLO_OFFLINE", "true")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise PoseModelUnavailableError(
            "Não foi possível validar o modelo de pose."
        ) from error
    return digest.hexdigest()
