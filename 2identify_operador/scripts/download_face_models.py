"""Download verified OpenCV Zoo models required by local Face ID."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIRECTORY = PROJECT_ROOT / "models"


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    filename: str
    url: str
    sha256: str


MODELS = (
    ModelArtifact(
        filename="face_detection_yunet_2023mar.onnx",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_detection_yunet/face_detection_yunet_2023mar.onnx"
        ),
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    ModelArtifact(
        filename="face_recognition_sface_2021dec.onnx",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_recognition_sface/face_recognition_sface_2021dec.onnx"
        ),
        sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
)


def main() -> int:
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for artifact in MODELS:
        destination = MODEL_DIRECTORY / artifact.filename
        if destination.is_file() and _sha256(destination) == artifact.sha256:
            print(f"OK: {artifact.filename}")
            continue

        temporary = destination.with_suffix(destination.suffix + ".download")
        print(f"Baixando {artifact.filename}...")
        try:
            urllib.request.urlretrieve(artifact.url, temporary)
            actual_hash = _sha256(temporary)
            if actual_hash != artifact.sha256:
                raise RuntimeError(
                    f"SHA-256 inválido para {artifact.filename}: {actual_hash}"
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Instalado: {destination}")
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

