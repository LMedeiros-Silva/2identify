from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import DashboardSummary, RealtimeAlert


class DashboardPage(QWidget):
    """View passiva do resumo administrativo recebido da API."""

    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._has_data = False
        self.setObjectName("dashboard_page")
        self.criar_interface()

    def criar_interface(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(35, 30, 35, 30)
        layout_principal.setSpacing(20)

        titulo = QLabel("Dashboard")
        titulo.setObjectName("pagina_titulo")
        layout_principal.addWidget(titulo)

        subtitulo = QLabel("Visão geral da segurança operacional")
        subtitulo.setObjectName("pagina_subtitulo")
        layout_principal.addWidget(subtitulo)

        status_layout = QHBoxLayout()
        self.status_label = QLabel("Aguardando atualização da API.")
        self.status_label.setObjectName("dashboard_status")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label, 1)

        self.retry_button = QPushButton("Tentar novamente")
        self.retry_button.setObjectName("dashboard_retry")
        self.retry_button.clicked.connect(self.refresh_requested.emit)
        self.retry_button.hide()
        status_layout.addWidget(self.retry_button)
        layout_principal.addLayout(status_layout)

        self.realtime_status_label = QLabel("Canal em tempo real desconectado.")
        self.realtime_status_label.setObjectName("realtime_status")
        self.realtime_status_label.setWordWrap(True)
        layout_principal.addWidget(self.realtime_status_label)

        self.realtime_alert_banner = QLabel()
        self.realtime_alert_banner.setObjectName("realtime_alert_banner")
        self.realtime_alert_banner.setTextFormat(Qt.TextFormat.PlainText)
        self.realtime_alert_banner.setWordWrap(True)
        self.realtime_alert_banner.hide()
        layout_principal.addWidget(self.realtime_alert_banner)

        cards_layout = QGridLayout()
        cards_layout.setSpacing(18)

        self.card_funcionarios = self.criar_card(
            "Funcionários ativos", "—", "Funcionários ativos cadastrados"
        )
        self.card_conformidade = self.criar_card(
            "EPIs entregues", "—", "Percentual de associações entregues"
        )
        self.card_alertas = self.criar_card(
            "Alertas", "—", "Alertas registrados"
        )
        self.card_criticos = self.criar_card(
            "Críticos", "—", "Alertas críticos"
        )

        for column, card in enumerate(
            (
                self.card_funcionarios,
                self.card_conformidade,
                self.card_alertas,
                self.card_criticos,
            )
        ):
            cards_layout.addWidget(card, 0, column)
        layout_principal.addLayout(cards_layout)

        conteudo = QHBoxLayout()
        conteudo.setSpacing(20)

        painel_conformidade = QFrame()
        painel_conformidade.setObjectName("dashboard_painel")
        layout_conformidade = QVBoxLayout(painel_conformidade)

        titulo_conformidade = QLabel("Entrega de EPIs")
        titulo_conformidade.setObjectName("painel_titulo")
        layout_conformidade.addWidget(titulo_conformidade)

        self.texto_conformidade = QLabel(
            "Os dados de entrega serão carregados pela API."
        )
        self.texto_conformidade.setObjectName("painel_texto")
        self.texto_conformidade.setWordWrap(True)
        layout_conformidade.addWidget(self.texto_conformidade)
        layout_conformidade.addStretch()

        self.indicador_conformidade = QLabel("—")
        self.indicador_conformidade.setObjectName("indicador_conformidade")
        self.indicador_conformidade.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_conformidade.addWidget(self.indicador_conformidade)

        legenda = QLabel("Percentual de associações de EPI entregues")
        legenda.setObjectName("painel_texto")
        legenda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_conformidade.addWidget(legenda)
        conteudo.addWidget(painel_conformidade, 2)

        painel_alertas = QFrame()
        painel_alertas.setObjectName("dashboard_painel")
        layout_alertas = QVBoxLayout(painel_alertas)

        titulo_alertas = QLabel("Resumo de alertas")
        titulo_alertas.setObjectName("painel_titulo")
        layout_alertas.addWidget(titulo_alertas)

        self.texto_alertas = QLabel("Aguardando dados da API.")
        self.texto_alertas.setObjectName("sem_alertas")
        self.texto_alertas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.texto_alertas.setWordWrap(True)
        layout_alertas.addWidget(self.texto_alertas)
        conteudo.addWidget(painel_alertas, 1)

        layout_principal.addLayout(conteudo)
        layout_principal.addStretch()

    def criar_card(self, titulo: str, valor: str, descricao: str) -> QFrame:
        card = QFrame()
        card.setObjectName("dashboard_card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)

        titulo_label = QLabel(titulo)
        titulo_label.setObjectName("card_titulo")
        layout.addWidget(titulo_label)

        valor_label = QLabel(valor)
        valor_label.setObjectName("card_valor")
        layout.addWidget(valor_label)

        descricao_label = QLabel(descricao)
        descricao_label.setObjectName("card_descricao")
        descricao_label.setWordWrap(True)
        layout.addWidget(descricao_label)

        card.valor_label = valor_label  # type: ignore[attr-defined]
        return card

    def show_loading(self) -> None:
        if not self._has_data:
            self._set_placeholder_values()
        self.status_label.setText("Atualizando indicadores pela API...")
        self.status_label.setProperty("state", "loading")
        self.retry_button.setEnabled(False)
        self.retry_button.hide()
        self._refresh_style(self.status_label)

    def show_summary(self, summary: DashboardSummary) -> None:
        self._has_data = True
        percentage = self._format_percentage(summary.ppe_delivery_percentage)
        self.card_funcionarios.valor_label.setText(  # type: ignore[attr-defined]
            str(summary.active_employees)
        )
        self.card_conformidade.valor_label.setText(percentage)  # type: ignore[attr-defined]
        self.card_alertas.valor_label.setText(str(summary.alerts))  # type: ignore[attr-defined]
        self.card_criticos.valor_label.setText(  # type: ignore[attr-defined]
            str(summary.critical_alerts)
        )
        self.indicador_conformidade.setText(percentage)
        self.texto_conformidade.setText(
            f"{summary.delivered_ppe} de {summary.ppe_assignments} "
            "associações de EPI estão marcadas como entregues."
        )
        if summary.alerts == 0:
            self.texto_alertas.setText("Nenhum alerta registrado.")
        else:
            self.texto_alertas.setText(
                f"{summary.alerts} alerta(s) registrado(s), "
                f"sendo {summary.critical_alerts} crítico(s)."
            )

        generated_at = summary.generated_at.astimezone()
        self.status_label.setText(
            f"Atualizado pela API em {generated_at:%d/%m/%Y às %H:%M:%S}."
        )
        self.status_label.setProperty("state", "ready")
        self.retry_button.setEnabled(True)
        self.retry_button.setText("Atualizar")
        self.retry_button.show()
        self._refresh_style(self.status_label)

    def show_error(self, message: str) -> None:
        if not self._has_data:
            self._set_placeholder_values()
            self.texto_conformidade.setText(
                "Os indicadores ainda não foram recebidos da API."
            )
            self.texto_alertas.setText("Dados de alertas indisponíveis.")
        self.status_label.setText(message)
        self.status_label.setProperty("state", "error")
        self.retry_button.setEnabled(True)
        self.retry_button.setText("Tentar novamente")
        self.retry_button.show()
        self._refresh_style(self.status_label)

    def set_realtime_status(self, message: str, *, state: str) -> None:
        self.realtime_status_label.setText(message)
        self.realtime_status_label.setProperty("state", state)
        self._refresh_style(self.realtime_status_label)

    def show_realtime_alert(self, alert: RealtimeAlert) -> None:
        severity = "crítico" if alert.level == "critical" else "de atenção"
        self.realtime_alert_banner.setText(
            f"Novo alerta {severity} #{alert.alert_id}: {alert.summary}"
        )
        self.realtime_alert_banner.setProperty("severity", alert.level)
        self.realtime_alert_banner.show()
        self._refresh_style(self.realtime_alert_banner)

    def _set_placeholder_values(self) -> None:
        for card in (
            self.card_funcionarios,
            self.card_conformidade,
            self.card_alertas,
            self.card_criticos,
        ):
            card.valor_label.setText("—")  # type: ignore[attr-defined]
        self.indicador_conformidade.setText("—")

    @staticmethod
    def _format_percentage(value: float) -> str:
        if float(value).is_integer():
            formatted = str(int(value))
        else:
            formatted = f"{value:.1f}".replace(".", ",")
        return f"{formatted}%"

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
