"""2Identify design tokens shared by every Admin stylesheet.

QSS has no variables, so the stylesheets reference tokens as ``{{name}}`` and
``apply_theme`` substitutes them when the stylesheet is loaded. The palette keeps
blue as the brand color; green, yellow and red are reserved for safety states.
The same values are mirrored in the Operator application (``app/ui/theme.py``).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

TOKENS: dict[str, str] = {
    # Brand blue (logo mark #1687F8, primary #1677D2).
    "brand_50": "#E7F1FC",
    "brand_100": "#E1EFFB",
    "brand_200": "#B9D6F5",
    "brand_300": "#94C9EF",
    "brand_400": "#51A8FF",
    "brand_500": "#1687F8",
    "brand_600": "#1677D2",
    "brand_700": "#0F5CA5",
    "brand_800": "#0B4A86",
    # Navigation and dark surfaces (sidebar, login brand panel, video).
    "nav_950": "#0A1A33",
    "nav_900": "#10264A",
    "nav_850": "#142D52",
    "nav_800": "#183459",
    "nav_700": "#24456F",
    "nav_600": "#2E5583",
    "nav_500": "#3B6497",
    "nav_text": "#C9D6E8",
    "nav_muted": "#7F93B3",
    # Neutrals for text, borders and surfaces.
    "ink_900": "#13233F",
    "ink_800": "#1C2E4C",
    "ink_700": "#2E4060",
    "ink_600": "#44546D",
    "ink_500": "#66758C",
    "ink_400": "#8592A6",
    "ink_300": "#AEBCCB",
    "line_300": "#C9D3DF",
    "line_200": "#DCE3EC",
    "line_100": "#E8EDF3",
    "surface_0": "#F2F5F9",
    "surface_1": "#FFFFFF",
    "surface_2": "#F7FAFD",
    "surface_3": "#EEF1F6",
    # Safety states only.
    "safe_800": "#105A37",
    "safe_700": "#17784A",
    "safe_600": "#1E8A57",
    "safe_500": "#25A066",
    "safe_300": "#A9DBBF",
    "safe_100": "#E5F4EC",
    "safe_50": "#F1FAF5",
    "warn_800": "#5B3A00",
    "warn_700": "#9A5B00",
    "warn_600": "#A86400",
    "warn_500": "#E59A1A",
    "warn_300": "#F3D597",
    "warn_100": "#FFF4DC",
    "warn_50": "#FFFAEE",
    "crit_800": "#8A1C1C",
    "crit_700": "#A82020",
    "crit_600": "#C62828",
    "crit_500": "#D84343",
    "crit_300": "#F2B8B8",
    "crit_100": "#FDECEC",
    "crit_50": "#FFF6F6",
    # Inconclusive: the AI could neither confirm nor deny (slate, dashed border).
    "inc_700": "#4F5F78",
    "inc_300": "#AEB9CA",
    "inc_100": "#EEF1F6",
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
