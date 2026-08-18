"""Operations workspace shown inside the authenticated application shell."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.operation import (
    Operation,
    OperationManual,
    PpeRequirement,
    RiskAreaReference,
)
from app.ui.components import CameraFrameView, CameraRiskZone


class OperationsPageState(StrEnum):
    """Explicit presentation states for the operations data source."""

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    READY = "ready"
    EMPTY = "empty"
    ERROR = "error"


_STATE_CONTENT = {
    OperationsPageState.NOT_LOADED: (
        "—",
        "NÃO CARREGADO",
        "Aguardando fonte de operações",
        "Nenhum dado operacional foi carregado nesta sessão.",
    ),
    OperationsPageState.LOADING: (
        "···",
        "CARREGANDO",
        "Carregando operações",
        "Aguarde enquanto as operações disponíveis são consultadas.",
    ),
    OperationsPageState.EMPTY: (
        "0",
        "LISTA VAZIA",
        "Nenhuma operação disponível",
        "Não há operações liberadas para este operador no momento.",
    ),
    OperationsPageState.ERROR: (
        "!",
        "INDISPONÍVEL",
        "Não foi possível carregar as operações",
        "Tente novamente quando a conexão com o serviço for restabelecida.",
    ),
}


class OperationsPage(QWidget):
    """Two-panel presentation shell for listing and inspecting operations."""

    operation_selected = Signal(int)
    manual_requested = Signal(int)
    risk_area_requested = Signal(int)
    safety_verification_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._state = OperationsPageState.NOT_LOADED
        self._operations: tuple[Operation, ...] = ()
        self._operation_buttons: dict[int, QPushButton] = {}
        self._ppe_requirement_rows: list[QFrame] = []
        self._displayed_required_ppe: tuple[PpeRequirement, ...] = ()
        self._displayed_risk_area: RiskAreaReference | None = None
        self._selected_operation_id: int | None = None
        self.setObjectName("operationsPage")
        self._build_ui()
        self.set_list_state(OperationsPageState.NOT_LOADED)

    @property
    def state(self) -> OperationsPageState:
        """Return the current list presentation state."""

        return self._state

    @property
    def operations(self) -> tuple[Operation, ...]:
        """Return the immutable snapshot currently rendered by the page."""

        return self._operations

    @property
    def selected_operation_id(self) -> int | None:
        """Return the identifier currently presented in the details panel."""

        return self._selected_operation_id

    @property
    def displayed_required_ppe(self) -> tuple[PpeRequirement, ...]:
        """Return the immutable PPE requirement snapshot shown in the details panel."""

        return self._displayed_required_ppe

    @property
    def displayed_risk_area(self) -> RiskAreaReference | None:
        """Return the risk-area reference shown for the selected operation."""

        return self._displayed_risk_area

    def set_list_state(
        self,
        state: OperationsPageState,
        message: str | None = None,
    ) -> None:
        """Present a non-ready data-source state without performing I/O."""

        if state is OperationsPageState.READY:
            raise ValueError("Use set_operations para apresentar o estado READY.")

        icon, badge, title, default_message = _STATE_CONTENT[state]
        self._operations = ()
        self._clear_operation_buttons()
        self._reset_details_panel()
        self._state = state
        self._set_state_properties(state)
        self._state_icon.setText(icon)
        self._list_status.setText(badge)
        self._state_title.setText(title)
        self._state_description.setText(message or default_message)
        self._list_body.setCurrentWidget(self._list_state_view)
        self._source_notice.hide()

    def set_operations(
        self,
        operations: Sequence[Operation],
        source_notice: str | None = None,
    ) -> None:
        """Render operations supplied by a controller, never by the widget itself."""

        received = tuple(operations)
        if not received:
            self.set_list_state(OperationsPageState.EMPTY)
            return

        self._clear_operation_buttons()
        self._reset_details_panel()
        for operation in received:
            button = QPushButton(operation.name)
            button.setObjectName("operationListButton")
            button.setProperty("operation_id", operation.operation_id)
            button.setProperty("selected", False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(f"Selecionar operação {operation.name}")
            button.clicked.connect(self._handle_operation_click)
            self._operation_buttons[operation.operation_id] = button
            self._operations_layout.addWidget(button)
        self._operations_layout.addStretch(1)

        self._operations = received
        self._state = OperationsPageState.READY
        self._set_state_properties(OperationsPageState.READY)
        count = len(received)
        suffix = "DISPONÍVEL" if count == 1 else "DISPONÍVEIS"
        self._list_status.setText(f"{count} {suffix}")
        self._source_notice.setText(source_notice or "")
        self._source_notice.setVisible(bool(source_notice))
        self._list_body.setCurrentWidget(self._operations_scroll)

    def show_operation_details(self, operation: Operation) -> None:
        """Present one operation already contained in the current list snapshot."""

        button = self._operation_buttons.get(operation.operation_id)
        if button is None:
            raise ValueError("A operação selecionada não pertence à lista atual.")

        current_operation = next(
            item for item in self._operations if item.operation_id == operation.operation_id
        )
        for operation_id, item_button in self._operation_buttons.items():
            item_button.setProperty("selected", operation_id == operation.operation_id)
            self._refresh_style(item_button)

        self._selected_operation_id = current_operation.operation_id
        self._details_status.setText("SELECIONADA")
        self._details_status.setProperty("state", "selected")
        self._refresh_style(self._details_status)
        self._details_code.setText(f"CÓDIGO #{current_operation.operation_id}")
        self._details_name.setText(current_operation.name)
        self._details_description.setText(
            current_operation.description or "Descrição não informada para esta operação."
        )
        active_state = "active" if current_operation.active else "inactive"
        self._details_active.setText("ATIVA" if current_operation.active else "INATIVA")
        self._details_active.setProperty("state", active_state)
        self._refresh_style(self._details_active)
        self._set_required_ppe(current_operation.required_ppe)
        self._set_manual(current_operation.manual)
        self._set_risk_area(current_operation.risk_area)
        self._safety_start_button.setEnabled(current_operation.active)
        self._safety_start_button.setText(
            "COMEÇAR TRABALHO" if current_operation.active else "OPERAÇÃO INATIVA"
        )
        self._details_body.setCurrentWidget(self._details_content)

    def show_manual_error(self, message: str) -> None:
        """Present a safe manual-opening failure without exposing local paths."""

        self._manual_status.setText("INDISPONÍVEL")
        self._manual_status.setProperty("state", "error")
        self._refresh_style(self._manual_status)
        self._manual_error.setText(message)
        self._manual_error.show()

    def show_risk_area(self, risk_area: RiskAreaReference) -> None:
        """Render the configured normalized geometry for the selected operation."""

        if (
            self._displayed_risk_area is None
            or risk_area.risk_area_id != self._displayed_risk_area.risk_area_id
            or risk_area.geometry is None
        ):
            raise ValueError("a área de risco não possui geometria visualizável")
        self._risk_area_preview.set_risk_zones(
            (
                CameraRiskZone(
                    risk_area.name,
                    tuple(
                        (point.x, point.y)
                        for point in risk_area.geometry.vertices
                    ),
                ),
            )
        )
        self._risk_area_preview.show()
        if risk_area.geometry_calibrated:
            self._risk_area_notice.setText(
                "Representação normalizada da zona calibrada para a câmera operacional."
            )
        else:
            self._risk_area_notice.setText(
                "Geometria demonstrativa não calibrada. Não possui validade operacional."
            )
        self._risk_area_notice.show()

    def show_risk_area_unavailable(self) -> None:
        """Explain an associated area whose camera geometry is still absent."""

        self._risk_area_preview.clear_risk_zones()
        self._risk_area_preview.hide()
        self._risk_area_notice.setText(
            "A área está associada, mas sua geometria de câmera não foi configurada."
        )
        self._risk_area_notice.show()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(0)

        layout.addWidget(self._label("TRABALHOS", "operationsEyebrow"))
        layout.addSpacing(6)
        layout.addWidget(self._label("Operações", "operationsTitle"))
        layout.addSpacing(7)
        description = self._label(
            "Consulte as operações disponíveis e visualize os requisitos antes de iniciar.",
            "operationsDescription",
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(24)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("operationsSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_details_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([380, 650])
        layout.addWidget(splitter, 1)

    def _build_list_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("operationsListPanel")
        panel.setMinimumWidth(300)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self._label("Operações disponíveis", "operationsPanelTitle"))
        header.addStretch(1)
        self._list_status = self._label("", "operationsListStatus")
        self._list_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._list_status)
        layout.addLayout(header)
        layout.addSpacing(18)

        self._list_body = QStackedWidget()
        self._list_body.setObjectName("operationsListBody")
        self._list_state_view = self._build_list_state_view()
        self._operations_scroll = self._build_operations_scroll()
        self._list_body.addWidget(self._list_state_view)
        self._list_body.addWidget(self._operations_scroll)
        layout.addWidget(self._list_body, 1)
        layout.addSpacing(10)

        self._source_notice = self._label("", "operationsSourceNotice")
        self._source_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_notice.setWordWrap(True)
        layout.addWidget(self._source_notice)
        return panel

    def _build_list_state_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("operationsListStateView")
        view_layout = QVBoxLayout(view)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)

        self._list_state = QFrame()
        self._list_state.setObjectName("operationsListState")
        state_layout = QVBoxLayout(self._list_state)
        state_layout.setContentsMargins(28, 30, 28, 30)
        state_layout.setSpacing(0)

        self._state_icon = self._label("", "operationsStateIcon")
        self._state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_icon.setFixedSize(46, 46)
        state_layout.addWidget(self._state_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        state_layout.addSpacing(16)

        self._state_title = self._label("", "operationsStateTitle")
        self._state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_title.setWordWrap(True)
        state_layout.addWidget(self._state_title)
        state_layout.addSpacing(7)

        self._state_description = self._label("", "operationsStateDescription")
        self._state_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_description.setWordWrap(True)
        state_layout.addWidget(self._state_description)
        view_layout.addWidget(self._list_state)
        view_layout.addStretch(1)
        return view

    def _build_operations_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("operationsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("operationsListContainer")
        self._operations_layout = QVBoxLayout(container)
        self._operations_layout.setContentsMargins(0, 0, 4, 0)
        self._operations_layout.setSpacing(10)
        scroll.setWidget(container)
        return scroll

    def _build_details_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("operationDetailsPanel")
        panel.setMinimumWidth(380)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self._label("Detalhes da operação", "operationsPanelTitle"))
        header.addStretch(1)
        self._details_status = self._label("", "operationDetailsStatus")
        self._details_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._details_status)
        layout.addLayout(header)
        layout.addSpacing(18)

        self._details_body = QStackedWidget()
        self._details_body.setObjectName("operationDetailsBody")
        self._details_empty_state = self._build_details_empty_state()
        self._details_content = self._build_details_content()
        self._details_body.addWidget(self._details_empty_state)
        self._details_body.addWidget(self._details_content)
        layout.addWidget(self._details_body, 1)
        return panel

    def _build_details_empty_state(self) -> QFrame:
        empty_state = QFrame()
        empty_state.setObjectName("operationDetailsEmptyState")
        empty_layout = QVBoxLayout(empty_state)
        empty_layout.setContentsMargins(36, 36, 36, 36)
        empty_layout.setSpacing(0)
        empty_layout.addStretch(1)

        marker = self._label("01", "operationDetailsMarker")
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedSize(52, 52)
        empty_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addSpacing(18)

        title = self._label("Selecione uma operação", "operationDetailsEmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        empty_layout.addSpacing(8)

        description = self._label(
            "O nome e a descrição da operação aparecerão aqui após a seleção.",
            "operationDetailsEmptyDescription",
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        empty_layout.addWidget(description)
        empty_layout.addStretch(1)
        return empty_state

    def _build_details_content(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("operationDetailsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("operationDetailsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(0)

        metadata = QHBoxLayout()
        metadata.setSpacing(10)
        self._details_code = self._label("", "operationDetailsCode")
        metadata.addWidget(self._details_code)
        metadata.addStretch(1)
        self._details_active = self._label("", "operationDetailsActiveBadge")
        self._details_active.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metadata.addWidget(self._details_active)
        layout.addLayout(metadata)
        layout.addSpacing(14)

        self._details_name = self._label("", "operationDetailsName")
        self._details_name.setWordWrap(True)
        layout.addWidget(self._details_name)
        layout.addSpacing(22)

        separator = QFrame()
        separator.setObjectName("operationDetailsSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        layout.addSpacing(22)

        description_card = QFrame()
        description_card.setObjectName("operationDescriptionCard")
        description_layout = QVBoxLayout(description_card)
        description_layout.setContentsMargins(20, 18, 20, 20)
        description_layout.setSpacing(0)
        description_layout.addWidget(
            self._label("DESCRIÇÃO DA OPERAÇÃO", "operationDetailsSectionLabel")
        )
        description_layout.addSpacing(10)
        self._details_description = self._label("", "operationDetailsDescription")
        self._details_description.setWordWrap(True)
        self._details_description.setAlignment(Qt.AlignmentFlag.AlignTop)
        description_layout.addWidget(self._details_description)
        layout.addWidget(description_card)
        layout.addSpacing(16)

        ppe_card = QFrame()
        ppe_card.setObjectName("operationPpeCard")
        ppe_layout = QVBoxLayout(ppe_card)
        ppe_layout.setContentsMargins(20, 18, 20, 20)
        ppe_layout.setSpacing(0)

        ppe_header = QHBoxLayout()
        ppe_header.setSpacing(10)
        ppe_header.addWidget(
            self._label("EPIs OBRIGATÓRIOS", "operationDetailsSectionLabel")
        )
        ppe_header.addStretch(1)
        self._ppe_count = self._label("", "operationPpeCount")
        self._ppe_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ppe_header.addWidget(self._ppe_count)
        ppe_layout.addLayout(ppe_header)
        ppe_layout.addSpacing(12)

        self._ppe_requirements_container = QWidget()
        self._ppe_requirements_container.setObjectName("operationPpeRequirementsContainer")
        self._ppe_requirements_layout = QVBoxLayout(self._ppe_requirements_container)
        self._ppe_requirements_layout.setContentsMargins(0, 0, 0, 0)
        self._ppe_requirements_layout.setSpacing(8)
        ppe_layout.addWidget(self._ppe_requirements_container)

        self._ppe_empty = self._label(
            "Nenhum EPI obrigatório configurado para esta operação.",
            "operationPpeEmptyState",
        )
        self._ppe_empty.setWordWrap(True)
        ppe_layout.addWidget(self._ppe_empty)
        layout.addWidget(ppe_card)
        layout.addSpacing(16)

        manual_card = QFrame()
        manual_card.setObjectName("operationManualCard")
        manual_layout = QVBoxLayout(manual_card)
        manual_layout.setContentsMargins(20, 18, 20, 20)
        manual_layout.setSpacing(0)

        manual_header = QHBoxLayout()
        manual_header.setSpacing(10)
        manual_header.addWidget(
            self._label("MANUAL DA OPERAÇÃO", "operationDetailsSectionLabel")
        )
        manual_header.addStretch(1)
        self._manual_status = self._label("", "operationManualStatus")
        self._manual_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        manual_header.addWidget(self._manual_status)
        manual_layout.addLayout(manual_header)
        manual_layout.addSpacing(10)

        self._manual_title = self._label("", "operationManualTitle")
        self._manual_title.setWordWrap(True)
        manual_layout.addWidget(self._manual_title)
        manual_layout.addSpacing(14)

        self._manual_button = QPushButton("ABRIR MANUAL PDF")
        self._manual_button.setObjectName("operationManualButton")
        self._manual_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manual_button.setAccessibleName("Abrir manual PDF da operação")
        self._manual_button.clicked.connect(self._handle_manual_click)
        manual_layout.addWidget(self._manual_button)

        self._manual_error = self._label("", "operationManualError")
        self._manual_error.setWordWrap(True)
        manual_layout.addWidget(self._manual_error)
        layout.addWidget(manual_card)
        layout.addSpacing(16)

        risk_area_card = QFrame()
        risk_area_card.setObjectName("operationRiskAreaCard")
        risk_area_layout = QVBoxLayout(risk_area_card)
        risk_area_layout.setContentsMargins(20, 18, 20, 20)
        risk_area_layout.setSpacing(0)

        risk_area_header = QHBoxLayout()
        risk_area_header.setSpacing(10)
        risk_area_header.addWidget(
            self._label("ÁREA DE RISCO", "operationDetailsSectionLabel")
        )
        risk_area_header.addStretch(1)
        self._risk_area_status = self._label("", "operationRiskAreaStatus")
        self._risk_area_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        risk_area_header.addWidget(self._risk_area_status)
        risk_area_layout.addLayout(risk_area_header)
        risk_area_layout.addSpacing(10)

        self._risk_area_name = self._label("", "operationRiskAreaName")
        self._risk_area_name.setWordWrap(True)
        risk_area_layout.addWidget(self._risk_area_name)
        risk_area_layout.addSpacing(14)

        self._risk_area_button = QPushButton("VISUALIZAR ÁREA DE RISCO")
        self._risk_area_button.setObjectName("operationRiskAreaButton")
        self._risk_area_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._risk_area_button.setAccessibleName("Visualizar área de risco da operação")
        self._risk_area_button.clicked.connect(self._handle_risk_area_click)
        risk_area_layout.addWidget(self._risk_area_button)

        self._risk_area_preview = CameraFrameView("operationRiskAreaPreview")
        self._risk_area_preview.setMinimumHeight(170)
        self._risk_area_preview.hide()
        risk_area_layout.addWidget(self._risk_area_preview)

        self._risk_area_notice = self._label("", "operationRiskAreaNotice")
        self._risk_area_notice.setWordWrap(True)
        risk_area_layout.addWidget(self._risk_area_notice)
        layout.addWidget(risk_area_card)
        layout.addSpacing(16)

        safety_start_card = QFrame()
        safety_start_card.setObjectName("operationSafetyStartCard")
        safety_start_layout = QVBoxLayout(safety_start_card)
        safety_start_layout.setContentsMargins(20, 18, 20, 20)
        safety_start_layout.setSpacing(0)
        safety_start_layout.addWidget(
            self._label(
                "VERIFICAÇÃO DE SEGURANÇA",
                "operationSafetyStartEyebrow",
            )
        )
        safety_start_layout.addSpacing(7)
        safety_start_layout.addWidget(
            self._label("Preparar verificação", "operationSafetyStartTitle")
        )
        safety_start_layout.addSpacing(6)
        safety_description = self._label(
            "Começar trabalho abre somente a verificação de segurança. "
            "A operação não será iniciada neste momento.",
            "operationSafetyStartDescription",
        )
        safety_description.setWordWrap(True)
        safety_start_layout.addWidget(safety_description)
        safety_start_layout.addSpacing(15)

        self._safety_start_button = QPushButton("COMEÇAR TRABALHO")
        self._safety_start_button.setObjectName("operationSafetyStartButton")
        self._safety_start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._safety_start_button.setAccessibleName(
            "Abrir a preparação da verificação de segurança"
        )
        self._safety_start_button.clicked.connect(
            self._handle_safety_verification_click
        )
        safety_start_layout.addWidget(self._safety_start_button)
        layout.addWidget(safety_start_card)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _set_state_properties(self, state: OperationsPageState) -> None:
        self._list_state.setProperty("state", state.value)
        self._list_status.setProperty("state", state.value)
        self._refresh_style(self._list_state)
        self._refresh_style(self._list_status)

    def _clear_operation_buttons(self) -> None:
        while self._operations_layout.count():
            item = self._operations_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._operation_buttons.clear()

    def _reset_details_panel(self) -> None:
        self._selected_operation_id = None
        for button in self._operation_buttons.values():
            button.setProperty("selected", False)
            self._refresh_style(button)
        self._details_status.setText("AGUARDANDO SELEÇÃO")
        self._details_status.setProperty("state", "waiting")
        self._refresh_style(self._details_status)
        self._details_code.clear()
        self._details_name.clear()
        self._details_description.clear()
        self._details_active.clear()
        self._details_active.setProperty("state", "inactive")
        self._clear_required_ppe_rows()
        self._ppe_count.clear()
        self._ppe_empty.show()
        self._set_manual(None)
        self._set_risk_area(None)
        self._safety_start_button.setText("COMEÇAR TRABALHO")
        self._safety_start_button.setEnabled(False)
        self._details_body.setCurrentWidget(self._details_empty_state)

    def _set_required_ppe(self, requirements: Sequence[PpeRequirement]) -> None:
        self._clear_required_ppe_rows()
        received = tuple(requirements)
        self._displayed_required_ppe = received
        count = len(received)
        count_label = "1 OBRIGATÓRIO" if count == 1 else f"{count} OBRIGATÓRIOS"
        self._ppe_count.setText(count_label)
        self._ppe_empty.setVisible(not received)

        for index, requirement in enumerate(received, start=1):
            row = QFrame()
            row.setObjectName("operationPpeRequirementRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(11)

            marker = self._label(f"{index:02d}", "operationPpeRequirementMarker")
            marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
            marker.setFixedSize(30, 30)
            row_layout.addWidget(marker)

            name = self._label(requirement.name, "operationPpeRequirementName")
            name.setWordWrap(True)
            row_layout.addWidget(name, 1)

            required = self._label("OBRIGATÓRIO", "operationPpeRequiredBadge")
            required.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(required)
            self._ppe_requirements_layout.addWidget(row)
            self._ppe_requirement_rows.append(row)

    def _clear_required_ppe_rows(self) -> None:
        while self._ppe_requirements_layout.count():
            item = self._ppe_requirements_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._ppe_requirement_rows.clear()
        self._displayed_required_ppe = ()

    def _set_manual(self, manual: OperationManual | None) -> None:
        self._manual_error.clear()
        self._manual_error.hide()
        if manual is None:
            self._manual_status.setText("NÃO CONFIGURADO")
            self._manual_status.setProperty("state", "missing")
            self._manual_title.setText(
                "Nenhum manual PDF foi associado a esta operação."
            )
            self._manual_button.setText("MANUAL NÃO CONFIGURADO")
            self._manual_button.setEnabled(False)
        else:
            self._manual_status.setText("CONFIGURADO")
            self._manual_status.setProperty("state", "configured")
            self._manual_title.setText(manual.title)
            self._manual_button.setText("ABRIR MANUAL PDF")
            self._manual_button.setEnabled(True)
        self._refresh_style(self._manual_status)

    def _set_risk_area(self, risk_area: RiskAreaReference | None) -> None:
        self._displayed_risk_area = risk_area
        self._risk_area_preview.clear_risk_zones()
        self._risk_area_preview.hide()
        self._risk_area_notice.clear()
        self._risk_area_notice.hide()
        if risk_area is None:
            self._risk_area_status.setText("NÃO CONFIGURADA")
            self._risk_area_status.setProperty("state", "missing")
            self._risk_area_name.setText(
                "Nenhuma área de risco foi associada a esta operação."
            )
            self._risk_area_button.setText("ÁREA DE RISCO NÃO CONFIGURADA")
            self._risk_area_button.setEnabled(False)
        elif risk_area.geometry is None:
            self._risk_area_status.setText("SEM GEOMETRIA")
            self._risk_area_status.setProperty("state", "missing")
            self._risk_area_name.setText(risk_area.name)
            self._risk_area_button.setText("GEOMETRIA NÃO CONFIGURADA")
            self._risk_area_button.setEnabled(False)
            self._risk_area_notice.setText(
                "A associação existe, mas ainda não há um polígono para esta câmera."
            )
            self._risk_area_notice.show()
        elif not risk_area.geometry_calibrated:
            self._risk_area_status.setText("DEMONSTRAÇÃO")
            self._risk_area_status.setProperty("state", "demonstration")
            self._risk_area_name.setText(risk_area.name)
            self._risk_area_button.setText("VISUALIZAR GEOMETRIA DEMONSTRATIVA")
            self._risk_area_button.setEnabled(True)
        else:
            self._risk_area_status.setText("DELIMITADA")
            self._risk_area_status.setProperty("state", "associated")
            self._risk_area_name.setText(risk_area.name)
            self._risk_area_button.setText("VISUALIZAR ÁREA DE RISCO")
            self._risk_area_button.setEnabled(True)
        self._refresh_style(self._risk_area_status)

    @Slot()
    def _handle_manual_click(self) -> None:
        operation_id = self._selected_operation_id
        if operation_id is not None and self._manual_button.isEnabled():
            self.manual_requested.emit(operation_id)

    @Slot()
    def _handle_risk_area_click(self) -> None:
        operation_id = self._selected_operation_id
        if operation_id is not None and self._risk_area_button.isEnabled():
            self.risk_area_requested.emit(operation_id)

    @Slot()
    def _handle_safety_verification_click(self) -> None:
        operation_id = self._selected_operation_id
        if operation_id is not None and self._safety_start_button.isEnabled():
            self.safety_verification_requested.emit(operation_id)

    @Slot()
    def _handle_operation_click(self) -> None:
        button = self.sender()
        if not isinstance(button, QPushButton):
            return
        operation_id = button.property("operation_id")
        if type(operation_id) is int:
            self.operation_selected.emit(operation_id)

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
