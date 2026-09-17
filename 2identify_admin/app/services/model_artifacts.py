"""Give OpenCV native loaders an ASCII path for immutable public model files."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def native_model_path(source: Path) -> Path:
    """Stage a model only when the installed path contains non-ASCII characters."""
    resolved = source.resolve()
    try:
        str(resolved).encode("ascii")
    except UnicodeEncodeError:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()[:16]
        directory = Path(tempfile.gettempdir()) / "2identify-models"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest}-{resolved.name}"
        if destination.is_file() and destination.stat().st_size == resolved.stat().st_size:
            return destination
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            shutil.copyfile(resolved, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
    return resolved


__all__ = ["native_model_path"]
