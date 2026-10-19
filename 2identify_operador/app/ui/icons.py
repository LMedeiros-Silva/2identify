"""Line icons for the Operator shell, rendered from inline SVG in the theme colors."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "works": (
        '<path d="m12 2 10 5-10 5L2 7z"/>'
        '<path d="m2 17 10 5 10-5"/>'
        '<path d="m2 12 10 5 10-5"/>'
    ),
    "logout": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<path d="m16 17 5-5-5-5"/>'
        '<path d="M21 12H9"/>'
    ),
}


def _pixmap(name: str, color: str, size: int) -> QPixmap:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.9" stroke-linecap="round" '
        f'stroke-linejoin="round">{_PATHS[name]}</svg>'
    )
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(
        painter, QRectF(0, 0, size * scale, size * scale)
    )
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def line_icon(name: str, color: str, *, active_color: str | None = None, size: int = 18) -> QIcon:
    """Return an icon whose checked/hovered state uses ``active_color``."""

    icon = QIcon()
    icon.addPixmap(_pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if active_color is not None:
        active = _pixmap(name, active_color, size)
        icon.addPixmap(active, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(active, QIcon.Mode.Active, QIcon.State.Off)
        icon.addPixmap(active, QIcon.Mode.Active, QIcon.State.On)
    return icon


__all__ = ["line_icon"]
