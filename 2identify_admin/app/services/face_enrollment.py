"""YuNet/SFace employee enrollment with three validated camera samples."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from app.domain.employees import FaceTemplateDraft
from app.services.model_artifacts import native_model_path

Frame = NDArray[np.uint8]
Embedding = NDArray[np.float32]


class FaceCaptureError(ValueError):
    pass


class FaceAngle(StrEnum):
    FRONTAL = "frontal"
    ESQUERDA = "esquerda"
    DIREITA = "direita"


@dataclass(frozen=True, slots=True)
class FaceObservation:
    box: tuple[float, float, float, float]
    landmarks: tuple[tuple[float, float], ...]
    confidence: float
    raw: tuple[float, ...] = field(repr=False)


class FaceModels(Protocol):
    def detect(self, frame: Frame) -> tuple[FaceObservation, ...]: ...
    def encode(self, frame: Frame, face: FaceObservation) -> Embedding: ...


class OpenCvFaceModels:
    """The same YuNet and SFace checkpoints used by Operator Face ID."""

    def __init__(self, detector_path: Path, recognizer_path: Path) -> None:
        if not detector_path.is_file() or not recognizer_path.is_file():
            raise FaceCaptureError("Modelos YuNet/SFace não encontrados nesta estação.")
        try:
            compatible_detector = native_model_path(detector_path)
            compatible_recognizer = native_model_path(recognizer_path)
            self._detector = cv2.FaceDetectorYN.create(
                str(compatible_detector), "", (320, 320), 0.90, 0.3, 5000
            )
            self._recognizer = cv2.FaceRecognizerSF.create(str(compatible_recognizer), "")
        except (cv2.error, OSError) as error:
            raise FaceCaptureError("Não foi possível carregar YuNet/SFace.") from error

    def detect(self, frame: Frame) -> tuple[FaceObservation, ...]:
        try:
            height, width = frame.shape[:2]
            self._detector.setInputSize((width, height))
            _, raw_faces = self._detector.detect(frame)
        except cv2.error as error:
            raise FaceCaptureError("Falha na detecção facial.") from error
        if raw_faces is None:
            return ()
        result = []
        for raw in np.asarray(raw_faces, dtype=np.float32):
            result.append(FaceObservation(
                box=tuple(float(value) for value in raw[:4]),
                landmarks=tuple(
                    (float(raw[index]), float(raw[index + 1]))
                    for index in range(4, 14, 2)
                ),
                confidence=float(raw[14]),
                raw=tuple(float(value) for value in raw),
            ))
        return tuple(result)

    def encode(self, frame: Frame, face: FaceObservation) -> Embedding:
        try:
            aligned = self._recognizer.alignCrop(
                frame, np.asarray(face.raw, dtype=np.float32).reshape(1, -1)
            )
            values = self._recognizer.feature(aligned)
        except cv2.error as error:
            raise FaceCaptureError("Não foi possível extrair o template SFace.") from error
        vector = np.asarray(values, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if len(vector) != 128 or not isfinite(norm) or norm <= 1e-12:
            raise FaceCaptureError("O template facial produzido é inválido.")
        return np.asarray(vector / norm, dtype=np.float32)


def _yaw(face: FaceObservation) -> float:
    left_eye, right_eye, nose = face.landmarks[:3]
    eye_span = abs(left_eye[0] - right_eye[0])
    if eye_span < 4:
        raise FaceCaptureError("Pontos faciais insuficientes. Repita a captura.")
    return (nose[0] - (left_eye[0] + right_eye[0]) / 2) / eye_span


def validate_face(frame: Frame, face: FaceObservation, angle: FaceAngle) -> None:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise FaceCaptureError("Imagem da câmera inválida.")
    if face.confidence < 0.90:
        raise FaceCaptureError("Confiança facial baixa. Repita a captura.")
    x, y, width, height = face.box
    frame_height, frame_width = frame.shape[:2]
    if width < max(60, frame_width * 0.12) or height < max(60, frame_height * 0.12):
        raise FaceCaptureError("Aproxime o rosto da câmera.")
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(frame_width, int(x + width)), min(frame_height, int(y + height))
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        raise FaceCaptureError("Rosto fora da imagem.")
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if not 45 <= brightness <= 215 or sharpness < 40:
        raise FaceCaptureError("Melhore a iluminação e mantenha o rosto nítido.")
    yaw = _yaw(face)
    if (
        angle is FaceAngle.FRONTAL and abs(yaw) > 0.22
        or angle is FaceAngle.ESQUERDA and not -0.9 <= yaw <= -0.16
        or angle is FaceAngle.DIREITA and not 0.16 <= yaw <= 0.9
    ):
        raise FaceCaptureError(f"Posicione o rosto para a captura {angle.value}.")


class FaceEnrollment:
    def __init__(self, models: FaceModels) -> None:
        self._models = models
        self._samples: dict[FaceAngle, Embedding] = {}

    @property
    def captured(self) -> frozenset[FaceAngle]:
        return frozenset(self._samples)

    def capture(self, frame: Frame, angle: FaceAngle) -> Embedding:
        faces = self._models.detect(frame)
        if len(faces) != 1:
            raise FaceCaptureError(
                "Nenhum rosto detectado." if not faces else "Há vários rostos na imagem."
            )
        validate_face(frame, faces[0], angle)
        embedding = self._models.encode(frame, faces[0])
        self._samples[angle] = embedding
        return embedding

    def template(self) -> FaceTemplateDraft:
        return combine_samples(self._samples)


def combine_samples(samples: dict[FaceAngle, Embedding]) -> FaceTemplateDraft:
    if frozenset(samples) != frozenset(FaceAngle):
        raise FaceCaptureError("Capture frontal, esquerda e direita.")
    combined = np.mean(np.stack([samples[angle] for angle in FaceAngle]), axis=0)
    norm = float(np.linalg.norm(combined))
    if len(combined) != 128 or not isfinite(norm) or norm <= 1e-12:
        raise FaceCaptureError("Não foi possível combinar as capturas faciais.")
    normalized = combined / norm
    return FaceTemplateDraft(
        model_id="opencv_sface_2021dec",
        embedding=tuple(float(value) for value in normalized),
    )


__all__ = [
    "FaceAngle", "FaceCaptureError", "FaceEnrollment", "FaceObservation",
    "OpenCvFaceModels", "validate_face",
    "combine_samples",
]
