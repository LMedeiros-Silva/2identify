"""2Identify design tokens shared by every Operator stylesheet.

QSS has no variables, so the stylesheets reference tokens as ``{{name}}`` and
``apply_theme`` substitutes them when the stylesheet is loaded. The palette keeps
blue as the brand color; green, yellow and red are reserved for safety states.
The same values are mirrored in the Admin application (``app/ui/theme.py``).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

TOKENS: dict[str, str] = {
    # Brand blue (logo mark #1687F8, primary #1677D2).
    "brand_50": "#EEF6FD",
    "brand_100": "#E1EFFB",
    "brand_200": "#C3DFF5",
    "brand_300": "#94C9EF",
    "brand_400": "#51A8FF",
    "brand_500": "#1687F8",
    "brand_600": "#1677D2",
    "brand_700": "#0F5CA5",
    "brand_800": "#0B4A86",
    # Navigation and dark surfaces (sidebar, login brand panel, video).
    "nav_950": "#061423",
    "nav_900": "#0A1B30",
    "nav_850": "#0D2037",
    "nav_800": "#10243E",
    "nav_700": "#183450",
    "nav_600": "#24445F",
    "nav_500": "#315775",
    "nav_text": "#B6C7D9",
    "nav_muted": "#8FA4BA",
    # Neutrals for text, borders and surfaces.
    "ink_900": "#10243E",
    "ink_800": "#18314C",
    "ink_700": "#2C4258",
    "ink_600": "#4A5D73",
    "ink_500": "#5F7186",
    "ink_400": "#8394A6",
    "ink_300": "#AEBCCB",
    "line_300": "#C7D3DF",
    "line_200": "#D8E2EC",
    "line_100": "#E6EDF3",
    "surface_0": "#F3F6FA",
    "surface_1": "#FFFFFF",
    "surface_2": "#F8FAFC",
    "surface_3": "#EDF2F6",
    # Safety states only.
    "safe_800": "#15563A",
    "safe_700": "#1C6D49",
    "safe_600": "#238056",
    "safe_500": "#28A96F",
    "safe_300": "#9CD8B7",
    "safe_100": "#E5F7ED",
    "safe_50": "#F0FAF4",
    "warn_800": "#563F12",
    "warn_700": "#7A5B1B",
    "warn_600": "#8A651D",
    "warn_500": "#C78620",
    "warn_300": "#EFD48D",
    "warn_100": "#FFF7DF",
    "warn_50": "#FFFBF0",
    "crit_800": "#8E2C2C",
    "crit_700": "#A23838",
    "crit_600": "#C93D46",
    "crit_500": "#DC4C55",
    "crit_300": "#EFB9B5",
    "crit_100": "#FCEBEA",
    "crit_50": "#FFF5F4",
    # Typography (projector legibility: 12 px floor, 11 px only for short badges).
    "font_family": '"Segoe UI", "Inter", sans-serif',
    "font_badge": "11px",
    "font_label": "12px",
    "font_small": "13px",
    "font_body": "14px",
    "font_panel": "16px",
    "font_section": "18px",
    "font_page": "22px",
    "font_kpi": "28px",
    "font_title": "26px",
    # Shape.
    "radius_sm": "6px",
    "radius_md": "8px",
    "radius_lg": "12px",
    "control_height": "40px",
}

_TOKEN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def apply_theme(stylesheet: str, tokens: dict[str, str] | None = None) -> str:
    """Replace ``{{token}}`` placeholders; unknown tokens are logged and left visible."""

    values = TOKENS if tokens is None else tokens

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            logger.warning("stylesheet_unknown_token", extra={"token": name})
            return match.group(0)
        return values[name]

    return _TOKEN.sub(replace, stylesheet)
