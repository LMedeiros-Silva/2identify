"""Small dependency-free dashboard charts painted with Qt."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class ChartBar:
    label: str
    value: int
    color: str


@dataclass(frozen=True, slots=True)
class ChartSegment:
    label: str
    value: int
    color: str


class AlertTrendChart(QWidget):
    """Seven-day line chart with a zero-safe scale."""

    def __init__(self) -> None:
        super().__init__()
        self._points: tuple[tuple[str, int], ...] = ()
        self.setObjectName("dashboardAlertTrendChart")
        self.setAccessibleName("Tendência de alertas nos últimos sete dias")
        self.setMinimumHeight(205)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(value for _label, value in self._points)

    def set_points(self, points: tuple[tuple[str, int], ...]) -> None:
        if any(value < 0 for _label, value in points):
            raise ValueError("Os valores do gráfico não podem ser negativos.")
        self._points = tuple(points)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(38, 12, max(1, self.width() - 52), max(1, self.height() - 42))
        values = self.values or (0,)
        maximum = max(values)
        scale_maximum = max(1, int(ceil(maximum / 4)) * 4)
        label_font = QFont(self.font())
        label_font.setPixelSize(9)
        painter.setFont(label_font)

        for index in range(5):
            ratio = index / 4
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(QPen(QColor("#E8EDF4"), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#98A2B3"))
            painter.drawText(
                QRectF(0, y - 8, 32, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(round(scale_maximum * ratio)),
            )

        if not self._points:
            self._draw_empty(painter, plot)
            return

        step = plot.width() / max(1, len(self._points) - 1)
        positions = tuple(
            QPointF(
                plot.left() + index * step,
                plot.bottom() - (value / scale_maximum) * plot.height(),
            )
            for index, (_label, value) in enumerate(self._points)
        )
        line = QPainterPath(positions[0])
        for point in positions[1:]:
            line.lineTo(point)

        area = QPainterPath(line)
        area.lineTo(positions[-1].x(), plot.bottom())
        area.lineTo(positions[0].x(), plot.bottom())
        area.closeSubpath()
        gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
        gradient.setColorAt(0, QColor(37, 99, 235, 95))
        gradient.setColorAt(1, QColor(37, 99, 235, 5))
        painter.fillPath(area, gradient)
        painter.setPen(QPen(QColor("#2563EB"), 2.5))
        painter.drawPath(line)

        for index, ((label, value), point) in enumerate(
            zip(self._points, positions, strict=True)
        ):
            painter.setBrush(QColor("#FFFFFF"))
            painter.setPen(QPen(QColor("#2563EB"), 2))
            painter.drawEllipse(point, 4, 4)
            painter.setPen(QColor("#667085"))
            alignment = Qt.AlignmentFlag.AlignHCenter
            label_width = 46.0
            label_x = point.x() - label_width / 2
            if index == 0:
                label_x = plot.left() - 2
                alignment = Qt.AlignmentFlag.AlignLeft
            elif index == len(positions) - 1:
                label_x = plot.right() - label_width + 2
                alignment = Qt.AlignmentFlag.AlignRight
            painter.drawText(
                QRectF(label_x, plot.bottom() + 8, label_width, 16),
                alignment | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            if value:
                painter.setPen(QColor("#172033"))
                painter.drawText(
                    QRectF(point.x() - 16, point.y() - 24, 32, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    str(value),
                )

    @staticmethod
    def _draw_empty(painter: QPainter, plot: QRectF) -> None:
        painter.setPen(QColor("#98A2B3"))
        painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Sem dados no período")


class AlertCategoryBarChart(QWidget):
    """Compact horizontal bars for alert categories."""

    def __init__(self) -> None:
        super().__init__()
        self._bars: tuple[ChartBar, ...] = ()
        self.setObjectName("dashboardAlertCategoryChart")
        self.setAccessibleName("Distribuição dos alertas por categoria")
        self.setMinimumHeight(205)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(item.value for item in self._bars)

    def set_bars(self, bars: tuple[ChartBar, ...]) -> None:
        if any(item.value < 0 for item in bars):
            raise ValueError("Os valores do gráfico não podem ser negativos.")
        self._bars = tuple(bars)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(9)
        painter.setFont(font)
        if not self._bars:
            painter.setPen(QColor("#98A2B3"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sem dados")
            return
        maximum = max(1, *(item.value for item in self._bars))
        row_height = self.height() / len(self._bars)
        for index, item in enumerate(self._bars):
            top = index * row_height + 4
            painter.setPen(QColor("#475467"))
            painter.drawText(
                QRectF(0, top, max(1, self.width() - 32), 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                item.label,
            )
            painter.setPen(QColor("#172033"))
            painter.drawText(
                QRectF(max(0, self.width() - 30), top, 30, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(item.value),
            )
            track = QRectF(0, top + 20, self.width(), 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#EEF2F6"))
            painter.drawRoundedRect(track, 4, 4)
            if item.value:
                fill = QRectF(
                    track.left(),
                    track.top(),
                    max(5.0, track.width() * item.value / maximum),
                    track.height(),
                )
                painter.setBrush(QColor(item.color))
                painter.drawRoundedRect(fill, 4, 4)


class AlertStatusDonutChart(QWidget):
    """Donut chart for the administrative alert lifecycle."""

    def __init__(self) -> None:
        super().__init__()
        self._segments: tuple[ChartSegment, ...] = ()
        self.setObjectName("dashboardAlertStatusChart")
        self.setAccessibleName("Distribuição dos alertas por situação")
        self.setMinimumHeight(205)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(item.value for item in self._segments)

    def set_segments(self, segments: tuple[ChartSegment, ...]) -> None:
        if any(item.value < 0 for item in segments):
            raise ValueError("Os valores do gráfico não podem ser negativos.")
        self._segments = tuple(segments)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(self.values)
        diameter = min(118.0, self.height() - 26.0, self.width() * 0.48)
        ring = QRectF(7, (self.height() - diameter) / 2, diameter, diameter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#EEF2F6"), 14))
        painter.drawEllipse(ring)
        if total:
            start_angle = 90 * 16
            for segment in self._segments:
                if not segment.value:
                    continue
                span = -round(360 * 16 * segment.value / total)
                painter.setPen(QPen(QColor(segment.color), 14))
                painter.drawArc(ring, start_angle, span)
                start_angle += span

        value_font = QFont(self.font())
        value_font.setPixelSize(20)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor("#172033"))
        painter.drawText(ring, Qt.AlignmentFlag.AlignCenter, str(total))

        legend_font = QFont(self.font())
        legend_font.setPixelSize(9)
        painter.setFont(legend_font)
        legend_x = ring.right() + 20
        row_height = 28
        legend_top = max(4.0, (self.height() - row_height * len(self._segments)) / 2)
        for index, segment in enumerate(self._segments):
            y = legend_top + index * row_height
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(segment.color))
            painter.drawEllipse(QRectF(legend_x, y + 4, 8, 8))
            painter.setPen(QColor("#475467"))
            painter.drawText(
                QRectF(legend_x + 14, y, max(1, self.width() - legend_x - 16), 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{segment.label} · {segment.value}",
            )


__all__ = [
    "AlertCategoryBarChart",
    "AlertStatusDonutChart",
    "AlertTrendChart",
    "ChartBar",
    "ChartSegment",
]
