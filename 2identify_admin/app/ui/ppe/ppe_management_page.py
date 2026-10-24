"""Read-only live PPE cards, retaining the last observation while offline."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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
from app.ui.safety_widgets import PpeChip, StateChip, state_pixmap

_PPE_STATES = {
    PpeLiveState.COLLECTING: ("Verificando", "inc"),
    PpeLiveState.CONFIRMED: ("Confirmado", "safe"),
    PpeLiveState.ABSENT: ("Ausente", "crit"),
    PpeLiveState.UNSTABLE: ("Instável", "inc"),
    PpeLiveState.UNMAPPED: ("Sem mapeamento", "inc"),
}
_STATUS = {
    ActiveOperationOverallStatus.NON_COMPLIANT: ("Não conforme", "crit"),
    ActiveOperationOverallStatus.ATTENTION: ("Atenção", "warn"),
    ActiveOperationOverallStatus.COMPLIANT: ("Conforme", "safe"),
}
_STATUS_ORDER = {
    ActiveOperationOverallStatus.NON_COMPLIANT: 0,
    ActiveOperationOverallStatus.ATTENTION: 1,
    ActiveOperationOverallStatus.COMPLIANT: 2,
}
_FILTERS = (
    ("todos", "Em operação", None),
    (ActiveOperationOverallStatus.NON_COMPLIANT.value, "Não conformes", "crit"),
    (ActiveOperationOverallStatus.ATTENTION.value, "Em atenção", "warn"),
    (ActiveOperationOverallStatus.COMPLIANT.value, "Conformes", "safe"),
)
# Idade a partir da qual a última observação recebida é destacada como antiga.
_STALE_OBSERVATION_SECONDS = 60
_CARD_MIN_WIDTH = 380


def _label(text: str, *, name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setObjectName(name)
    return label


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


class _FilterChip(QFrame):
    """Checkable pill: coloured dot, name and the live count."""

    clicked = Signal()

    def __init__(self, text: str, tone: str | None) -> None:
        super().__init__()
        self.setObjectName("ppe_filter")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)
        if tone is not None:
            dot = QLabel()
            dot.setObjectName("ppe_filter_dot")
            dot.setProperty("tone", tone)
            dot.setFixedSize(8, 8)
            layout.addWidget(dot)
        layout.addWidget(_label(text, name="ppe_filter_text", wrap=False))
        self.count_label = _label("—", name="ppe_filter_count", wrap=False)
        layout.addWidget(self.count_label)
        self.setChecked(False)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        self.setProperty("checked", "true" if checked else "false")
        for widget in (self, *self.findChildren(QLabel)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def isChecked(self) -> bool:  # noqa: N802 - Qt naming
        return self.property("checked") == "true"

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class PpeManagementPage(QWidget):
    refresh_requested = Signal()
    active_operations_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ppe_page")
        self._snapshots: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._latest: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._cards: dict[tuple[int, UUID], QFrame] = {}
        self._rendered: dict[tuple[int, UUID], ActiveOperationSnapshot] = {}
        self._timing_labels: dict[tuple[int, UUID], tuple[QLabel, QLabel]] = {}
        self._filter = "todos"
        self._columns = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        # O cabeçalho da janela já mostra o canal em tempo real.
        self.connection_status = _label("Aguardando canal em tempo real.", name="realtime_status")
        self.connection_status.setParent(self)
        self.connection_status.hide()

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.filter_chips: dict[str, _FilterChip] = {}
        for key, text, tone in _FILTERS:
            chip = _FilterChip(text, tone)
            chip.setChecked(key == "todos")
            chip.clicked.connect(lambda value=key: self._set_filter(value))
            controls.addWidget(chip)
            self.filter_chips[key] = chip
        self.online_count_label = self.filter_chips["todos"].count_label
        self.non_compliant_count_label = self.filter_chips[
            ActiveOperationOverallStatus.NON_COMPLIANT.value
        ].count_label
        self.attention_count_label = self.filter_chips[
            ActiveOperationOverallStatus.ATTENTION.value
        ].count_label
        self.compliant_count_label = self.filter_chips[
            ActiveOperationOverallStatus.COMPLIANT.value
        ].count_label
        self.search_input = QLineEdit()
        self.search_input.setObjectName("ppe_search")
        self.search_input.setPlaceholderText("Buscar funcionário, operação ou câmera")
        self.search_input.setAccessibleName("Buscar operações ativas")
        controls.addWidget(self.search_input, 1)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("ppe_refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh_requested.emit)
        controls.addWidget(refresh)
        layout.addLayout(controls)

        self.feedback = _label("Aguardando as operações ativas.", name="operations_feedback")
        layout.addWidget(self.feedback)
        self.empty_state = _label("Nenhuma operação ativa.", name="dashboard_vazio")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_state)
        scroll = QScrollArea()
        scroll.setObjectName("ppe_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("ppe_cards")
        self._cards_layout = QGridLayout(container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(14)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        self._scroll = scroll
        layout.addWidget(scroll, 1)
        self.search_input.textChanged.connect(self._filter_cards)
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
        self._show_feedback("Atualizando operações ativas...")

    def show_error(self, message: str) -> None:
        self._show_feedback(message, "error")

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
        self.feedback.hide()
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

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._place_cards()

    def _show_feedback(self, message: str, state: str = "loading") -> None:
        self.feedback.setText(message)
        self.feedback.setProperty("state", state)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        self.feedback.show()

    def _remove_card(self, key: tuple[int, UUID]) -> None:
        card = self._cards.pop(key, None)
        if card is not None:
            self._cards_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self._timing_labels.pop(key, None)
        self._rendered.pop(key, None)

    def _build_card(self, key: tuple[int, UUID], item: ActiveOperationSnapshot) -> QFrame:
        status, tone = _STATUS[item.overall_status]
        card = QFrame()
        card.setObjectName("ppe_card")
        card.setProperty("tone", tone)
        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        head = QFrame()
        head.setObjectName("ppe_card_head")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(16, 12, 16, 12)
        head_layout.setSpacing(12)
        avatar = _label(_initials(item.operator_name), name="linha_avatar", wrap=False)
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head_layout.addWidget(avatar)
        names = QVBoxLayout()
        names.setSpacing(1)
        names.addWidget(_label(item.operator_name, name="ppe_card_name", wrap=False))
        names.addWidget(
            _label(
                f"{item.operation_name} · {item.camera_name or 'Câmera não informada'}",
                name="linha_texto",
            )
        )
        head_layout.addLayout(names, 1)
        head_layout.addWidget(StateChip(status, tone), 0, Qt.AlignmentFlag.AlignTop)
        column.addWidget(head)

        body = QFrame()
        body.setObjectName("ppe_card_body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 10, 16, 10)
        body_layout.setSpacing(8)
        if not item.ppe:
            body_layout.addWidget(_label("Nenhum EPI exigido nesta operação.", name="linha_texto"))
        for ppe in item.ppe:
            word, ppe_tone = _PPE_STATES[ppe.state]
            row = QHBoxLayout()
            row.setSpacing(10)
            icon = QLabel()
            icon.setPixmap(state_pixmap(ppe_tone, 16))
            row.addWidget(icon)
            row.addWidget(_label(ppe.name, name="ppe_item_name", wrap=False), 1)
            row.addWidget(PpeChip(word, ppe_tone), 0, Qt.AlignmentFlag.AlignVCenter)
            body_layout.addLayout(row)
        body_layout.addStretch()
        column.addWidget(body, 1)

        foot = QFrame()
        foot.setObjectName("ppe_card_foot")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(16, 9, 16, 10)
        foot_layout.setSpacing(18)
        duration = QLabel()
        duration.setObjectName("ppe_card_foot_text")
        duration.setTextFormat(Qt.TextFormat.RichText)
        age = _label("", name="ppe_card_foot_text", wrap=False)
        foot_layout.addWidget(duration)
        foot_layout.addWidget(age)
        foot_layout.addStretch()
        column.addWidget(foot)
        self._timing_labels[key] = (duration, age)
        card.setMinimumWidth(_CARD_MIN_WIDTH - 40)
        return card

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
            self._cards[key] = self._build_card(key, item)
            self._rendered[key] = item
        operators = {item.operator_id for item in self._snapshots.values()}
        by_status = {
            status: {
                item.operator_id
                for item in self._snapshots.values()
                if item.overall_status is status
            }
            for status in ActiveOperationOverallStatus
        }
        self.online_count_label.setText(str(len(operators)))
        self.non_compliant_count_label.setText(
            str(len(by_status[ActiveOperationOverallStatus.NON_COMPLIANT]))
        )
        self.attention_count_label.setText(
            str(len(by_status[ActiveOperationOverallStatus.ATTENTION]))
        )
        with_alert = (
            by_status[ActiveOperationOverallStatus.NON_COMPLIANT]
            | by_status[ActiveOperationOverallStatus.ATTENTION]
        )
        self.compliant_count_label.setText(str(len(operators - with_alert)))
        self._filter_cards()
        self._update_timing()
        self.active_operations_changed.emit(tuple(self._snapshots.values()))

    def _set_filter(self, value: str) -> None:
        self._filter = value
        for key, chip in self.filter_chips.items():
            chip.setChecked(key == value)
        self._filter_cards()

    def _filter_cards(self) -> None:
        query = self.search_input.text().strip().casefold()
        for key, card in self._cards.items():
            item = self._snapshots[key]
            text = (
                f"{item.operator_name} {item.operator_id} {item.operation_name} {item.camera_name}"
            )
            card.setVisible(
                query in text.casefold()
                and (self._filter == "todos" or item.overall_status.value == self._filter)
            )
        self.empty_state.setText(
            "Nenhuma operação ativa.\nAs operações iniciadas no Operator aparecem aqui."
            if not self._cards
            else "Nenhuma operação corresponde aos filtros."
        )
        self.empty_state.setVisible(self.visible_card_count == 0)
        self._place_cards()

    def _place_cards(self) -> None:
        width = self._scroll.viewport().width() if self.isVisible() else 900
        columns = max(1, min(3, width // _CARD_MIN_WIDTH))
        ordered = sorted(
            self._cards,
            key=lambda key: (
                _STATUS_ORDER[self._snapshots[key].overall_status],
                self._snapshots[key].started_at,
            ),
        )
        visible = [key for key in ordered if not self._cards[key].isHidden()]
        self._columns = columns
        for card in self._cards.values():
            self._cards_layout.removeWidget(card)
        position = 0
        for key in ordered:
            card = self._cards[key]
            if key in visible:
                self._cards_layout.addWidget(card, position // columns, position % columns)
                position += 1
        for column in range(3):
            self._cards_layout.setColumnStretch(column, 1 if column < columns else 0)
        rows = (position + columns - 1) // columns
        for row in range(self._cards_layout.rowCount()):
            self._cards_layout.setRowStretch(row, 1 if row == rows else 0)
        self._cards_layout.setRowStretch(rows, 1)

    def _update_timing(self) -> None:
        now = datetime.now(UTC)
        for key, (duration, age_label) in self._timing_labels.items():
            item = self._snapshots[key]
            elapsed = max(0, int((now - item.started_at).total_seconds()))
            age = max(0, int((now - item.observed_at).total_seconds()))
            duration.setText(
                "Em operação há <b>"
                f"{elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}</b>"
            )
            age_label.setText(
                f"Última observação há {age} s"
                if age < 60
                else f"Última observação há {age // 60} min"
            )
            stale = "true" if age >= _STALE_OBSERVATION_SECONDS else "false"
            if age_label.property("stale") != stale:
                age_label.setProperty("stale", stale)
                age_label.style().unpolish(age_label)
                age_label.style().polish(age_label)
