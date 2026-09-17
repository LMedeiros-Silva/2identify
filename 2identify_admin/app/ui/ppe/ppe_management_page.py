"""Read-only live PPE cards, retaining the last observation while offline."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.ppe_management import (
    ActiveOperationOverallStatus,
    ActiveOperationSnapshot,
    PpeLiveState,
    WorkSessionLiveStatus,
)

_PPE_LABELS = {
    PpeLiveState.COLLECTING: "COLETANDO",
    PpeLiveState.CONFIRMED: "CONFIRMADO",
    PpeLiveState.ABSENT: "AUSENTE",
    PpeLiveState.UNSTABLE: "INSTÁVEL",
    PpeLiveState.UNMAPPED: "SEM MAPEAMENTO",
}
_STATUS_LABELS = {
    ActiveOperationOverallStatus.COMPLIANT: "Conforme",
    ActiveOperationOverallStatus.ATTENTION: "Atenção",
    ActiveOperationOverallStatus.NON_COMPLIANT: "Não conforme",
}


def _label(text: str, *, name: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setObjectName(name)
    return label


class PpeManagementPage(QWidget):
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._snapshots: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._latest: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._cards: dict[tuple[int, UUID], QFrame] = {}
        self._rendered: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._timing_labels: dict[tuple[int, UUID], QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)
        layout.addWidget(_label("Gestão de EPIs", name="pagina_titulo"))
        layout.addWidget(_label("Operações ativas e última observação de segurança recebida."))
        self.connection_status = _label("Aguardando canal em tempo real.", name="realtime_status")
        layout.addWidget(self.connection_status)
        summary = QHBoxLayout()
        self.online_count_label = _label("—", name="card_valor")
        self.compliant_count_label = _label("—", name="card_valor")
        self.alert_count_label = _label("—", name="card_valor")
        for title, value in (
            ("Operadores no último snapshot", self.online_count_label),
            ("Conformes", self.compliant_count_label),
            ("Com alerta", self.alert_count_label),
        ):
            panel = QFrame()
            panel.setObjectName("dashboard_card")
            column = QVBoxLayout(panel)
            column.addWidget(_label(title, name="card_titulo"))
            column.addWidget(value)
            summary.addWidget(panel)
        layout.addLayout(summary)
        controls = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar operador, operação ou câmera")
        self.search_input.setAccessibleName("Buscar operações ativas")
        self.status_filter = QComboBox()
        self.status_filter.setAccessibleName("Filtrar conformidade")
        self.status_filter.addItem("Todos os estados", None)
        for status, label in _STATUS_LABELS.items():
            self.status_filter.addItem(label, status.value)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("primary_action")
        refresh.clicked.connect(self.refresh_requested.emit)
        controls.addWidget(self.search_input, 1)
        controls.addWidget(self.status_filter)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        self.feedback = _label("Aguardando snapshot das operações.", name="operations_feedback")
        layout.addWidget(self.feedback)
        self.empty_state = _label("Nenhuma operação ativa.")
        layout.addWidget(self.empty_state)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._cards_layout = QVBoxLayout(container)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        self.search_input.textChanged.connect(self._filter_cards)
        self.status_filter.currentIndexChanged.connect(self._filter_cards)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_timing)
        self._clock.start()

    @property
    def card_count(self) -> int:
        return len(self._cards)

    @property
    def visible_card_count(self) -> int:
        return sum(not card.isHidden() for card in self._cards.values())

    def cards_text(self) -> str:
        return "\n".join(
            label.text() for card in self._cards.values() for label in card.findChildren(QLabel)
        )

    def show_loading(self) -> None:
        self.feedback.setText("Atualizando operações ativas...")

    def show_error(self, message: str) -> None:
        self.feedback.setText(message)

    def show_snapshot(self, snapshots: tuple[ActiveOperationSnapshot, ...]) -> None:
        self._snapshots.clear()
        for item in snapshots:
            key = (item.operator_id, item.work_session_id)
            previous = self._latest.get(key)
            if previous is not None and previous.observed_at >= item.observed_at:
                item = previous
            self._latest[key] = item
            if item.session_status is WorkSessionLiveStatus.ACTIVE:
                self._snapshots[key] = item
        self.feedback.setText("Snapshot atualizado. Aguardando novas observações.")
        self._render_cards()

    def apply_update(self, snapshot: ActiveOperationSnapshot) -> None:
        key = (snapshot.operator_id, snapshot.work_session_id)
        previous = self._latest.get(key)
        if previous == snapshot:
            return
        if previous is not None and (
            snapshot.observed_at < previous.observed_at
            or (
                snapshot.observed_at == previous.observed_at
                and previous.session_status is WorkSessionLiveStatus.ENDED
            )
        ):
            return
        self._latest[key] = snapshot
        if snapshot.session_status is WorkSessionLiveStatus.ENDED:
            self._snapshots.pop(key, None)
        else:
            self._snapshots[key] = snapshot
        self._render_cards((key,))

    def set_connection_status(self, message: str, *, state: str) -> None:
        self.connection_status.setText(message)
        self.connection_status.setProperty("state", state)
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)

    def _remove_card(self, key: tuple[int, UUID]) -> None:
        card = self._cards.pop(key, None)
        if card is not None:
            self._cards_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self._timing_labels.pop(key, None)
        self._rendered.pop(key, None)

    def _render_cards(self, changed_keys: tuple[tuple[int, UUID], ...] | None = None) -> None:
        keys = (
            tuple(dict.fromkeys((*self._cards, *self._snapshots)))
            if changed_keys is None
            else changed_keys
        )
        for key in keys:
            item = self._snapshots.get(key)
            if item is None:
                self._remove_card(key)
                continue
            rendered = self._rendered.get(key)
            if rendered is not None and replace(rendered, observed_at=item.observed_at) == item:
                continue
            self._remove_card(key)
            card = QFrame()
            card.setObjectName("dashboard_card")
            column = QVBoxLayout(card)
            placeholder = _label("Foto não disponível")
            placeholder.setObjectName("alert_muted")
            column.addWidget(placeholder)
            column.addWidget(
                _label(f"●  {item.operator_name} · ID {item.operator_id}", name="painel_titulo")
            )
            column.addWidget(_label(item.operation_name))
            column.addWidget(_label(f"Câmera: {item.camera_name or 'Não informada'}"))
            column.addWidget(_label(f"Início: {item.started_at.astimezone():%d/%m/%Y %H:%M:%S}"))
            timing = _label("")
            column.addWidget(timing)
            self._timing_labels[key] = timing
            for ppe in item.ppe:
                column.addWidget(_label(f"{ppe.name}: {_PPE_LABELS[ppe.state]}"))
            column.addWidget(_label(f"Estado observado: {_STATUS_LABELS[item.overall_status]}"))
            self._cards_layout.addWidget(card)
            self._cards[key] = card
            self._rendered[key] = item
        operators = {item.operator_id for item in self._snapshots.values()}
        with_alert = {
            item.operator_id
            for item in self._snapshots.values()
            if item.overall_status is not ActiveOperationOverallStatus.COMPLIANT
        }
        self.online_count_label.setText(str(len(operators)))
        self.compliant_count_label.setText(str(len(operators - with_alert)))
        self.alert_count_label.setText(str(len(with_alert)))
        self._filter_cards()
        self._update_timing()

    def _filter_cards(self) -> None:
        query = self.search_input.text().strip().casefold()
        selected = self.status_filter.currentData()
        for key, card in self._cards.items():
            item = self._snapshots[key]
            text = (
                f"{item.operator_name} {item.operator_id} {item.operation_name} {item.camera_name}"
            )
            card.setVisible(
                query in text.casefold()
                and (selected is None or item.overall_status.value == selected)
            )
        self.empty_state.setText(
            "Nenhuma operação ativa."
            if not self._cards
            else "Nenhuma operação corresponde aos filtros."
        )
        self.empty_state.setVisible(self.visible_card_count == 0)

    def _update_timing(self) -> None:
        now = datetime.now(UTC)
        for key, label in self._timing_labels.items():
            item = self._snapshots[key]
            elapsed = max(0, int((now - item.started_at).total_seconds()))
            age = max(0, int((now - item.observed_at).total_seconds()))
            label.setText(
                f"Duração: {elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}"
                f" · Última observação há {age}s"
            )
