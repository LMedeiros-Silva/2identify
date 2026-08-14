"""Industrial product branding used by the authentication screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class IndustrialBrandPanel(QFrame):
    """Brand panel with product context and a subtle code-drawn grid."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("loginBrandPanel")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(64, 50, 64, 46)
        layout.setSpacing(0)
        layout.addLayout(self._build_header())
        layout.addStretch(2)
        layout.addWidget(self._label("MONITORAMENTO INTELIGENTE", "brandEyebrow"))

        headline = self._label(
            "Segurança industrial\ncom inteligência em\ntempo real.",
            "brandHeadline",
        )
        headline.setWordWrap(True)
        layout.addWidget(headline)
        layout.addSpacing(18)

        supporting_text = self._label(
            "Identificação, conformidade e resposta conectadas para apoiar "
            "operações industriais mais seguras.",
            "brandSupportingText",
        )
        supporting_text.setWordWrap(True)
        supporting_text.setMaximumWidth(480)
        layout.addWidget(supporting_text)
        layout.addSpacing(38)

        features = QHBoxLayout()
        features.setSpacing(18)
        features.addWidget(self._feature_item("01", "IDENTIFICAR"))
        features.addWidget(self._feature_item("02", "VERIFICAR"))
        features.addWidget(self._feature_item("03", "PROTEGER"))
        layout.addLayout(features)
        layout.addStretch(3)

        layout.addWidget(
            self._label(
                "2Identify · Tecnologia aplicada à prevenção",
                "brandFooter",
            )
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        grid_pen = QPen(QColor(67, 139, 211, 24))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        spacing = 48
        for x_position in range(0, self.width(), spacing):
            painter.drawLine(x_position, 0, x_position, self.height())
        for y_position in range(0, self.height(), spacing):
            painter.drawLine(0, y_position, self.width(), y_position)

        accent_pen = QPen(QColor(50, 155, 255, 82))
        accent_pen.setWidth(2)
        painter.setPen(accent_pen)
        painter.drawLine(self.width() - 180, 0, self.width(), 180)
        painter.drawLine(0, self.height() - 110, 110, self.height())

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)

        mark = self._label("2I", "brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(42, 42)
        header.addWidget(mark)

        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self._label("2IDENTIFY", "loginBrandName"))
        names.addWidget(self._label("OPERATOR", "loginProductName"))
        header.addLayout(names)
        header.addStretch()
        return header

    @staticmethod
    def _feature_item(number: str, title: str) -> QWidget:
        item = QFrame()
        item.setObjectName("brandFeature")
        layout = QVBoxLayout(item)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setSpacing(6)
        layout.addWidget(IndustrialBrandPanel._label(number, "featureNumber"))
        layout.addWidget(IndustrialBrandPanel._label(title, "featureTitle"))
        return item

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

