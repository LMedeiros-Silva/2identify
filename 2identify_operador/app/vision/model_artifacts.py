"""Compatibility staging for native runtimes that cannot open Unicode paths."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def native_model_path(source: Path) -> Path:
    """Return an ASCII path, staging immutable public models only when necessary."""

    resolved_source = source.resolve()
    if _is_ascii(str(resolved_source)):
        return resolved_source

    digest = _sha256(resolved_source)[:16]
    cache_directory = Path(tempfile.gettempdir()) / "2identify-models"
    cache_directory.mkdir(parents=True, exist_ok=True)
    destination = cache_directory / f"{digest}-{resolved_source.name}"
    if destination.is_file() and destination.stat().st_size == resolved_source.stat().st_size:
        return destination

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copyfile(resolved_source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

