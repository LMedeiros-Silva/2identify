from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.domain import AdminAlert, DashboardSummary, RealtimeAlert
from app.domain.ppe_management import (
    ActiveOperationOverallStatus,
    ActiveOperationSnapshot,
    PpeLiveState,
)
from app.ui.dashboard.chart_widgets import (
    AlertCategoryBarChart,
    AlertStatusDonutChart,
    AlertTrendChart,
    ChartBar,
    ChartSegment,
)
from app.ui.theme import TOKENS

_MAX_OPERATION_ROWS = 6
_MAX_RECENT_ALERTS = 5
# Idade a partir da qual a última observação recebida é destacada como antiga.
_STALE_OBSERVATION_SECONDS = 60

_OPERATION_STATUS = {
    ActiveOperationOverallStatus.COMPLIANT: ("Conforme", "safe"),
    ActiveOperationOverallStatus.ATTENTION: ("Atenção", "warn"),
    ActiveOperationOverallStatus.NON_COMPLIANT: ("Não conforme", "crit"),
}
_STATUS_ORDER = {
    ActiveOperationOverallStatus.NON_COMPLIANT: 0,
    ActiveOperationOverallStatus.ATTENTION: 1,
    ActiveOperationOverallStatus.COMPLIANT: 2,
}
_CATEGORY_LABELS = {
    "ppe": "EPI",
    "ergonomics": "Ergonomia",
    "risk_area": "Área de risco",
    "monitoring": "Monitoramento",
    "safety": "Segurança",
}
_ALERT_STATUS_LABELS = {
    "nao_lido": "Não confirmado",
    "lido": "Confirmado",
    "encerrado": "Encerrado",
}


@dataclass(frozen=True, slots=True)
class _RecentAlert:
    alert_id: int
    level: str
    category: str
    status: str
    summary: str
    detected_at: datetime
    employee: str | None
    realtime: bool = False


def _label(text: str = "", name: str = "", *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    # Qt indenta rótulos com margem/padding de QSS; o alinhamento fica com o layout.
    label.setIndent(0)
    return label


class _ElidedLabel(QLabel):
    """Single-line label that ends with "…" instead of clipping long text."""

    def __init__(self, text: str, name: str) -> None:
        super().__init__(text)
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), elided
        )


