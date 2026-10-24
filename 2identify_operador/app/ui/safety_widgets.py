"""Safety-state building blocks shared by the Operator screens.

A safety state is always shown as colour + shape + word, so it reads on a
projector and for colour-blind viewers: octagon = critical, triangle =
attention, check circle = compliant, dashed circle with "?" = inconclusive.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui.theme import TOKENS

TONES = ("crit", "warn", "safe", "inc", "neutral")

_TONE_COLORS = {
    "crit": TOKENS["crit_600"],
    "warn": TOKENS["warn_500"],
    "safe": TOKENS["safe_700"],
    "inc": TOKENS["inc_700"],
    "neutral": TOKENS["ink_500"],
}

_SHAPES = {
    "crit": (
        '<path fill="{c}" d="M8 1h8l7 7v8l-7 7H8l-7-7V8z"/>'
        '<path stroke="#fff" stroke-width="2.4" stroke-linecap="round" d="M12 6.5v7M12 17.2v.1"/>'
    ),
    "warn": (
        '<path fill="{c}" d="M12 1.5 23 21.5H1z"/>'
        '<path stroke="#fff" stroke-width="2.2" stroke-linecap="round" d="M12 8.5v6.5M12 18.2v.1"/>'
    ),
    "safe": (
        '<circle fill="{c}" cx="12" cy="12" r="11"/>'
        '<path stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round" '
        'stroke-linejoin="round" d="m7 12.3 3.3 3.3L17 8.8"/>'
    ),
    "inc": (
        '<circle fill="none" stroke="{c}" stroke-width="2" stroke-dasharray="3.2 2.4" '
        'cx="12" cy="12" r="10"/>'
        '<path stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round" '
        'd="M9.4 9.4a2.7 2.7 0 1 1 3.8 2.5c-.8.4-1.2.9-1.2 1.8M12 17v.1"/>'
    ),
    "neutral": '<circle fill="{c}" cx="12" cy="12" r="6"/>',
}


def state_pixmap(
    tone: str, size: int = 14, color: str | None = None, mark: str = "#fff"
) -> QPixmap:
    """Render the shape for ``tone`` (crit, warn, safe, inc) as a crisp pixmap.

    ``mark`` colours the "!" or check inside the shape, so a white shape can
    sit on a filled state block.
    """

    shape = _SHAPES.get(tone, _SHAPES["neutral"]).format(c=color or _TONE_COLORS.get(tone))
    shape = shape.replace('stroke="#fff"', f'stroke="{mark}"')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{shape}</svg>'
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(
        painter, QRectF(0, 0, size * scale, size * scale)
    )
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def _refresh(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class StateChip(QFrame):
    """Pill with shape icon and an upper-case word, styled by the ``tone`` property."""

    def __init__(
        self, text: str = "", tone: str = "neutral", *, big: bool = False, solid: bool = False
    ) -> None:
        super().__init__()
        self.setObjectName("state_chip")
        # Styled by property so callers may rename the chip for lookups.
        self.setProperty("chip", "state")
        self.setProperty("size", "big" if big else "normal")
        # Solid chips sit on video: filled with the state colour, white text.
        self.setProperty("fill", "solid" if solid else "soft")
        self._solid = solid
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8 if not big else 11, 0, 10 if not big else 14, 0)
        layout.setSpacing(6)
        self._icon = QLabel()
        self._icon.setObjectName("state_chip_icon")
        layout.addWidget(self._icon)
        self._text = QLabel()
        self._text.setObjectName("state_chip_text")
        self._text.setTextFormat(Qt.TextFormat.PlainText)
        font = QFont(self._text.font())
        font.setCapitalization(QFont.Capitalization.AllUppercase)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
        self._text.setFont(font)
        layout.addWidget(self._text)
        self._big = big
        self.set_state(text, tone)

    def set_state(self, text: str, tone: str) -> None:
        self._text.setText(text)
        size = 16 if self._big else 13
        if self._solid:
            self._icon.setPixmap(
                state_pixmap(tone, size, color="#fff", mark=_TONE_COLORS.get(tone, "#000"))
            )
        else:
            self._icon.setPixmap(state_pixmap(tone, size))
        if self.property("tone") != tone:
            self.setProperty("tone", tone)
            for widget in (self, self._text):
                _refresh(widget)

    def text(self) -> str:
        return self._text.text()

    def tone(self) -> str:
        return str(self.property("tone"))


__all__ = ["TONES", "StateChip", "state_pixmap"]
