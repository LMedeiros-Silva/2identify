from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import RealtimeAlert

_MAX_VISIBLE_ALERTS = 100


class AlertsPage(QWidget):
    """Lista limitada de notificações efêmeras; a API continua fonte dos totais."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("alerts_page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(16)

        title = QLabel("Alertas")
        title.setObjectName("pagina_titulo")
        layout.addWidget(title)

        subtitle = QLabel(
            "Eventos recebidos nesta sessão pelo canal em tempo real."
        )
        subtitle.setObjectName("pagina_subtitulo")
        layout.addWidget(subtitle)

        self.connection_status = QLabel("Canal em tempo real desconectado.")
        self.connection_status.setObjectName("realtime_status")
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)

        self.alert_banner = QFrame()
        self.alert_banner.setObjectName("alert_banner")
        banner_layout = QVBoxLayout(self.alert_banner)
        self.alert_banner_text = QLabel()
        self.alert_banner_text.setObjectName("alert_banner_text")
        self.alert_banner_text.setTextFormat(Qt.TextFormat.PlainText)
        self.alert_banner_text.setWordWrap(True)
        banner_layout.addWidget(self.alert_banner_text)
        self.alert_banner.hide()
        layout.addWidget(self.alert_banner)

        self.alert_list = QListWidget()
        self.alert_list.setObjectName("alert_list")
        self.alert_list.setAlternatingRowColors(True)
        self.alert_list.setWordWrap(True)
        layout.addWidget(self.alert_list, 1)

        self.empty_label = QLabel(
            "Nenhum alerta foi recebido pelo WebSocket nesta sessão."
        )
        self.empty_label.setObjectName("sem_alertas")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

    def set_connection_status(self, message: str, *, state: str) -> None:
        self.connection_status.setText(message)
        self.connection_status.setProperty("state", state)
        self._refresh_style(self.connection_status)

    def add_alert(self, alert: RealtimeAlert) -> None:
        severity = "Crítico" if alert.level == "critical" else "Atenção"
        camera = f" · Câmera #{alert.camera_id}" if alert.camera_id is not None else ""
        timestamp = alert.detected_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        text = (
            f"{timestamp} · {severity} · Alerta #{alert.alert_id}{camera}\n"
            f"{alert.summary}"
        )

        self.alert_banner.setProperty("severity", alert.level)
        self.alert_banner_text.setText(text)
        self.alert_banner.show()
        self._refresh_style(self.alert_banner)

        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, str(alert.event_id))
        self.alert_list.insertItem(0, item)
        while self.alert_list.count() > _MAX_VISIBLE_ALERTS:
            self.alert_list.takeItem(self.alert_list.count() - 1)
        self.empty_label.hide()

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