def _refresh(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _ClickableFrame(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class DashboardPage(QWidget):
    """Central de segurança: estado atual primeiro, histórico depois.

    A página é passiva: recebe o resumo da API, as operações ativas da
    Gestão de EPIs e os alertas da Central de alertas. Nada é estimado.
    """

    refresh_requested = Signal()
    navigate_requested = Signal(str)
    alert_open_requested = Signal(int)
    open_alerts_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._has_data = False
        self._operations: tuple[ActiveOperationSnapshot, ...] | None = None
        self._recent: tuple[_RecentAlert, ...] | None = None
        self._realtime_recent: list[_RecentAlert] = []
        self._timing_labels: list[tuple[ActiveOperationSnapshot, QLabel, QLabel]] = []
        self.setObjectName("dashboard_page")
        self.criar_interface()
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_timing)
        self._clock.start()

    # ======================================================
    # ESTRUTURA
    # ======================================================

    def criar_interface(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("dashboard_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        raiz.addWidget(scroll)

        conteudo = QWidget()
        conteudo.setObjectName("dashboard_conteudo")
        scroll.setWidget(conteudo)

        layout_principal = QVBoxLayout(conteudo)
        layout_principal.setContentsMargins(28, 22, 28, 28)
        layout_principal.setSpacing(16)

        layout_principal.addLayout(self._criar_topo())

        self.realtime_alert_banner = QLabel()
        self.realtime_alert_banner.setObjectName("realtime_alert_banner")
        self.realtime_alert_banner.setTextFormat(Qt.TextFormat.PlainText)
        self.realtime_alert_banner.setWordWrap(True)
        self.realtime_alert_banner.hide()
        layout_principal.addWidget(self.realtime_alert_banner)

        layout_principal.addLayout(self._criar_indicadores())

        agora = QHBoxLayout()
        agora.setSpacing(16)
        agora.addWidget(self._criar_painel_operacoes(), 8)
        agora.addWidget(self._criar_painel_alertas(), 5)
        layout_principal.addLayout(agora)

        layout_principal.addLayout(self._criar_historico())
        layout_principal.addStretch()

        self._render_operations()
        self._render_recent_alerts()

    def _criar_topo(self) -> QHBoxLayout:
        topo = QHBoxLayout()
        topo.setSpacing(16)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(_label("AGORA NA PLANTA", "dashboard_secao"))
        subtitulo = _label(
            "Operações em andamento, alertas e indicadores de segurança.", "pagina_subtitulo"
        )
        titulos.addWidget(subtitulo)
        topo.addLayout(titulos, 1)

        self.status_label = _label("Aguardando atualização da API.", "dashboard_status", wrap=True)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_label.setMaximumWidth(380)
        topo.addWidget(self.status_label)

        self.retry_button = QPushButton("Tentar novamente")
        self.retry_button.setObjectName("dashboard_retry")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.clicked.connect(self.refresh_requested.emit)
        self.retry_button.hide()
        topo.addWidget(self.retry_button)
        return topo

    def _criar_indicadores(self) -> QGridLayout:
        grade = QGridLayout()
        grade.setHorizontalSpacing(14)

        self.card_operacoes = self.criar_card(
            "Operações ativas", "—", "Aguardando operações ativas.", tom="hero"
        )
        self.card_alertas = self.criar_card(
            "Alertas em aberto", "—", "Novos e confirmados, ainda não encerrados."
        )
        self.card_criticos = self.criar_card(
            "Alertas críticos", "—", "Registrados no histórico."
        )
        self.card_funcionarios = self.criar_card(
            "Funcionários ativos", "—", "Funcionários ativos cadastrados"
        )
        self.card_conformidade = self.criar_card(
            "EPIs entregues", "—", "Os dados de entrega serão carregados pela API."
        )
        self.texto_conformidade = self.card_conformidade.descricao_label  # type: ignore[attr-defined]

        cards = (
            self.card_operacoes,
            self.card_alertas,
            self.card_criticos,
            self.card_funcionarios,
            self.card_conformidade,
        )
        for column, card in enumerate(cards):
            grade.addWidget(card, 0, column)
            grade.setColumnStretch(column, 1)
        return grade

    def criar_card(
        self, titulo: str, valor: str, descricao: str, *, tom: str = "neutral"
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("dashboard_card")
        card.setProperty("tone", tom)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

        titulo_label = _label(titulo.upper(), "card_titulo")
        layout.addWidget(titulo_label)

        valor_label = _label(valor, "card_valor")
        layout.addWidget(valor_label)

        descricao_label = _label(descricao, "card_descricao", wrap=True)
        layout.addWidget(descricao_label)
        layout.addStretch()

        card.valor_label = valor_label  # type: ignore[attr-defined]
        card.descricao_label = descricao_label  # type: ignore[attr-defined]
        return card

    def _cabecalho_painel(self, titulo: str, descricao: str) -> tuple[QHBoxLayout, QVBoxLayout]:
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(10)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        textos.addWidget(_label(titulo, "painel_titulo"))
        textos.addWidget(_label(descricao, "grafico_descricao", wrap=True))
        cabecalho.addLayout(textos, 1)
        return cabecalho, textos

    def _botao_link(self, texto: str, destino: str) -> QPushButton:
        botao = QPushButton(texto)
        botao.setObjectName("dashboard_link")
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.clicked.connect(lambda: self.navigate_requested.emit(destino))
        return botao

    def _criar_painel_operacoes(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("dashboard_painel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        cabecalho, _ = self._cabecalho_painel(
            "Operações em andamento",
            "Última observação de EPIs enviada por cada Operador.",
        )
        self.realtime_status_label = _label("Canal em tempo real desconectado.", "realtime_status")
        self.realtime_status_label.setProperty("state", "offline")
        cabecalho.addWidget(self.realtime_status_label, 0, Qt.AlignmentFlag.AlignTop)
        cabecalho.addWidget(
            self._botao_link("Gestão de EPIs", "epis"), 0, Qt.AlignmentFlag.AlignTop
        )
        layout.addLayout(cabecalho)

        self._operations_layout = QVBoxLayout()
        self._operations_layout.setSpacing(8)
        layout.addLayout(self._operations_layout)

        self.operations_empty = _label("", "dashboard_vazio", wrap=True)
        self.operations_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.operations_empty, 1)

        self.operations_more = _label("", "grafico_descricao")
        layout.addWidget(self.operations_more)
        layout.addStretch()
        return painel

    def _criar_painel_alertas(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("dashboard_painel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        cabecalho, _ = self._cabecalho_painel(
            "Alertas recentes", "Selecione um alerta para abrir os detalhes."
        )
        cabecalho.addWidget(self._botao_link("Ver todos", "alertas"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(cabecalho)

        self._alerts_layout = QVBoxLayout()
        self._alerts_layout.setSpacing(8)
        layout.addLayout(self._alerts_layout)

        self.alerts_empty = _label("", "dashboard_vazio", wrap=True)
        self.alerts_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.alerts_empty, 1)
        layout.addStretch()
        return painel

    def _criar_historico(self) -> QVBoxLayout:
        secao = QVBoxLayout()
        secao.setSpacing(10)

        cabecalho = QHBoxLayout()
        cabecalho.addWidget(_label("HISTÓRICO DE ALERTAS", "dashboard_secao"))
        cabecalho.addStretch()
        self.texto_alertas = _label("Aguardando dados da API.", "painel_texto")
        cabecalho.addWidget(self.texto_alertas)
        secao.addLayout(cabecalho)

        graficos = QHBoxLayout()
        graficos.setSpacing(16)
        self.alert_trend_chart = AlertTrendChart()
        graficos.addWidget(
            self._criar_painel_grafico(
                "Evolução dos alertas",
                "Ocorrências registradas nos últimos 7 dias",
                self.alert_trend_chart,
            ),
            2,
        )
        self.alert_category_chart = AlertCategoryBarChart()
        graficos.addWidget(
            self._criar_painel_grafico(
                "Alertas por categoria",
                "Origem das ocorrências registradas",
                self.alert_category_chart,
            ),
            1,
        )
        self.alert_status_chart = AlertStatusDonutChart()
        graficos.addWidget(
            self._criar_painel_grafico(
                "Situação dos alertas",
                "Andamento do tratamento administrativo",
                self.alert_status_chart,
            ),
            1,
        )
        for chart in (self.alert_trend_chart, self.alert_category_chart, self.alert_status_chart):
            chart.setMinimumHeight(180)
        secao.addLayout(graficos)
        return secao

    @staticmethod
    def _criar_painel_grafico(
        titulo: str,
        descricao: str,
        grafico: QWidget,
    ) -> QFrame:
        painel = QFrame()
        painel.setObjectName("dashboard_grafico_painel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(3)
        titulo_label = QLabel(titulo)
        titulo_label.setObjectName("grafico_titulo")
        layout.addWidget(titulo_label)
        descricao_label = QLabel(descricao)
        descricao_label.setObjectName("grafico_descricao")
        descricao_label.setWordWrap(True)
        layout.addWidget(descricao_label)
        layout.addSpacing(4)
        layout.addWidget(grafico, 1)
        return painel

    # ======================================================
    # RESUMO DA API
    # ======================================================

    def show_loading(self) -> None:
        if not self._has_data:
            self._set_placeholder_values()
        self.status_label.setText("Atualizando indicadores pela API...")
        self.status_label.setProperty("state", "loading")
        self.retry_button.setEnabled(False)
        self.retry_button.hide()
        _refresh(self.status_label)

    def show_summary(self, summary: DashboardSummary) -> None:
        self._has_data = True
        percentage = self._format_percentage(summary.ppe_delivery_percentage)
        status = summary.alert_status
        open_alerts = status.new + status.confirmed

        self.card_funcionarios.valor_label.setText(  # type: ignore[attr-defined]
            str(summary.active_employees)
        )
        self.card_conformidade.valor_label.setText(percentage)  # type: ignore[attr-defined]
        self.texto_conformidade.setText(
            f"{summary.delivered_ppe} de {summary.ppe_assignments} "
            "associações de EPI estão marcadas como entregues."
        )
        self.card_alertas.valor_label.setText(str(open_alerts))  # type: ignore[attr-defined]
        self.card_alertas.descricao_label.setText(  # type: ignore[attr-defined]
            f"{status.new} novo(s) · {status.confirmed} confirmado(s)"
        )
        self._set_tone(self.card_alertas, "warn" if open_alerts else "neutral")
        self.card_criticos.valor_label.setText(  # type: ignore[attr-defined]
            str(summary.critical_alerts)
        )
        self.card_criticos.descricao_label.setText(  # type: ignore[attr-defined]
            f"De {summary.alerts} alerta(s) registrado(s) no histórico."
        )
        self._set_tone(self.card_criticos, "crit" if summary.critical_alerts else "neutral")
        self.open_alerts_changed.emit(open_alerts)

        if summary.alerts == 0:
            self.texto_alertas.setText("Nenhum alerta registrado.")
        else:
            self.texto_alertas.setText(
                f"{summary.alerts} alerta(s) registrado(s), "
                f"sendo {summary.critical_alerts} crítico(s)."
            )
        self.alert_trend_chart.set_points(
            tuple(
                (item.day.strftime("%d/%m"), item.alerts)
                for item in summary.alert_trend
            )
        )
        categories = summary.alert_categories
        self.alert_category_chart.set_bars(
            (
                ChartBar("EPI", categories.ppe, TOKENS["brand_600"]),
                ChartBar("Ergonomia", categories.ergonomics, TOKENS["brand_800"]),
                ChartBar("Área de risco", categories.risk_area, TOKENS["brand_400"]),
                ChartBar("Monitoramento", categories.monitoring, TOKENS["nav_500"]),
                ChartBar("Outros", categories.other, TOKENS["ink_300"]),
            )
        )
        self.alert_status_chart.set_segments(
            (
                ChartSegment("Novos", status.new, TOKENS["crit_500"]),
                ChartSegment("Confirmados", status.confirmed, TOKENS["warn_500"]),
                ChartSegment("Encerrados", status.closed, TOKENS["safe_500"]),
                ChartSegment("Outros", status.other, TOKENS["ink_300"]),
            )
        )

        generated_at = summary.generated_at.astimezone()
        self.status_label.setText(f"Atualizado pela API em {generated_at:%d/%m/%Y às %H:%M:%S}.")
        self.status_label.setProperty("state", "ready")
        self.retry_button.setEnabled(True)
        self.retry_button.setText("Atualizar")
        self.retry_button.show()
        _refresh(self.status_label)

    def show_error(self, message: str) -> None:
        if not self._has_data:
            self._set_placeholder_values()
            self.texto_conformidade.setText("Os indicadores ainda não foram recebidos da API.")
            self.texto_alertas.setText("Dados de alertas indisponíveis.")
        self.status_label.setText(message)
        self.status_label.setProperty("state", "error")
        self.retry_button.setEnabled(True)
        self.retry_button.setText("Tentar novamente")
        self.retry_button.show()
        _refresh(self.status_label)

    # ======================================================
    # TEMPO REAL
    # ======================================================

    def set_realtime_status(self, message: str, *, state: str) -> None:
        self.realtime_status_label.setText(
            {
                "connected": "● Ao vivo",
                "connecting": "● Conectando",
            }.get(state, "● Sem tempo real")
        )
        self.realtime_status_label.setToolTip(message)
        self.realtime_status_label.setProperty("state", state)
        _refresh(self.realtime_status_label)

    def show_realtime_alert(self, alert: RealtimeAlert) -> None:
        severity = "crítico" if alert.level == "critical" else "de atenção"
        category = {
            "ppe": " de EPI",
            "ergonomics": " ergonômico",
            "risk_area": " de área de risco",
            "monitoring": " de monitoramento",
        }.get(alert.category, "")
        self.realtime_alert_banner.setText(
            f"Novo alerta{category} {severity} #{alert.alert_id}: {alert.summary}"
        )
        self.realtime_alert_banner.setProperty("severity", alert.level)
        self.realtime_alert_banner.show()
        _refresh(self.realtime_alert_banner)

        self._realtime_recent = [
            item for item in self._realtime_recent if item.alert_id != alert.alert_id
        ]
        self._realtime_recent.insert(
            0,
            _RecentAlert(
                alert.alert_id,
                alert.level,
                alert.category,
                alert.status,
                alert.summary,
                alert.detected_at,
                None,
                realtime=True,
            ),
        )
        del self._realtime_recent[_MAX_RECENT_ALERTS:]
        self._render_recent_alerts()

    # ======================================================
    # OPERAÇÕES ATIVAS
    # ======================================================

    def set_active_operations(self, snapshots: tuple[ActiveOperationSnapshot, ...]) -> None:
        self._operations = tuple(snapshots)
        self._render_operations()

    def _render_operations(self) -> None:
        self._clear_layout(self._operations_layout)
        self._timing_labels.clear()
        operations = self._operations

        if operations is None:
            self.card_operacoes.valor_label.setText("—")  # type: ignore[attr-defined]
            self.card_operacoes.descricao_label.setText(  # type: ignore[attr-defined]
                "Aguardando operações ativas."
            )
            self.operations_empty.setText("Aguardando as operações ativas informadas pela API.")
            self.operations_empty.show()
            self.operations_more.hide()
            return

        attention = sum(
            item.overall_status is ActiveOperationOverallStatus.ATTENTION for item in operations
        )
        non_compliant = sum(
            item.overall_status is ActiveOperationOverallStatus.NON_COMPLIANT
            for item in operations
        )
        self.card_operacoes.valor_label.setText(str(len(operations)))  # type: ignore[attr-defined]
        if not operations:
            description = "Nenhuma operação em andamento."
        elif attention or non_compliant:
            description = f"{non_compliant} não conforme(s) · {attention} em atenção"
        else:
            description = "Todas conformes na última observação."
        self.card_operacoes.descricao_label.setText(description)  # type: ignore[attr-defined]

        ordered = sorted(
            operations, key=lambda item: (_STATUS_ORDER[item.overall_status], item.started_at)
        )
        for item in ordered[:_MAX_OPERATION_ROWS]:
            self._operations_layout.addWidget(self._operation_row(item))

        self.operations_empty.setText(
            "Nenhuma operação ativa no momento.\n"
            "As operações iniciadas no Operador aparecem aqui em tempo real."
        )
        self.operations_empty.setVisible(not operations)
        hidden = len(operations) - _MAX_OPERATION_ROWS
        self.operations_more.setText(
            f"+ {hidden} operação(ões) ativa(s). Veja todas em Gestão de EPIs."
        )
        self.operations_more.setVisible(hidden > 0)
        self._update_timing()

    def _operation_row(self, item: ActiveOperationSnapshot) -> QFrame:
        label, tone = _OPERATION_STATUS[item.overall_status]
        row = _ClickableFrame()
        row.setObjectName("dashboard_operacao")
        row.setProperty("tone", tone)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setToolTip("Abrir na Gestão de EPIs")
        row.clicked.connect(lambda: self.navigate_requested.emit("epis"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 9, 12, 9)
        layout.setSpacing(14)

        who = QVBoxLayout()
        who.setSpacing(1)
        who.addWidget(_ElidedLabel(item.operator_name, "linha_titulo"))
        who.addWidget(
            _ElidedLabel(
                f"{item.operation_name} · {item.camera_name or 'Câmera não informada'}",
                "linha_texto",
            )
        )
        layout.addLayout(who, 1)

        ppe = QVBoxLayout()
        ppe.setSpacing(1)
        confirmed = sum(entry.state is PpeLiveState.CONFIRMED for entry in item.ppe)
        ppe.addWidget(
            _label(
                f"EPIs {confirmed}/{len(item.ppe)}" if item.ppe else "Sem EPI exigido",
                "linha_valor",
            )
        )
        absent = [entry.name for entry in item.ppe if entry.state is PpeLiveState.ABSENT]
        pending = [
            entry.name
            for entry in item.ppe
            if entry.state in (PpeLiveState.COLLECTING, PpeLiveState.UNSTABLE)
        ]
        unmapped = [entry.name for entry in item.ppe if entry.state is PpeLiveState.UNMAPPED]
        if absent:
            detail = _ElidedLabel("Ausente: " + ", ".join(absent), "linha_alerta")
        elif pending:
            detail = _ElidedLabel("Em verificação: " + ", ".join(pending), "linha_texto")
        elif unmapped:
            detail = _ElidedLabel("Sem mapeamento: " + ", ".join(unmapped), "linha_texto")
        else:
            detail = _ElidedLabel("Todos confirmados" if item.ppe else "—", "linha_texto")
        ppe.addWidget(detail)
        ppe_box = QWidget()
        ppe_box.setLayout(ppe)
        ppe_box.setFixedWidth(158)
        layout.addWidget(ppe_box)

        timing = QVBoxLayout()
        timing.setSpacing(1)
        duration = _label("", "linha_valor")
        age = _label("", "linha_texto")
        timing.addWidget(duration)
        timing.addWidget(age)
        timing_box = QWidget()
        timing_box.setLayout(timing)
        timing_box.setFixedWidth(96)
        layout.addWidget(timing_box)
        self._timing_labels.append((item, duration, age))

        chip = _label(label, "status_chip")
        chip.setProperty("tone", tone)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setFixedWidth(104)
        layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _update_timing(self) -> None:
        now = datetime.now(UTC)
        for item, duration, age in self._timing_labels:
            elapsed = max(0, int((now - item.started_at).total_seconds()))
            duration.setText(
                f"{elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}"
            )
            seconds = max(0, int((now - item.observed_at).total_seconds()))
            age.setText(
                f"obs. há {seconds}s" if seconds < 60 else f"obs. há {seconds // 60} min"
            )
            stale = "true" if seconds >= _STALE_OBSERVATION_SECONDS else "false"
            if age.property("stale") != stale:
                age.setProperty("stale", stale)
                _refresh(age)

    # ======================================================
    # ALERTAS RECENTES
    # ======================================================

    def set_recent_alerts(self, alerts: tuple[AdminAlert, ...]) -> None:
        ordered = sorted(alerts, key=lambda alert: alert.occurrence.detected_at, reverse=True)
        self._recent = tuple(
            _RecentAlert(
                alert.id,
                alert.level,
                alert.category,
                alert.status,
                alert.summary,
                alert.occurrence.detected_at,
                alert.occurrence.employee.name if alert.occurrence.employee else None,
            )
            for alert in ordered[:_MAX_RECENT_ALERTS]
        )
        known = {item.alert_id for item in self._recent}
        self._realtime_recent = [
            item for item in self._realtime_recent if item.alert_id not in known
        ]
        self._render_recent_alerts()

    def _render_recent_alerts(self) -> None:
        self._clear_layout(self._alerts_layout)
        items = [*self._realtime_recent, *(self._recent or ())][:_MAX_RECENT_ALERTS]
        for item in items:
            self._alerts_layout.addWidget(self._alert_row(item))
        if self._recent is None and not items:
            self.alerts_empty.setText("Aguardando o histórico de alertas.")
        else:
            self.alerts_empty.setText(
                "Nenhum alerta registrado.\nAs ocorrências detectadas aparecem aqui."
            )
        self.alerts_empty.setVisible(not items)

    def _alert_row(self, item: _RecentAlert) -> QFrame:
        level = "crit" if item.level == "critical" else "warn"
        row = _ClickableFrame()
        row.setObjectName("dashboard_alerta")
        row.setProperty("tone", level)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setToolTip("Abrir na Central de alertas")
        row.clicked.connect(lambda: self.alert_open_requested.emit(item.alert_id))
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 8, 12, 8)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        chip = _label("Crítico" if level == "crit" else "Atenção", "status_chip")
        chip.setProperty("tone", level)
        top.addWidget(chip)
        top.addWidget(
            _label(
                f"{_CATEGORY_LABELS.get(item.category, 'Segurança')} · #{item.alert_id}",
                "linha_valor",
            )
        )
        top.addStretch()
        when = item.detected_at.astimezone()
        today = datetime.now().astimezone().date()
        top.addWidget(
            _label(
                f"{when:%H:%M}" if when.date() == today else f"{when:%d/%m %H:%M}",
                "linha_texto",
            )
        )
        layout.addLayout(top)

        layout.addWidget(_ElidedLabel(item.summary, "linha_titulo"))

        details = [_ALERT_STATUS_LABELS.get(item.status, item.status)]
        if item.employee:
            details.append(item.employee)
        if item.realtime:
            details.append("recebido agora")
        layout.addWidget(_label(" · ".join(details), "linha_texto"))
        return row

    # ======================================================
    # AUXILIARES
    # ======================================================

    def _set_placeholder_values(self) -> None:
        for card in (
            self.card_funcionarios,
            self.card_conformidade,
            self.card_alertas,
            self.card_criticos,
        ):
            card.valor_label.setText("—")  # type: ignore[attr-defined]
        self.alert_trend_chart.set_points(())
        self.alert_category_chart.set_bars(())
        self.alert_status_chart.set_segments(())

    def _set_tone(self, card: QFrame, tone: str) -> None:
        if card.property("tone") != tone:
            card.setProperty("tone", tone)
            for widget in (card, *card.findChildren(QLabel)):
                _refresh(widget)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    @staticmethod
    def _format_percentage(value: float) -> str:
        if float(value).is_integer():
            formatted = str(int(value))
        else:
            formatted = f"{value:.1f}".replace(".", ",")
        return f"{formatted}%"

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        _refresh(widget)
