from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.domain import AdminAlert, AdminAlertPage, RealtimeAlert
from app.ui.safety_widgets import StateChip
from app.ui.theme import TOKENS

_MAX_REALTIME_ITEMS = 100
_FILTERS = (
    ("todos", "Todos"),
    ("nao_lido", "Não confirmados"),
    ("lido", "Confirmados"),
    ("encerrado", "Encerrados"),
)
_ROW_HEIGHT = 74


def _tone(level: str, category: str) -> str:
    if category == "monitoring":
        return "inc"
    return "crit" if level == "critical" else "warn"


def _relative(value: datetime) -> str:
    now = datetime.now(value.tzinfo)
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return "agora"
    if seconds < 3600:
        return f"há {seconds // 60} min"
    if seconds < 6 * 3600:
        return f"há {seconds // 3600} h"
    local = value.astimezone()
    today = datetime.now().astimezone().date()
    if local.date() == today:
        return f"hoje {local:%H:%M}"
    if (today - local.date()).days == 1:
        return "ontem"
    return f"{local:%d/%m/%Y}"


class _AlertRow(QFrame):
    """One inbox row: severity stripe, title, category and who, state and age."""

    def __init__(
        self,
        alert_id: int,
        title: str,
        meta: str,
        level: str,
        category: str,
        when: str,
    ) -> None:
        super().__init__()
        self.setObjectName("alert_row")
        self.setProperty("tone", _tone(level, category))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("alert_row_title")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setWordWrap(True)
        texts.addWidget(title_label)
        meta_label = QLabel(meta)
        meta_label.setObjectName("alert_row_meta")
        meta_label.setTextFormat(Qt.TextFormat.PlainText)
        texts.addWidget(meta_label)
        layout.addLayout(texts, 1)
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(
            StateChip("Crítico" if level == "critical" else "Atenção", _tone(level, category)),
            0,
            Qt.AlignmentFlag.AlignRight,
        )
        when_label = QLabel(when)
        when_label.setObjectName("alert_row_meta")
        right.addWidget(when_label, 0, Qt.AlignmentFlag.AlignRight)
        right.addStretch()
        layout.addLayout(right)
        self.alert_id = alert_id


class _LifecycleStepper(QWidget):
    """Detected → received → confirmed → closed, filled up to the current step."""

    def __init__(self, steps: tuple[tuple[str, str, bool], ...]) -> None:
        super().__init__()
        self._steps = steps
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(480, 64)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        count = len(self._steps)
        width = self.width() / count
        blue = QColor(TOKENS["brand_600"])
        line = QColor(TOKENS["line_200"])
        current = next((index for index, step in enumerate(self._steps) if not step[2]), count)
        for index, (title, detail, done) in enumerate(self._steps):
            x = index * width
            painter.setPen(QPen(blue if done else line, 2))
            painter.drawLine(QPointF(x + 7, 8), QPointF(x + width, 8))
            painter.setPen(QPen(blue if done or index == current else line, 2))
            painter.setBrush(blue if done else QColor(TOKENS["surface_1"]))
            painter.drawEllipse(QRectF(x + 1, 2, 12, 12))
            title_font = QFont(self.font())
            title_font.setPixelSize(13)
            title_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(title_font)
            painter.setPen(QColor(TOKENS["ink_900"]))
            painter.drawText(QRectF(x, 22, width - 8, 20), Qt.AlignmentFlag.AlignLeft, title)
            detail_font = QFont(self.font())
            detail_font.setPixelSize(12)
            painter.setFont(detail_font)
            painter.setPen(QColor(TOKENS["ink_500"]))
            painter.drawText(QRectF(x, 42, width - 8, 20), Qt.AlignmentFlag.AlignLeft, detail)
        painter.end()


