"""Primary facial-authentication presentation components."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.domain.auth import OperatorIdentity


class FaceLoginState(StrEnum):
    READY = "ready"
    STARTING = "starting"
    SCANNING = "scanning"
    RECOGNIZED = "recognized"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class CameraPreview(QFrame):
    """Qt-only camera surface; OpenCV remains outside the UI layer."""

    def __init__(self) -> None:
        super().__init__()
        self._frame: QImage | None = None
        self._state = FaceLoginState.READY
        self.setObjectName("faceCameraPreview")
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_frame(self, frame: QImage) -> None:
        """Copy a worker-owned frame before scheduling a repaint."""

        self._frame = frame.copy()
        self.update()

    def clear_frame(self) -> None:
        self._frame = None
        self.update()

    def set_state(self, state: FaceLoginState) -> None:
        self._state = state
        self.setProperty("faceState", state.value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            content_rect = self.rect().adjusted(1, 1, -1, -1)

            frame = self._frame
            if frame is not None and not frame.isNull():
                self._paint_frame(painter, content_rect, frame)
            else:
                self._paint_placeholder(painter, content_rect)

            self._paint_face_guide(painter, content_rect)
        finally:
            painter.end()

    def _paint_frame(self, painter: QPainter, target: QRect, frame: QImage) -> None:
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

    def _paint_placeholder(self, painter: QPainter, target: QRect) -> None:
        painter.fillRect(target, QColor("#061423"))
        center = target.center()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#17344f"))
        painter.drawEllipse(QPoint(center.x(), center.y() - 22), 29, 35)

        body = QPainterPath()
        body.addRoundedRect(
            QRectF(center.x() - 59, center.y() + 18, 118, 84),
            34,
            34,
        )
        painter.drawPath(body)

        painter.setPen(QColor("#7894ad"))
        painter.drawText(
            target.adjusted(0, 160, 0, -16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "A visualização da câmera aparecerá aqui",
        )

    def _paint_face_guide(self, painter: QPainter, target: QRect) -> None:
        center = target.center()
        guide = QRectF(center.x() - 82, center.y() - 104, 164, 208)
        guide_color = {
            FaceLoginState.RECOGNIZED: QColor("#4ad295"),
            FaceLoginState.ERROR: QColor("#f0646d"),
            FaceLoginState.UNAVAILABLE: QColor("#e8ad4c"),
        }.get(self._state, QColor("#45a8ff"))
        pen = QPen(guide_color)
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(guide, 70, 70)

        corner_pen = QPen(guide_color)
        corner_pen.setWidth(4)
        painter.setPen(corner_pen)
        length = 22
        left, top, right, bottom = guide.left(), guide.top(), guide.right(), guide.bottom()
        painter.drawLine(int(left), int(top + length), int(left), int(top))
        painter.drawLine(int(left), int(top), int(left + length), int(top))
        painter.drawLine(int(right - length), int(top), int(right), int(top))
        painter.drawLine(int(right), int(top), int(right), int(top + length))
        painter.drawLine(int(left), int(bottom - length), int(left), int(bottom))
        painter.drawLine(int(left), int(bottom), int(left + length), int(bottom))
        painter.drawLine(int(right - length), int(bottom), int(right), int(bottom))
        painter.drawLine(int(right), int(bottom), int(right), int(bottom - length))


class ProfileAvatar(QWidget):
    """Circular operator portrait with initials as a safe fallback."""

    def __init__(self) -> None:
        super().__init__()
        self._portrait: QImage | None = None
        self._initials = ""
        self.setObjectName("operatorPhoto")
        self.setFixedSize(58, 58)

    @property
    def has_portrait(self) -> bool:
        return self._portrait is not None and not self._portrait.isNull()

    def set_profile(self, identity: OperatorIdentity, portrait: QImage | None) -> None:
        self._portrait = portrait.copy() if portrait is not None else None
        self._initials = "".join(part[0] for part in identity.name.split()[:2]).upper()
        self.update()

    def clear_profile(self) -> None:
        self._portrait = None
        self._initials = ""
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            target = self.rect().adjusted(2, 2, -2, -2)
            clip_path = QPainterPath()
            clip_path.addEllipse(QRectF(target))

            painter.setClipPath(clip_path)
            painter.fillRect(target, QColor("#1687f8"))
            portrait = self._portrait
            if portrait is not None and not portrait.isNull():
                pixmap = QPixmap.fromImage(portrait).scaled(
                    target.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                source_x = max(0, (pixmap.width() - target.width()) // 2)
                source_y = max(0, (pixmap.height() - target.height()) // 2)
                source = QRect(source_x, source_y, target.width(), target.height())
                painter.drawPixmap(target, pixmap, source)
            else:
                painter.setPen(QColor("#ffffff"))
                font = QFont(painter.font())
                font.setBold(True)
                font.setPixelSize(16)
                painter.setFont(font)
                painter.drawText(target, Qt.AlignmentFlag.AlignCenter, self._initials)

            painter.setClipping(False)
            border_pen = QPen(QColor("#ffffff"))
            border_pen.setWidth(2)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(target)
        finally:
            painter.end()


class FaceLoginPanel(QWidget):
    """Primary login view with camera state, identity and fallback controls."""

    scan_requested = Signal()
    credentials_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._state = FaceLoginState.READY
        self.setObjectName("faceLoginPanel")
        self.setMinimumWidth(420)
        self.setMaximumWidth(460)
        self._build_content()
        self.set_state(
            FaceLoginState.READY,
            "Pronto para iniciar o reconhecimento facial.",
        )

    def focus_initial_control(self) -> None:
        self._scan_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def update_frame(self, frame: QImage) -> None:
        self._camera_preview.set_frame(frame)
        if self._state in {FaceLoginState.READY, FaceLoginState.STARTING}:
            self.set_state(FaceLoginState.SCANNING, "Procurando um rosto cadastrado...")

    def set_state(self, state: FaceLoginState, message: str) -> None:
        self._state = state
        self._camera_preview.set_state(state)
        self._status_row.setProperty("faceState", state.value)
        self._status_dot.setProperty("faceState", state.value)
        self._refresh_style(self._status_row)
        self._refresh_style(self._status_dot)
        self._status_text.setText(message)

        is_busy = state in {FaceLoginState.STARTING, FaceLoginState.SCANNING}
        self._scan_button.setEnabled(not is_busy)
        # The fallback remains available so the operator can cancel a slow camera attempt.
        self._credentials_button.setEnabled(True)
        self._scan_button.setText(
            "RECONHECENDO..." if is_busy else "INICIAR RECONHECIMENTO FACIAL"
        )
        if state is not FaceLoginState.RECOGNIZED:
            self._identity_card.hide()
            self._scan_button.show()

    def show_identity(self, identity: OperatorIdentity, portrait: QImage | None = None) -> None:
        self.set_state(
            FaceLoginState.RECOGNIZED,
            f"Operador confirmado com {identity.confidence:.0%} de confiança.",
        )
        self._operator_name.setText(identity.name)
        self._operator_detail.setText(f"Operador #{identity.operator_id} · Acesso autorizado")
        self._set_portrait(identity, portrait)
        self._identity_card.show()
        self._scan_button.hide()

    def show_error(self, message: str, unavailable: bool = False) -> None:
        state = FaceLoginState.UNAVAILABLE if unavailable else FaceLoginState.ERROR
        self.set_state(state, message)

    def reset(self) -> None:
        """Remove frames and identity data before a new authentication session."""

        self._camera_preview.clear_frame()
        self._operator_photo.clear_profile()
        self._operator_name.clear()
        self._operator_detail.clear()
        self.set_state(
            FaceLoginState.READY,
            "Pronto para iniciar o reconhecimento facial.",
        )

    def _build_content(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label("FACE ID · ACESSO PRINCIPAL", "formEyebrow"))
        layout.addSpacing(8)
        layout.addWidget(self._label("Olhe para a câmera", "formTitle"))
        layout.addSpacing(7)

        description = self._label(
            "Posicione o rosto dentro da marcação para identificarmos seu acesso.",
            "formDescription",
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(17)

        self._camera_preview = CameraPreview()
        layout.addWidget(self._camera_preview)
        layout.addSpacing(11)

        self._status_row = QFrame()
        self._status_row.setObjectName("faceStatusRow")
        status_layout = QHBoxLayout(self._status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("faceStatusDot")
        status_layout.addWidget(self._status_dot)
        self._status_text = self._label("", "faceStatusText")
        self._status_text.setWordWrap(True)
        status_layout.addWidget(self._status_text, 1)
        layout.addWidget(self._status_row)
        layout.addSpacing(10)

        self._identity_card = self._build_identity_card()
        self._identity_card.hide()
        layout.addWidget(self._identity_card)
        layout.addSpacing(10)

        self._scan_button = QPushButton("INICIAR RECONHECIMENTO FACIAL")
        self._scan_button.setObjectName("faceScanButton")
        self._scan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_button.clicked.connect(self._request_scan)
        layout.addWidget(self._scan_button)
        layout.addSpacing(10)

        self._credentials_button = QPushButton("ENTRAR COM E-MAIL E SENHA")
        self._credentials_button.setObjectName("secondaryAuthButton")
        self._credentials_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._credentials_button.clicked.connect(self.credentials_requested)
        layout.addWidget(self._credentials_button)

    def _build_identity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("recognizedOperatorCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(13)

        self._operator_photo = ProfileAvatar()
        layout.addWidget(self._operator_photo)

        identity_text = QVBoxLayout()
        identity_text.setSpacing(2)
        identity_text.addWidget(self._label("BEM-VINDO", "welcomeEyebrow"))
        self._operator_name = self._label("", "recognizedOperatorName")
        identity_text.addWidget(self._operator_name)
        self._operator_detail = self._label("", "recognizedOperatorDetail")
        identity_text.addWidget(self._operator_detail)
        layout.addLayout(identity_text, 1)
        return card

    def _set_portrait(self, identity: OperatorIdentity, portrait: QImage | None) -> None:
        self._operator_photo.set_profile(identity, portrait)

    def _request_scan(self) -> None:
        self.set_state(FaceLoginState.STARTING, "Inicializando câmera segura...")
        self.scan_requested.emit()

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label
