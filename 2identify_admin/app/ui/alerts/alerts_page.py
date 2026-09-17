from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.domain import AdminAlert, AdminAlertPage, RealtimeAlert

_MAX_REALTIME_ITEMS = 100


class AlertsPage(QWidget):
    """Persistent alert inbox with complete occurrence details and actions."""

    refresh_requested = Signal()
    alert_selected = Signal(int)
    confirm_requested = Signal(int)
    close_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("alerts_page")
        self._alerts: dict[int, AdminAlert] = {}
        self._selected_alert_id: int | None = None
        self._action_busy = False
        self.confirm_button: QPushButton | None = None
        self.close_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("Central de alertas")
        title.setObjectName("pagina_titulo")
        title_column.addWidget(title)
        subtitle = QLabel("Confirme os alertas recebidos e encerre as ocorrências tratadas.")
        subtitle.setObjectName("pagina_subtitulo")
        title_column.addWidget(subtitle)
        title_row.addLayout(title_column, 1)
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setObjectName("alerts_refresh")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        title_row.addWidget(self.refresh_button)
        layout.addLayout(title_row)

        self.connection_status = QLabel("Canal em tempo real desconectado.")
        self.connection_status.setObjectName("realtime_status")
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)

        self.feedback_label = QLabel()
        self.feedback_label.setObjectName("alerts_feedback")
        self.feedback_label.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback_label.setWordWrap(True)
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("alerts_splitter")
        splitter.setChildrenCollapsible(False)

        list_panel = QFrame()
        list_panel.setObjectName("alerts_list_panel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(14, 14, 14, 14)
        list_title = QLabel("Alertas registrados")
        list_title.setObjectName("alert_section_title")
        list_layout.addWidget(list_title)
        self.count_label = QLabel("Carregando...")
        self.count_label.setObjectName("alert_muted")
        list_layout.addWidget(self.count_label)
        self.alert_list = QListWidget()
        self.alert_list.setObjectName("alert_list")
        self.alert_list.setAlternatingRowColors(True)
        self.alert_list.setWordWrap(True)
        self.alert_list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.alert_list, 1)
        self.empty_label = QLabel("Nenhum alerta registrado.")
        self.empty_label.setObjectName("sem_alertas")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        list_layout.addWidget(self.empty_label)
        splitter.addWidget(list_panel)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("alert_detail_scroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_container = QWidget()
        self.detail_container.setObjectName("alert_detail_container")
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(18, 18, 18, 18)
        self.detail_layout.setSpacing(14)
        self.detail_scroll.setWidget(self.detail_container)
        splitter.addWidget(self.detail_scroll)
        splitter.setSizes([390, 750])
        layout.addWidget(splitter, 1)

        self._show_placeholder("Selecione um alerta para visualizar todos os dados.")

    def set_connection_status(self, message: str, *, state: str) -> None:
        self.connection_status.setText(message)
        self.connection_status.setProperty("state", state)
        self._refresh_style(self.connection_status)

    def set_alerts(self, page: AdminAlertPage) -> None:
        self.feedback_label.clear()
        self.feedback_label.hide()
        selected_id = self._selected_alert_id
        self._alerts = {alert.id: alert for alert in page.items}
        self.alert_list.clear()
        for alert in page.items:
            item = QListWidgetItem(self._list_text(alert))
            item.setData(Qt.ItemDataRole.UserRole, alert.id)
            item.setToolTip(alert.summary)
            self.alert_list.addItem(item)
            if alert.id == selected_id:
                self.alert_list.setCurrentItem(item)
        self.count_label.setText(f"{page.total} alerta(s) no histórico")
        self.empty_label.setVisible(not page.items)
        self.alert_list.setVisible(bool(page.items))
        self.refresh_button.setEnabled(True)
        if not page.items:
            self._selected_alert_id = None
            self._show_placeholder("Nenhum alerta foi registrado até o momento.")
        elif self.alert_list.currentItem() is None:
            self.alert_list.setCurrentRow(0)

    def update_alert(self, alert: AdminAlert) -> None:
        self._alerts[alert.id] = alert
        for index in range(self.alert_list.count()):
            item = self.alert_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == alert.id:
                item.setText(self._list_text(alert))
                item.setToolTip(alert.summary)
                break
        self._selected_alert_id = alert.id
        self._show_alert(alert)

    def add_alert(self, alert: RealtimeAlert) -> None:
        """Surface a realtime notification while the controller reloads history."""

        category = self._category_label(alert.category)
        severity = "Crítico" if alert.level == "critical" else "Atenção"
        timestamp = self._format_datetime(alert.detected_at)
        self.alert_banner.setProperty("severity", alert.level)
        self.alert_banner_text.setText(
            f"Novo alerta #{alert.alert_id} · {category} · {severity} · {timestamp}\n"
            f"{alert.summary}"
        )
        self.alert_banner.show()
        self._refresh_style(self.alert_banner)
        item = QListWidgetItem(
            f"#{alert.alert_id} · {category} · {self._status_label(alert.status)}\n"
            f"{timestamp} · {alert.summary}"
        )
        item.setData(Qt.ItemDataRole.UserRole, alert.alert_id)
        item.setToolTip(alert.summary)
        self.alert_list.insertItem(0, item)
        while self.alert_list.count() > _MAX_REALTIME_ITEMS:
            self.alert_list.takeItem(self.alert_list.count() - 1)
        self.alert_list.show()
        self.empty_label.hide()
        self.count_label.setText(f"{self.alert_list.count()} alerta(s) recebido(s) nesta sessão")

    def show_loading(self) -> None:
        self.refresh_button.setEnabled(False)
        self.count_label.setText("Carregando alertas...")
        self._show_feedback("Consultando o histórico de alertas...", "loading")

    def show_error(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self._action_busy = False
        loaded_count = self.alert_list.count()
        self.count_label.setText(
            f"{loaded_count} alerta(s) carregado(s)"
            if loaded_count
            else "Histórico indisponível."
        )
        self.empty_label.hide()
        self._show_feedback(message, "error")
        self._refresh_actions()

    def show_action_loading(self, action: str) -> None:
        self._action_busy = True
        verb = "Confirmando alerta..." if action == "confirm" else "Encerrando ocorrência..."
        self._show_feedback(verb, "loading")
        self._refresh_actions()

    def show_action_success(self, action: str) -> None:
        self._action_busy = False
        message = (
            "Alerta confirmado com sucesso."
            if action == "confirm"
            else "Ocorrência encerrada com sucesso."
        )
        self._show_feedback(message, "success")
        self._refresh_actions()

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        alert_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(alert_id, int):
            return
        alert = self._alerts.get(alert_id)
        if alert is None:
            return
        self._selected_alert_id = alert_id
        self._show_alert(alert)
        self.alert_selected.emit(alert_id)

    def _show_alert(self, alert: AdminAlert) -> None:
        self._clear_detail()
        header = QFrame()
        header.setObjectName("alert_detail_header")
        header_layout = QVBoxLayout(header)
        self.detail_title = QLabel(f"Alerta #{alert.id}")
        self.detail_title.setObjectName("alert_detail_title")
        header_layout.addWidget(self.detail_title)
        self.detail_status = QLabel(
            f"{self._category_label(alert.category)} · "
            f"{self._level_label(alert.level)} · {self._status_label(alert.status)}"
        )
        self.detail_status.setObjectName("alert_detail_status")
        self.detail_status.setProperty("status", alert.status)
        header_layout.addWidget(self.detail_status)
        summary = QLabel(alert.summary)
        summary.setObjectName("alert_detail_summary")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        header_layout.addWidget(summary)
        self.detail_layout.addWidget(header)

        self.detail_layout.addWidget(
            self._section(
                "Ciclo do alerta",
                (
                    ("Status", self._status_label(alert.status)),
                    ("Nível", self._level_label(alert.level)),
                    ("Criado em", self._format_datetime(alert.created_at)),
                    ("Recebido em", self._format_datetime(alert.received_at)),
                    ("Confirmado em", self._format_datetime(alert.confirmed_at)),
                    ("Confirmado por", self._actor_text(alert.confirmed_by)),
                    ("Encerrado em", self._format_datetime(alert.closed_at)),
                    ("Encerrado por", self._actor_text(alert.closed_by)),
                    ("Observação", alert.observation or "—"),
                ),
            )
        )

        occurrence = alert.occurrence
        confidence = (
            f"{occurrence.confidence * 100:.1f}%"
            if occurrence.confidence is not None and occurrence.confidence <= 1
            else str(occurrence.confidence)
            if occurrence.confidence is not None
            else "—"
        )
        self.detail_layout.addWidget(
            self._section(
                "Ocorrência",
                (
                    ("ID", str(occurrence.id)),
                    ("Tipo", occurrence.type),
                    ("Descrição", occurrence.description or "—"),
                    ("Confiança", confidence),
                    ("Detectado em", self._format_datetime(occurrence.detected_at)),
                    ("Imagem", occurrence.image_reference or "—"),
                    ("Vídeo", occurrence.video_reference or "—"),
                ),
            )
        )

        employee = occurrence.employee
        self.detail_layout.addWidget(
            self._section(
                "Funcionário identificado",
                (
                    ("ID", str(employee.id) if employee else "—"),
                    ("Nome", employee.name if employee else "Não identificado"),
                    ("Matrícula", employee.registration if employee else "—"),
                    ("Cargo", (employee.role or "—") if employee else "—"),
                    ("Turno", (employee.shift or "—") if employee else "—"),
                    (
                        "Setor",
                        employee.sector.name if employee and employee.sector else "—",
                    ),
                ),
            )
        )

        camera = occurrence.camera
        self.detail_layout.addWidget(
            self._section(
                "Câmera",
                (
                    ("ID", str(camera.id) if camera else "—"),
                    ("Nome", camera.name if camera else "Não informada"),
                    ("Descrição", (camera.description or "—") if camera else "—"),
                    (
                        "Setor",
                        camera.sector.name if camera and camera.sector else "—",
                    ),
                ),
            )
        )

        context = alert.operational_context
        self.detail_layout.addWidget(
            self._section(
                "Contexto operacional",
                (
                    ("Evento", str(context.event_id) if context else "—"),
                    (
                        "Sessão de trabalho",
                        str(context.work_session_id) if context else "—",
                    ),
                    ("Operação", str(context.operation_id) if context else "—"),
                    (
                        "Área de risco",
                        str(context.risk_area_id) if context and context.risk_area_id else "—",
                    ),
                    (
                        "Violação",
                        context.violation_type if context else occurrence.type,
                    ),
                    ("Chave", context.subject_key if context else "—"),
                    (
                        "Operador",
                        self._actor_text(context.operator) if context else "—",
                    ),
                    (
                        "Ingerido em",
                        self._format_datetime(context.received_at) if context else "—",
                    ),
                ),
            )
        )

        actions = QFrame()
        actions.setObjectName("alert_actions")
        actions_layout = QHBoxLayout(actions)
        self.confirm_button = QPushButton("Confirmar alerta")
        self.confirm_button.setObjectName("alert_confirm")
        self.confirm_button.clicked.connect(self._request_confirmation)
        actions_layout.addWidget(self.confirm_button)
        self.close_button = QPushButton("Encerrar ocorrência")
        self.close_button.setObjectName("alert_close")
        self.close_button.clicked.connect(self._request_close)
        actions_layout.addWidget(self.close_button)
        self.detail_layout.addWidget(actions)
        self.detail_layout.addStretch()
        self._refresh_actions()

    @Slot()
    def _request_confirmation(self) -> None:
        if self._selected_alert_id is not None:
            self.confirm_requested.emit(self._selected_alert_id)

    @Slot()
    def _request_close(self) -> None:
        if self._selected_alert_id is not None:
            self.close_requested.emit(self._selected_alert_id)

    def _refresh_actions(self) -> None:
        alert = self._alerts.get(self._selected_alert_id or -1)
        confirm_button = getattr(self, "confirm_button", None)
        close_button = getattr(self, "close_button", None)
        if confirm_button is None or close_button is None:
            return
        confirm_button.setEnabled(
            not self._action_busy and alert is not None and alert.status == "nao_lido"
        )
        close_button.setEnabled(
            not self._action_busy and alert is not None and alert.status == "lido"
        )

    def _show_placeholder(self, message: str) -> None:
        self._clear_detail()
        label = QLabel(message)
        label.setObjectName("alert_detail_placeholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.detail_layout.addWidget(label, 1)

    def _clear_detail(self) -> None:
        self.confirm_button = None
        self.close_button = None
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _section(title: str, rows: tuple[tuple[str, str], ...]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("alert_detail_section")
        layout = QVBoxLayout(frame)
        section_title = QLabel(title)
        section_title.setObjectName("alert_section_title")
        layout.addWidget(section_title)
        for key, value in rows:
            row = QFrame()
            row.setObjectName("alert_detail_row")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 3, 0, 3)
            key_label = QLabel(key)
            key_label.setObjectName("alert_detail_key")
            key_label.setMinimumWidth(145)
            value_label = QLabel(value)
            value_label.setObjectName("alert_detail_value")
            value_label.setTextFormat(Qt.TextFormat.PlainText)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_layout.addWidget(key_label)
            row_layout.addWidget(value_label, 1)
            layout.addWidget(row)
        return frame

    def _show_feedback(self, message: str, state: str) -> None:
        self.feedback_label.setText(message)
        self.feedback_label.setProperty("state", state)
        self.feedback_label.show()
        self._refresh_style(self.feedback_label)

    @classmethod
    def _list_text(cls, alert: AdminAlert) -> str:
        return (
            f"#{alert.id} · {cls._category_label(alert.category)} · "
            f"{cls._status_label(alert.status)}\n"
            f"{cls._format_datetime(alert.occurrence.detected_at)} · {alert.summary}"
        )

    @staticmethod
    def _category_label(category: str) -> str:
        return {
            "ergonomics": "Ergonomia",
            "ppe": "EPI",
            "monitoring": "Monitoramento",
            "risk_area": "Área de risco",
            "safety": "Segurança",
        }.get(category, "Segurança")

    @staticmethod
    def _status_label(status: str) -> str:
        return {
            "nao_lido": "Não confirmado",
            "lido": "Confirmado",
            "encerrado": "Encerrado",
        }.get(status, status)

    @staticmethod
    def _level_label(level: str) -> str:
        return "Crítico" if level == "critical" else "Atenção"

    @staticmethod
    def _actor_text(actor: object | None) -> str:
        if actor is None:
            return "—"
        actor_id = getattr(actor, "id", None)
        name = getattr(actor, "name", None)
        return f"{name} (#{actor_id})" if name and actor_id else "—"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        return value.astimezone().strftime("%d/%m/%Y %H:%M:%S") if value else "—"

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
