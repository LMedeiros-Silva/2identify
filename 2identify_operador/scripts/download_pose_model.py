"""Download the pinned public YOLO pose checkpoint and verify its SHA-256."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "pose" / "yolo11n-pose.pt"
MODEL_URL = (
    "https://github.com/ultralytics/assets/releases/download/"
    "v8.4.0/yolo11n-pose.pt"
)
EXPECTED_SHA256 = "869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0"


def main() -> int:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.is_file() and _sha256(MODEL_PATH) == EXPECTED_SHA256:
        print(f"Modelo de pose já validado: {MODEL_PATH}")
        return 0

    descriptor, temporary_name = tempfile.mkstemp(
        prefix="yolo11n-pose-",
        suffix=".pt",
        dir=MODEL_PATH.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        urllib.request.urlretrieve(MODEL_URL, temporary)  # noqa: S310
        if _sha256(temporary) != EXPECTED_SHA256:
            raise RuntimeError("O modelo baixado não corresponde ao SHA-256 aprovado.")
        os.replace(temporary, MODEL_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Modelo de pose instalado: {MODEL_PATH}")
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
