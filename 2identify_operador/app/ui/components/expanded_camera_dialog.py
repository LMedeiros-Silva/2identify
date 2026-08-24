"""Reusable full-screen presentation for camera frames and overlays."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.components.camera_frame_view import CameraFrameView


class ExpandedCameraDialog(QDialog):
    """Show a camera presentation in a dedicated full-screen window."""

    closed = Signal()

    def __init__(
        self,
        *,
        parent: QWidget,
        window_title: str,
        header_text: str,
        preview_object_name: str,
        aspect_ratio_mode: Qt.AspectRatioMode = (Qt.AspectRatioMode.KeepAspectRatioByExpanding),
    ) -> None:
        super().__init__(parent)
        self.setObjectName("expandedCameraDialog")
        self.setWindowTitle(window_title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(QLabel(header_text))
        header.addStretch(1)
        close_button = QPushButton("VOLTAR · ESC")
        close_button.setObjectName("expandedCameraCloseButton")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        layout.addLayout(header)

        self.camera_view = CameraFrameView(
            preview_object_name,
            aspect_ratio_mode=aspect_ratio_mode,
        )
        layout.addWidget(self.camera_view, 1)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        super().closeEvent(event)


__all__ = ["ExpandedCameraDialog"]
