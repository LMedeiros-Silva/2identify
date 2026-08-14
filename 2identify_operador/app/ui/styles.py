"""Application stylesheet loader."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.constants import APPLICATION_STYLESHEET, STYLES_DIRECTORY

logger = logging.getLogger(__name__)


def load_application_stylesheet() -> str:
    """Load base styles first, followed by screen-specific QSS files."""

    stylesheets = [
        APPLICATION_STYLESHEET,
        *sorted(
            path
            for path in STYLES_DIRECTORY.glob("*.qss")
            if path != APPLICATION_STYLESHEET
        ),
    ]
    return "\n\n".join(_read_stylesheet(path) for path in stylesheets)


def _read_stylesheet(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.exception(
            "application_stylesheet_load_failed",
            extra={"path": str(path)},
        )
        return ""
