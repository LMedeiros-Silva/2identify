"""Stable product constants and canonical project paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIRECTORY = PROJECT_ROOT / "assets"
STYLES_DIRECTORY = ASSETS_DIRECTORY / "styles"
APPLICATION_STYLESHEET = STYLES_DIRECTORY / "base.qss"

APPLICATION_NAME = "2Identify Operator"
ORGANIZATION_NAME = "2Identify"
LOG_FILE_NAME = "operator.log"
