"""Resolution-independent polygon editor drawn over the real camera image rect."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import CameraOption, NormalizedPoint, PolygonGeometry, RiskArea, RiskAreaDraft


class RiskAreaEditor(QWidget):
    """Store only normalized points while painting them over a letterboxed image."""

    geometry_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._image = QImage()
        self._points: list[NormalizedPoint] = []
        self._closed = False

    @property
    def points(self) -> tuple[NormalizedPoint, ...]:
        return tuple(self._points)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def set_image(self, image: QImage) -> None:
        self._image = image.copy()
        self.update()

    def set_geometry(self, geometry: PolygonGeometry) -> None:
        self._points = list(geometry.points)
        self._closed = True
        self.geometry_changed.emit()
        self.update()

    def image_rect(self) -> QRectF:
        if self._image.isNull() or self.width() <= 0 or self.height() <= 0:
            return QRectF()
        scaled = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            (self.width() - scaled.width()) / 2.0,
            (self.height() - scaled.height()) / 2.0,
            float(scaled.width()),
            float(scaled.height()),
        )

    def normalized_point_at(self, position: QPointF) -> NormalizedPoint | None:
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(position):
            return None
        return NormalizedPoint(
            min(1.0, max(0.0, (position.x() - rect.left()) / rect.width())),
            min(1.0, max(0.0, (position.y() - rect.top()) / rect.height())),
        )

    def close_polygon(self) -> bool:
        try:
            PolygonGeometry(tuple(self._points))
        except ValueError:
            return False
        self._closed = True
        self.geometry_changed.emit()
        self.update()
        return True

    def undo_last_point(self) -> None:
        self._closed = False
        if self._points:
            self._points.pop()
        self.geometry_changed.emit()
        self.update()

    def clear_points(self) -> None:
        self._points.clear()
        self._closed = False
        self.geometry_changed.emit()
        self.update()

    def geometry(self) -> PolygonGeometry:
        if not self._closed:
            raise ValueError("feche o polígono antes de salvar")
        return PolygonGeometry(tuple(self._points))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._closed:
            point = self.normalized_point_at(event.position())
            if point is not None:
                self._points.append(point)
                self.geometry_changed.emit()
                self.update()
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111827"))
        rect = self.image_rect()
        if not self._image.isNull():
            painter.drawImage(rect, self._image)
        if not self._points or rect.isEmpty():
            return
        visual = QPolygonF(
            [
                QPointF(
                    rect.left() + point.x * rect.width(),
                    rect.top() + point.y * rect.height(),
                )
                for point in self._points
            ]
        )
        painter.setPen(QPen(QColor("#FDB022"), 3))
        if len(visual) >= 2:
            painter.drawPolyline(visual)
        if self._closed and len(visual) >= 3:
            painter.drawLine(visual[-1], visual[0])
            painter.setBrush(QColor(253, 176, 34, 45))
            painter.drawPolygon(visual)
        painter.setBrush(QColor("#2563EB"))
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        for index, point in enumerate(visual, start=1):
            painter.drawEllipse(point, 6, 6)
            painter.drawText(point + QPointF(9, -9), str(index))


class RiskAreaEditorDialog(QDialog):
    def __init__(
        self,
        camera: CameraOption,
        image: QImage,
        existing: RiskArea | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._camera = camera
        self._existing = existing
        self.result_draft: RiskAreaDraft | None = None
        self.setWindowTitle(f"Configurar área de risco · {camera.name}")
        self.resize(980, 720)
        layout = QVBoxLayout(self)
        heading = QLabel(f"Câmera: {camera.name}")
        heading.setObjectName("risk_editor_title")
        layout.addWidget(heading)
        help_text = QLabel(
            "Clique somente dentro da imagem para adicionar os vértices. "
            "Os pontos serão salvos em coordenadas normalizadas."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.name_edit = QLineEdit(existing.name if existing else "Área de risco")
        self.name_edit.setPlaceholderText("Nome da área de risco")
        layout.addWidget(self.name_edit)
        self.editor = RiskAreaEditor()
        self.editor.set_image(image)
        if existing is not None:
            self.editor.set_geometry(existing.geometry)
        layout.addWidget(self.editor, 1)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        toolbar = QHBoxLayout()
        undo = QPushButton("Desfazer último ponto")
        undo.clicked.connect(self.editor.undo_last_point)
        toolbar.addWidget(undo)
        clear = QPushButton("Limpar pontos")
        clear.clicked.connect(self.editor.clear_points)
        toolbar.addWidget(clear)
        close = QPushButton("Fechar polígono")
        close.clicked.connect(self._close_polygon)
        toolbar.addWidget(close)
        toolbar.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        toolbar.addWidget(cancel)
        save = QPushButton("Salvar área")
        save.setObjectName("primary_action")
        save.clicked.connect(self._save)
        toolbar.addWidget(save)
        layout.addLayout(toolbar)
        self.editor.geometry_changed.connect(self._update_status)
        self._update_status()

    def _close_polygon(self) -> None:
        if not self.editor.close_polygon():
            QMessageBox.warning(
                self,
                "Polígono inválido",
                "Use pelo menos três pontos sem repetição, cruzamentos ou área zero.",
            )

    def _update_status(self) -> None:
        state = "fechado" if self.editor.is_closed else "aberto"
        self.status_label.setText(f"{len(self.editor.points)} ponto(s) · polígono {state}")

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nome obrigatório", "Informe o nome da área de risco.")
            return
        try:
            geometry = self.editor.geometry()
        except ValueError as error:
            QMessageBox.warning(self, "Área inválida", str(error))
            return
        self.result_draft = RiskAreaDraft(
            camera_id=self._camera.id,
            name=name,
            geometry=geometry,
            active=self._existing.active if self._existing else True,
        )
        self.accept()


__all__ = ["RiskAreaEditor", "RiskAreaEditorDialog"]
