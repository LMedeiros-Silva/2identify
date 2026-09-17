"""Resolve workstation camera credentials without changing the shared catalog."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from dotenv import dotenv_values

from app.core import config


class LocalCameraSourceError(ValueError):
    """A local override is invalid; the message never includes its value."""


def resolve_camera_source(camera_id: int, catalog_source: str) -> str:
    """Prefer the process, Admin .env, then the adjacent Operator .env by ID."""
    key = f"CAMERA_SOURCE_{camera_id}"
    source = os.environ.get(key)
    if not source or not source.strip():
        for env_file in (
            config.PROJECT_ROOT / ".env",
            config.PROJECT_ROOT.parent / "2identify_operador" / ".env",
        ):
            source = dotenv_values(env_file).get(key)
            if source and source.strip():
                break
    if not source or not source.strip():
        return catalog_source.strip()

    source = source.strip()
    if catalog_source.strip().isdecimal():
        if source.isdecimal():
            return source
    else:
        try:
            parsed = urlsplit(source)
            if (
                parsed.scheme.casefold() in {"rtsp", "http", "https"}
                and parsed.hostname
                and (parsed.port is None or parsed.port > 0)
            ):
                return source
        except ValueError:
            pass
    raise LocalCameraSourceError(
        f"Fonte local inválida para a câmera {camera_id}. "
        f"Confira {key} no .env do Admin ou do Operator."
    )
