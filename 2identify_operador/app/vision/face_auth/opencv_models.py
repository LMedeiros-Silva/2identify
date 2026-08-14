"""OpenCV YuNet and SFace adapters."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.vision.face_auth.errors import (
    FaceAuthenticationProcessingError,
    FaceAuthenticationUnavailableError,
)
from app.vision.face_auth.types import BoundingBox, DetectedFace, Embedding, Frame
from app.vision.model_artifacts import native_model_path


class YuNetFaceDetector:
    """Detect faces and five landmarks using OpenCV's FaceDetectorYN API."""

    def __init__(
        self,
        model_path: Path,
        score_threshold: float,
        nms_threshold: float = 0.3,
        top_k: int = 5_000,
    ) -> None:
        _require_model(model_path, "detector facial YuNet")
        compatible_model_path = native_model_path(model_path)
        try:
            self._detector: Any = cv2.FaceDetectorYN.create(
                str(compatible_model_path),
                "",
                (320, 320),
                score_threshold,
                nms_threshold,
                top_k,
            )
        except cv2.error as error:
            raise FaceAuthenticationUnavailableError(
                "Não foi possível carregar o detector facial configurado."
            ) from error

    def detect(self, frame: Frame) -> Sequence[DetectedFace]:
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise FaceAuthenticationProcessingError("O frame da câmera possui formato inválido.")

        height, width = frame.shape[:2]
        try:
            self._detector.setInputSize((width, height))
            _result, detections = self._detector.detect(frame)
        except cv2.error as error:
            raise FaceAuthenticationProcessingError(
                "Falha ao executar a detecção facial."
            ) from error

        if detections is None:
            return ()

        faces: list[DetectedFace] = []
        for raw_detection in np.asarray(detections, dtype=np.float32):
            raw_values = tuple(float(value) for value in raw_detection.tolist())
            landmarks = tuple(
                (float(raw_detection[index]), float(raw_detection[index + 1]))
                for index in range(4, 14, 2)
            )
            faces.append(
                DetectedFace(
                    bounding_box=BoundingBox(
                        x=float(raw_detection[0]),
                        y=float(raw_detection[1]),
                        width=float(raw_detection[2]),
                        height=float(raw_detection[3]),
                    ),
                    landmarks=landmarks,
                    confidence=float(raw_detection[14]),
                    raw_values=raw_values,
                )
            )
        return faces


class SFaceEncoder:
    """Align faces and generate normalized SFace embeddings."""

    def __init__(self, model_path: Path) -> None:
        _require_model(model_path, "reconhecedor facial SFace")
        compatible_model_path = native_model_path(model_path)
        try:
            self._recognizer: Any = cv2.FaceRecognizerSF.create(
                str(compatible_model_path),
                "",
            )
        except cv2.error as error:
            raise FaceAuthenticationUnavailableError(
                "Não foi possível carregar o reconhecedor facial configurado."
            ) from error

    def encode(self, frame: Frame, face: DetectedFace) -> Embedding:
        detection = np.asarray(face.raw_values, dtype=np.float32).reshape(1, -1)
        try:
            aligned_face = self._recognizer.alignCrop(frame, detection)
            feature = self._recognizer.feature(aligned_face)
        except cv2.error as error:
            raise FaceAuthenticationProcessingError(
                "Não foi possível extrair as características do rosto."
            ) from error

        embedding = np.asarray(feature, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(embedding))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise FaceAuthenticationProcessingError("O embedding facial gerado é inválido.")
        return np.asarray(embedding / norm, dtype=np.float32)


def _require_model(model_path: Path, description: str) -> None:
    if not model_path.is_file():
        raise FaceAuthenticationUnavailableError(
            f"Arquivo do {description} não encontrado: {model_path.name}."
        )
