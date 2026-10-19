"""Line icons for the Admin shell, rendered from inline SVG in the theme colors."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "dashboard": (
        '<rect x="3" y="3" width="7" height="9" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="5" rx="1.5"/>'
        '<rect x="14" y="12" width="7" height="9" rx="1.5"/>'
        '<rect x="3" y="16" width="7" height="5" rx="1.5"/>'
    ),
    "alertas": (
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
    ),
    "epis": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "operacoes": (
        '<path d="m12 2 10 5-10 5L2 7z"/>'
        '<path d="m2 17 10 5 10-5"/>'
        '<path d="m2 12 10 5 10-5"/>'
    ),
    "funcionarios": (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    "relatorios": (
        '<path d="M3 3v18h18"/>'
        '<path d="M8 17v-6"/>'
        '<path d="M13 17V6"/>'
        '<path d="M18 17v-4"/>'
    ),
    "configuracoes": (
        '<path d="M4 21v-7"/><path d="M4 10V3"/>'
        '<path d="M12 21v-9"/><path d="M12 8V3"/>'
        '<path d="M20 21v-5"/><path d="M20 12V3"/>'
        '<path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>'
    ),
    "sair": (
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
