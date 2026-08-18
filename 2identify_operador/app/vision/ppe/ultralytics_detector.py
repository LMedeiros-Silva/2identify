"""Ultralytics YOLO adapter isolated from workers and presentation code."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any

from app.vision.ppe.errors import PpeInferenceError, PpeModelUnavailableError
from app.vision.ppe.types import DetectionBox, PpeDetection
from app.vision.types import Frame

ModelFactory = Callable[..., Any]


class UltralyticsPpeDetector:
    """Load one local YOLO checkpoint and normalize its box results."""

    def __init__(
        self,
        model_path: Path,
        confidence_threshold: float,
        iou_threshold: float,
        image_size: int,
        device: str,
        expected_sha256: str | None = None,
        config_directory: Path | None = None,
        model_factory: ModelFactory | None = None,
    ) -> None:
        if not model_path.is_file() or model_path.suffix.casefold() != ".pt":
            raise PpeModelUnavailableError(
                "O modelo de detecção de EPIs não foi encontrado."
            )
        if (
            expected_sha256 is not None
            and _file_sha256(model_path) != expected_sha256.casefold()
        ):
            raise PpeModelUnavailableError(
                "A verificação de integridade do modelo de EPIs falhou."
            )

        try:
            _configure_runtime(config_directory)
            factory = model_factory or import_module("ultralytics").YOLO
            self._model = factory(str(model_path), task="detect")
            self._class_names = _normalize_class_names(self._model.names)
        except PpeModelUnavailableError:
            raise
        except Exception as error:
            raise PpeModelUnavailableError(
                "Não foi possível carregar o modelo de detecção de EPIs."
            ) from error

        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._image_size = image_size
        self._device = device

    @property
    def class_names(self) -> tuple[str, ...]:
        return self._class_names

    def detect(self, frame: Frame) -> tuple[PpeDetection, ...]:
        """Run one local prediction and return normalized raw observations."""

        try:
            results = self._model.predict(
                source=frame,
                conf=self._confidence_threshold,
                iou=self._iou_threshold,
                imgsz=self._image_size,
                device=self._device,
                verbose=False,
            )
            if not results:
                return ()
            boxes = results[0].boxes
            if boxes is None:
                return ()
            coordinates = boxes.xyxy.detach().cpu().tolist()
            class_ids = boxes.cls.detach().cpu().tolist()
            confidences = boxes.conf.detach().cpu().tolist()
        except Exception as error:
            raise PpeInferenceError(
                "O modelo de EPIs falhou ao processar a imagem da câmera."
            ) from error

        detections: list[PpeDetection] = []
        for coordinates_row, raw_class_id, raw_confidence in zip(
            coordinates,
            class_ids,
            confidences,
            strict=True,
        ):
            class_id = int(raw_class_id)
            class_name = (
                self._class_names[class_id]
                if 0 <= class_id < len(self._class_names)
                else f"classe_{class_id}"
            )
            x1, y1, x2, y2 = (float(value) for value in coordinates_row)
            detections.append(
                PpeDetection(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(raw_confidence),
                    box=DetectionBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )
        return tuple(detections)


def _normalize_class_names(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        try:
            ordered = [value[index] for index in range(len(value))]
        except (KeyError, TypeError) as error:
            raise PpeModelUnavailableError(
                "O modelo de EPIs possui classes inválidas."
            ) from error
    elif isinstance(value, Sequence) and not isinstance(value, str):
        ordered = list(value)
    else:
        raise PpeModelUnavailableError("O modelo de EPIs não informa suas classes.")

    normalized = tuple(str(item).strip().casefold() for item in ordered)
    if not normalized or any(not item for item in normalized):
        raise PpeModelUnavailableError("O modelo de EPIs possui classes inválidas.")
    return normalized


def _configure_runtime(config_directory: Path | None) -> None:
    if config_directory is None:
        return
    try:
        config_directory.mkdir(parents=True, exist_ok=True)
        matplotlib_directory = config_directory / "matplotlib"
        matplotlib_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PpeModelUnavailableError(
            "Não foi possível preparar o runtime local do modelo de EPIs."
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
        raise PpeModelUnavailableError(
            "Não foi possível validar o modelo de detecção de EPIs."
        ) from error
    return digest.hexdigest()
