"""Admin design-system stylesheets resolve every token and keep the font floor."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ui.styles import login_stylesheet, main_window_stylesheet


@pytest.mark.parametrize("stylesheet", [main_window_stylesheet(), login_stylesheet()])
def test_stylesheet_tokens_are_resolved(stylesheet: str) -> None:
    assert "{{" not in stylesheet
    assert "}}" not in stylesheet


@pytest.mark.parametrize("stylesheet", [main_window_stylesheet(), login_stylesheet()])
def test_no_font_is_smaller_than_the_badge_floor(stylesheet: str) -> None:
    sizes = [int(size) for size in re.findall(r"font-size:\s*(\d+)px", stylesheet)]

    assert min(sizes) >= 11


def test_stylesheet_icons_exist() -> None:
    icons = re.findall(r"url\(([^)]+)\)", main_window_stylesheet())

    assert icons
    assert all(Path(icon).is_file() for icon in icons)
