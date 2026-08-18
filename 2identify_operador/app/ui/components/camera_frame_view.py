"""Reusable Qt-only surface for displaying owned camera frames."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QFrame, QSizePolicy


@dataclass(frozen=True, slots=True)
class CameraOverlayBox:
    """One presentation-only detection box in source-frame coordinates."""

    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        normalized_label = self.label.strip().replace("_", " ")
        coordinates = (self.x1, self.y1, self.x2, self.y2)
        if not normalized_label:
            raise ValueError("label do overlay não pode ser vazio")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence do overlay deve estar entre zero e um")
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("coordenadas do overlay devem ser finitas")
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("overlay possui limites invertidos")
        object.__setattr__(self, "label", normalized_label)


@dataclass(frozen=True, slots=True)
class CameraFrameOverlay:
    """Boxes produced for one source-frame geometry."""

    boxes: tuple[CameraOverlayBox, ...]
    source_width: int
    source_height: int

    def __post_init__(self) -> None:
        if self.source_width <= 0 or self.source_height <= 0:
            raise ValueError("dimensões de origem do overlay devem ser positivas")
        if any(not isinstance(item, CameraOverlayBox) for item in self.boxes):
            raise ValueError("boxes deve conter somente CameraOverlayBox")


@dataclass(frozen=True, slots=True)
class CameraRiskZone:
    """One persistent polygon in normalized camera-frame coordinates."""

    label: str
    vertices: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        normalized_label = self.label.strip()
        if not normalized_label:
            raise ValueError("label da zona de risco não pode ser vazio")
        vertices = tuple(self.vertices)
        if len(vertices) < 3:
            raise ValueError("a zona de risco exige ao menos três vértices")
        normalized_vertices: list[tuple[float, float]] = []
        for vertex in vertices:
            if not isinstance(vertex, tuple) or len(vertex) != 2:
                raise ValueError("cada vértice da zona deve possuir x e y")
            x, y = (float(coordinate) for coordinate in vertex)
            if not isfinite(x) or not isfinite(y):
                raise ValueError("coordenadas da zona devem ser finitas")
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                raise ValueError("coordenadas da zona devem estar entre zero e um")
            normalized_vertices.append((x, y))
        object.__setattr__(self, "label", normalized_label)
        object.__setattr__(self, "vertices", tuple(normalized_vertices))


class CameraFrameView(QFrame):
    """Paint an owned frame and expiring generic boxes without OpenCV."""

    def __init__(self, object_name: str) -> None:
        super().__init__()
        self._frame: QImage | None = None
        self._overlay: CameraFrameOverlay | None = None
        self._risk_zones: tuple[CameraRiskZone, ...] = ()
        self._overlay_expiry_timer = QTimer(self)
        self._overlay_expiry_timer.setSingleShot(True)
        self._overlay_expiry_timer.timeout.connect(self.clear_overlay)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def has_frame(self) -> bool:
        return self._frame is not None and not self._frame.isNull()

    @property
    def has_overlay(self) -> bool:
        return self._overlay is not None and bool(self._overlay.boxes)

    @property
    def overlay_box_count(self) -> int:
        overlay = self._overlay
        return len(overlay.boxes) if overlay is not None else 0

    @property
    def overlay_labels(self) -> tuple[str, ...]:
        overlay = self._overlay
        return tuple(box.label for box in overlay.boxes) if overlay is not None else ()

    @property
    def risk_zone_count(self) -> int:
        return len(self._risk_zones)

    @property
    def risk_zone_labels(self) -> tuple[str, ...]:
        return tuple(zone.label for zone in self._risk_zones)

    def set_frame(self, frame: QImage) -> None:
        """Copy a worker-owned frame before scheduling a repaint."""

        self._frame = frame.copy()
        self.update()

    def clear_frame(self) -> None:
        self._frame = None
        self.clear_overlay()
        self.update()

    def set_overlay(
        self,
        overlay: CameraFrameOverlay,
        *,
        maximum_age_ms: int,
    ) -> None:
        """Replace stale boxes and schedule their automatic visual expiry."""

        if not isinstance(overlay, CameraFrameOverlay):
            raise ValueError("overlay deve ser um CameraFrameOverlay")
        if maximum_age_ms <= 0:
            raise ValueError("maximum_age_ms deve ser maior que zero")
        self._overlay = overlay
        if overlay.boxes:
            self._overlay_expiry_timer.start(maximum_age_ms)
        else:
            self._overlay_expiry_timer.stop()
        self.update()

    def clear_overlay(self) -> None:
        self._overlay_expiry_timer.stop()
        self._overlay = None
        self.update()

    def set_risk_zones(self, zones: tuple[CameraRiskZone, ...]) -> None:
        """Replace persistent normalized zones independently from detections."""

        received = tuple(zones)
        if any(not isinstance(item, CameraRiskZone) for item in received):
            raise ValueError("zones deve conter somente CameraRiskZone")
        self._risk_zones = received
        self.update()

    def clear_risk_zones(self) -> None:
        self._risk_zones = ()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            target = self.rect().adjusted(1, 1, -1, -1)
            frame = self._frame
            if frame is None or frame.isNull():
                painter.fillRect(target, QColor("#10243e"))
                transform = target.width(), target.height(), 0, 0
            else:
                transform = self._paint_frame(painter, target, frame)
            if self._risk_zones:
                self._paint_risk_zones(painter, target, self._risk_zones, transform)
            overlay = self._overlay
            if overlay is not None and overlay.boxes:
                self._paint_overlay(painter, target, overlay, transform)
        finally:
            painter.end()

    @staticmethod
    def _paint_frame(
        painter: QPainter,
        target: QRect,
        frame: QImage,
    ) -> tuple[int, int, int, int]:
        pixmap = QPixmap.fromImage(frame)
        scaled = pixmap.scaled(
            target.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        source_x = max(0, (scaled.width() - target.width()) // 2)
        source_y = max(0, (scaled.height() - target.height()) // 2)
        source = QRect(source_x, source_y, target.width(), target.height())
        painter.drawPixmap(target, scaled, source)
        return scaled.width(), scaled.height(), source_x, source_y

    @staticmethod
    def _paint_risk_zones(
        painter: QPainter,
        target: QRect,
        zones: tuple[CameraRiskZone, ...],
        transform: tuple[int, int, int, int],
    ) -> None:
        scaled_width, scaled_height, source_x, source_y = transform
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipRect(target)
            pen = QPen(QColor("#ffb347"))
            pen.setWidth(3)
            pen.setStyle(Qt.PenStyle.DashLine)
            font = QFont(painter.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)

            for zone in zones:
                polygon = QPolygonF(
                    [
                        QPointF(
                            target.left() + x * scaled_width - source_x,
                            target.top() + y * scaled_height - source_y,
                        )
                        for x, y in zone.vertices
                    ]
                )
                painter.setPen(pen)
                painter.setBrush(QColor(235, 87, 87, 48))
                painter.drawPolygon(polygon)

                text = f"ÁREA DE RISCO · {zone.label}"
                metrics = painter.fontMetrics()
                label_width = metrics.horizontalAdvance(text) + 14
                label_height = metrics.height() + 6
                bounds = polygon.boundingRect()
                label_left = min(
                    max(bounds.left(), float(target.left())),
                    max(float(target.left()), target.right() - label_width),
                )
                label_top = max(float(target.top()), bounds.top() - label_height)
                label_rect = QRectF(
                    label_left,
                    label_top,
                    min(float(label_width), float(target.width())),
                    float(label_height),
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(91, 38, 18, 220))
                painter.drawRoundedRect(label_rect, 3, 3)
                painter.setPen(QColor("#fff4df"))
                painter.drawText(
                    label_rect.adjusted(7, 0, -7, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )
        finally:
            painter.restore()

    @staticmethod
    def _paint_overlay(
        painter: QPainter,
        target: QRect,
        overlay: CameraFrameOverlay,
        transform: tuple[int, int, int, int],
    ) -> None:
        scaled_width, scaled_height, source_x, source_y = transform
        scale_x = scaled_width / overlay.source_width
        scale_y = scaled_height / overlay.source_height
        target_rect = QRectF(target)

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipRect(target)
            pen = QPen(QColor("#42b8ff"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            font = QFont(painter.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()

            for box in overlay.boxes:
                mapped = QRectF(
                    target.left() + box.x1 * scale_x - source_x,
                    target.top() + box.y1 * scale_y - source_y,
                    max(1.0, (box.x2 - box.x1) * scale_x),
                    max(1.0, (box.y2 - box.y1) * scale_y),
                ).intersected(target_rect)
                if mapped.isEmpty():
                    continue
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(mapped, 3, 3)

                text = f"{box.label}  {box.confidence:.0%}"
                padding_x = 6
                label_width = metrics.horizontalAdvance(text) + padding_x * 2
                label_height = metrics.height() + 4
                label_left = min(
                    max(mapped.left(), target_rect.left()),
                    max(target_rect.left(), target_rect.right() - label_width),
                )
                label_top = mapped.top() - label_height
                if label_top < target_rect.top():
                    label_top = mapped.top()
                label_rect = QRectF(
                    label_left,
                    label_top,
                    min(float(label_width), target_rect.width()),
                    float(label_height),
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(10, 42, 68, 220))
                painter.drawRoundedRect(label_rect, 3, 3)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(
                    label_rect.adjusted(padding_x, 0, -padding_x, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )
        finally:
            painter.restore()
