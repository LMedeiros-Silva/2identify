"""Design-system tokens resolve completely and keep the projector font floor."""

from __future__ import annotations

import re

from app.ui.styles import load_application_stylesheet
from app.ui.theme import TOKENS, apply_theme


def test_every_stylesheet_token_is_resolved() -> None:
    stylesheet = load_application_stylesheet()

    assert "{{" not in stylesheet
    assert "}}" not in stylesheet


def test_no_font_is_smaller_than_the_badge_floor() -> None:
    stylesheet = load_application_stylesheet()
    sizes = [int(size) for size in re.findall(r"font-size:\s*(\d+)px", stylesheet)]

    assert sizes
    assert min(sizes) >= 11


def test_unknown_tokens_stay_visible_instead_of_becoming_empty() -> None:
    assert apply_theme("color: {{brand_600}}; x: {{missing}};") == (
        f"color: {TOKENS['brand_600']}; x: {{{{missing}}}};"
    )