class AlertsPage(QWidget):
    """Persistent alert inbox with complete occurrence details and actions."""

    refresh_requested = Signal()
    alert_selected = Signal(int)
    confirm_requested = Signal(int)
    close_requested = Signal(int)
    alerts_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("alerts_page")
        self._alerts: dict[int, AdminAlert] = {}
        self._selected_alert_id: int | None = None
        self._action_busy = False
        self._filter = "todos"
        self.confirm_button: QPushButton | None = None
        self.close_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        # O cabeçalho da janela já mostra o canal em tempo real; o texto
        # detalhado fica disponível como dica no rótulo do painel.
        self.connection_status = QLabel("Canal em tempo real desconectado.", self)
        self.connection_status.setObjectName("realtime_status")
        self.connection_status.hide()

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
        splitter.setHandleWidth(16)

        list_panel = QFrame()
        list_panel.setObjectName("alerts_list_panel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(1, 14, 1, 1)
        list_layout.setSpacing(10)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(16, 0, 14, 0)
        title_row.setSpacing(10)
        list_title = QLabel("Alertas registrados")
        list_title.setObjectName("alert_section_title")
        title_row.addWidget(list_title)
        self.count_label = QLabel("Carregando...")
        self.count_label.setObjectName("alert_muted")
        title_row.addWidget(self.count_label)
        title_row.addStretch()
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setObjectName("alerts_refresh")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        title_row.addWidget(self.refresh_button)
        list_layout.addLayout(title_row)

        filters = QHBoxLayout()
        filters.setContentsMargins(16, 0, 16, 2)
        filters.setSpacing(6)
        self.filter_buttons: dict[str, QPushButton] = {}
        for key, text in _FILTERS:
            button = QPushButton(text)
            button.setObjectName("alert_filter")
            button.setCheckable(True)
            button.setChecked(key == "todos")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=key: self._set_filter(value))
            filters.addWidget(button)
            self.filter_buttons[key] = button
        filters.addStretch()
        list_layout.addLayout(filters)

        self.alert_list = QListWidget()
        self.alert_list.setObjectName("alert_list")
        self.alert_list.setSpacing(0)
        self.alert_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.alert_list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.alert_list, 1)
        self.empty_label = QLabel("Nenhum alerta registrado.")
        self.empty_label.setObjectName("sem_alertas")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        list_layout.addWidget(self.empty_label, 1)
        splitter.addWidget(list_panel)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("alert_detail_scroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_container = QWidget()
        self.detail_container.setObjectName("alert_detail_container")
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(0)
        self.detail_scroll.setWidget(self.detail_container)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 9)
        splitter.setStretchFactor(1, 16)
        splitter.setSizes([400, 700])
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
            item = self._add_row(self.alert_list.count(), alert.id, alert.summary)
            self._render_row(item, alert)
            if alert.id == selected_id:
                self.alert_list.setCurrentItem(item)
        self.count_label.setText(f"{page.total} no histórico")
        self._update_filter_counts()
        self._apply_filter()
        self.empty_label.setVisible(not page.items)
        self.alert_list.setVisible(bool(page.items))
        self.refresh_button.setEnabled(True)
        if not page.items:
            self._selected_alert_id = None
            self._show_placeholder("Nenhum alerta foi registrado até o momento.")
        elif self.alert_list.currentItem() is None:
            self.alert_list.setCurrentRow(0)
        self.alerts_changed.emit(tuple(self._alerts.values()))

    def update_alert(self, alert: AdminAlert) -> None:
        self._alerts[alert.id] = alert
        for index in range(self.alert_list.count()):
            item = self.alert_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == alert.id:
                self._render_row(item, alert)
                item.setToolTip(alert.summary)
                break
        self._selected_alert_id = alert.id
        self._update_filter_counts()
        self._show_alert(alert)
        self.alerts_changed.emit(tuple(self._alerts.values()))

    def select_alert(self, alert_id: int) -> None:
        """Select an alert already listed, as requested from the dashboard."""

        for index in range(self.alert_list.count()):
            item = self.alert_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == alert_id:
                if item.isHidden():
                    self._set_filter("todos")
                self.alert_list.setCurrentItem(item)
                self.alert_list.scrollToItem(item)
                return

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
        item = self._add_row(0, alert.alert_id, alert.summary)
        item.setData(Qt.ItemDataRole.UserRole + 1, alert.status)
        self.alert_list.setItemWidget(
            item,
            _AlertRow(
                alert.alert_id,
                alert.summary,
                f"{category} · #{alert.alert_id} · {self._status_label(alert.status)}",
                alert.level,
                alert.category,
                _relative(alert.detected_at),
            ),
        )
        while self.alert_list.count() > _MAX_REALTIME_ITEMS:
            self.alert_list.takeItem(self.alert_list.count() - 1)
        self.alert_list.show()
        self.empty_label.hide()
        self.count_label.setText(f"{self.alert_list.count()} recebidos nesta sessão")

    def show_loading(self) -> None:
        self.refresh_button.setEnabled(False)
        self.count_label.setText("Carregando alertas...")
        self._show_feedback("Consultando o histórico de alertas...", "loading")

    def show_error(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self._action_busy = False
        loaded_count = self.alert_list.count()
        self.count_label.setText(
            f"{loaded_count} carregados" if loaded_count else "Histórico indisponível."
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

    # ======================================================
    # LISTA E FILTROS
    # ======================================================

    def _add_row(self, position: int, alert_id: int, summary: str) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, alert_id)
        item.setToolTip(summary)
        item.setSizeHint(QSize(0, _ROW_HEIGHT))
        self.alert_list.insertItem(position, item)
        return item

    def _render_row(self, item: QListWidgetItem, alert: AdminAlert) -> None:
        item.setData(Qt.ItemDataRole.UserRole + 1, alert.status)
        meta = [f"{self._category_label(alert.category, alert.occurrence.type)} · #{alert.id}"]
        if alert.occurrence.employee is not None:
            meta.append(alert.occurrence.employee.name)
        self.alert_list.setItemWidget(
            item,
            _AlertRow(
                alert.id,
                alert.summary,
                " · ".join(meta),
                alert.level,
                alert.category,
                _relative(alert.occurrence.detected_at),
            ),
        )

    def _set_filter(self, value: str) -> None:
        self._filter = value
        for key, button in self.filter_buttons.items():
            button.setChecked(key == value)
        self._apply_filter()

    def _apply_filter(self) -> None:
        for index in range(self.alert_list.count()):
            item = self.alert_list.item(index)
            status = item.data(Qt.ItemDataRole.UserRole + 1)
            item.setHidden(self._filter != "todos" and status != self._filter)

    def _update_filter_counts(self) -> None:
        counts = {key: 0 for key, _ in _FILTERS}
        for alert in self._alerts.values():
            counts["todos"] += 1
            if alert.status in counts:
                counts[alert.status] += 1
        for key, text in _FILTERS:
            self.filter_buttons[key].setText(f"{text}  {counts[key]}")

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        for item, selected in ((previous, False), (current, True)):
            row = self.alert_list.itemWidget(item) if item is not None else None
            if row is not None:
                row.setProperty("selected", "true" if selected else "false")
                self._refresh_style(row)
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

    # ======================================================
    # DETALHE
    # ======================================================

    def _show_alert(self, alert: AdminAlert) -> None:
        self._clear_detail()
        occurrence = alert.occurrence
        employee = occurrence.employee
        camera = occurrence.camera
        context = alert.operational_context
        tone = _tone(alert.level, alert.category)

        header = QFrame()
        header.setObjectName("alert_detail_header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(StateChip(self._level_label(alert.level), tone))
        self.detail_title = QLabel(f"Alerta #{alert.id}")
        self.detail_title.setObjectName("alert_detail_kicker")
        top.addWidget(self.detail_title)
        top.addStretch()
        self.confirm_button = QPushButton("Confirmar recebimento")
        self.confirm_button.setObjectName("alert_confirm")
        self.confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_button.clicked.connect(self._request_confirmation)
        top.addWidget(self.confirm_button)
        self.close_button = QPushButton("Encerrar ocorrência")
        self.close_button.setObjectName("alert_close")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self._request_close)
        top.addWidget(self.close_button)
        header_layout.addLayout(top)
        summary = QLabel(alert.summary)
        summary.setObjectName("alert_detail_title")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        header_layout.addWidget(summary)
        self.detail_status = QLabel(
            f"{self._category_label(alert.category, occurrence.type)} · "
            f"{self._status_label(alert.status)} · detectado "
            f"{_relative(occurrence.detected_at)} "
            f"({self._format_datetime(occurrence.detected_at)})"
        )
        self.detail_status.setObjectName("alert_detail_status")
        self.detail_status.setProperty("status", alert.status)
        self.detail_status.setWordWrap(True)
        header_layout.addWidget(self.detail_status)
        self.detail_layout.addWidget(header)

        why = self._section("Por que a IA alertou")
        why_text = QLabel(self._why_text(alert))
        why_text.setObjectName("alert_why")
        why_text.setTextFormat(Qt.TextFormat.RichText)
        why_text.setWordWrap(True)
        why.layout().addWidget(why_text)
        self.detail_layout.addWidget(why)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        where = self._section("Onde e com quem")
        self._rows(
            where,
            (
                ("Funcionário", employee.name if employee else "Não identificado"),
                ("Matrícula", employee.registration if employee else "—"),
                (
                    "Setor",
                    employee.sector.name if employee and employee.sector else "—",
                ),
                ("Câmera", camera.name if camera else "Não informada"),
                ("Local da câmera", (camera.description or "—") if camera else "—"),
                (
                    "Área de risco",
                    f"#{context.risk_area_id}" if context and context.risk_area_id else "—",
                ),
            ),
        )
        where.setProperty("column", "left")
        grid.addWidget(where, 0, 0)
        evidence = self._section("Evidência")
        if occurrence.image_reference or occurrence.video_reference:
            self._rows(
                evidence,
                (
                    ("Imagem", occurrence.image_reference or "—"),
                    ("Vídeo", occurrence.video_reference or "—"),
                ),
                key_width=70,
            )
        else:
            missing = QLabel("A estação não enviou imagem nem vídeo para este alerta.")
            missing.setObjectName("alert_no_evidence")
            missing.setWordWrap(True)
            evidence.layout().addWidget(missing)
        evidence.layout().addStretch()
        grid.addWidget(evidence, 0, 1)
        grid.setColumnStretch(0, 6)
        grid.setColumnStretch(1, 5)
        holder = QWidget()
        holder.setLayout(grid)
        self.detail_layout.addWidget(holder)

        lifecycle = self._section("Ciclo do alerta")
        lifecycle.layout().addWidget(
            _LifecycleStepper(
                (
                    ("Detectado", self._time(occurrence.detected_at), True),
                    (
                        "Recebido no Admin",
                        self._time(alert.received_at),
                        alert.received_at is not None,
                    ),
                    (
                        "Confirmado",
                        self._time(alert.confirmed_at) if alert.confirmed_at else "pendente",
                        alert.confirmed_at is not None,
                    ),
                    (
                        "Encerrado",
                        self._time(alert.closed_at) if alert.closed_at else "pendente",
                        alert.closed_at is not None,
                    ),
                )
            )
        )
        self._rows(
            lifecycle,
            (
                ("Confirmado por", self._actor_text(alert.confirmed_by)),
                ("Encerrado por", self._actor_text(alert.closed_by)),
                ("Observação", alert.observation or "—"),
            ),
        )
        self.detail_layout.addWidget(lifecycle)

        technical = self._section("Dados técnicos")
        self._rows(
            technical,
            (
                ("Ocorrência", f"#{occurrence.id} · {occurrence.type}"),
                ("Descrição", occurrence.description or "—"),
                ("Operação", f"#{context.operation_id}" if context else "—"),
                ("Operador da estação", self._actor_text(context.operator) if context else "—"),
                ("Violação", context.violation_type if context else occurrence.type),
                ("Chave", context.subject_key if context else "—"),
                ("Sessão de trabalho", str(context.work_session_id) if context else "—"),
                ("Evento", str(context.event_id) if context else "—"),
                (
                    "Ingerido em",
                    self._format_datetime(context.received_at) if context else "—",
                ),
            ),
        )
        technical.setProperty("last", "true")
        self.detail_layout.addWidget(technical)
        self.detail_layout.addStretch()
        self._refresh_actions()

    def _why_text(self, alert: AdminAlert) -> str:
        occurrence = alert.occurrence
        parts = [f"<b>{self._escape(occurrence.description or alert.summary)}</b>."]
        if occurrence.employee is not None:
            parts.append(f"Funcionário: <b>{self._escape(occurrence.employee.name)}</b>.")
        if occurrence.confidence is not None:
            confidence = (
                f"{occurrence.confidence * 100:.0f}%".replace(".", ",")
                if occurrence.confidence <= 1
                else str(occurrence.confidence)
            )
            parts.append(f"Confiança da IA: {confidence}.")
        if alert.observation:
            parts.append(f"Observação da estação: {self._escape(alert.observation)}.")
        if alert.category == "monitoring":
            parts.append("Inconclusivo significa que a IA não conseguiu confirmar nem negar.")
        return " ".join(parts)

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
                widget.hide()
                widget.deleteLater()

    @staticmethod
    def _section(title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("alert_detail_section")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(8)
        section_title = QLabel(title)
        section_title.setObjectName("alert_section_title")
        layout.addWidget(section_title)
        return frame

    @staticmethod
    def _rows(
        frame: QFrame, rows: tuple[tuple[str, str], ...], *, key_width: int = 130
    ) -> None:
        for key, value in rows:
            row = QFrame()
            row.setObjectName("alert_detail_row")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 1, 0, 1)
            key_label = QLabel(key)
            key_label.setObjectName("alert_detail_key")
            key_label.setFixedWidth(key_width)
            value_label = QLabel(value)
            value_label.setObjectName("alert_detail_value")
            value_label.setTextFormat(Qt.TextFormat.PlainText)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_layout.addWidget(key_label, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(value_label, 1)
            frame.layout().addWidget(row)

    def _show_feedback(self, message: str, state: str) -> None:
        self.feedback_label.setText(message)
        self.feedback_label.setProperty("state", state)
        self.feedback_label.show()
        self._refresh_style(self.feedback_label)

    @staticmethod
    def _category_label(category: str, occurrence_type: str | None = None) -> str:
        if occurrence_type == "fall_detected":
            return "Queda"
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
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _time(value: datetime | None) -> str:
        if value is None:
            return "—"
        local = value.astimezone()
        today = datetime.now().astimezone().date()
        return f"{local:%H:%M}" if local.date() == today else f"{local:%d/%m %H:%M}"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        return value.astimezone().strftime("%d/%m/%Y %H:%M:%S") if value else "—"

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
