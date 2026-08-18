"""Presentation-only safety verification page for a selected operation."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage
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

from app.core.session import OperatorSession
from app.domain.operation import Operation
from app.engine import (
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyStatus,
)
from app.ui.components import CameraFrameOverlay, CameraFrameView, CameraOverlayBox
from app.vision.ppe import PpeDetectionBatch


class SafetyCameraState(StrEnum):
    """Presentation states for the operational camera lifecycle."""

    NOT_INITIALIZED = "not_initialized"
    STARTING = "starting"
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class PpeInferenceState(StrEnum):
    """Presentation states for PPE inference and temporal stabilization."""

    NOT_INITIALIZED = "not_initialized"
    LOADING = "loading"
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class SafetyVerificationPage(QWidget):
    """Present camera and stable PPE evidence without releasing the operation."""

    back_requested = Signal()
    camera_start_requested = Signal()
    camera_stop_requested = Signal()
    operation_start_requested = Signal(int)

    def __init__(self, session: OperatorSession) -> None:
        super().__init__()
        self._session = session
        self._operation: Operation | None = None
        self._ppe_rows: list[QFrame] = []
        self._ppe_state_labels: dict[int, QLabel] = {}
        self._camera_state = SafetyCameraState.NOT_INITIALIZED
        self._inference_state = PpeInferenceState.NOT_INITIALIZED
        self._model_classes: frozenset[str] = frozenset()
        self._detection_overlay_maximum_age_ms = 2_000
        self._camera_active = False
        self.setObjectName("safetyVerificationPage")
        self._build_ui()

    @property
    def operation(self) -> Operation | None:
        """Return the operation currently prepared for verification."""

        return self._operation

    @property
    def camera_state(self) -> SafetyCameraState:
        """Return the current camera presentation state."""

        return self._camera_state

    @property
    def inference_state(self) -> PpeInferenceState:
        """Return the current inference presentation state."""

        return self._inference_state

    def configure_detection_overlay(self, maximum_age_ms: int) -> None:
        """Set how long raw boxes may remain visible without a new result."""

        if maximum_age_ms <= 0:
            raise ValueError("maximum_age_ms deve ser maior que zero")
        self._detection_overlay_maximum_age_ms = maximum_age_ms

    def set_operation(self, operation: Operation) -> None:
        """Prepare a fresh, non-started verification context."""

        self._operation = operation
        self._operation_name.setText(operation.name)
        self._operation_code.setText(f"OPERAÇÃO #{operation.operation_id}")
        self._operator_name.setText(self._session.operator_name)
        self._operator_detail.setText(f"Operador #{self._session.operator_id}")
        self._risk_area_name.setText(
            operation.risk_area.name
            if operation.risk_area is not None
            else "Área de risco não configurada"
        )
        self._render_required_ppe(operation)
        self._reset_camera()
        self._reset_inference()
        self._release_status.setText("AGUARDANDO VERIFICAÇÃO")
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_description.setText(
            "A verificação de segurança ainda não foi executada."
        )
        self._set_release_banner_state("blocked")
        self._set_operation_start_enabled(False)

    def activate(self) -> None:
        """Request camera capture when the page becomes the active route."""

        self._camera_active = True
        self.set_camera_state(
            SafetyCameraState.STARTING,
            "Conectando à câmera configurada para esta estação.",
        )
        self.camera_start_requested.emit()

    def deactivate(self) -> None:
        """Stop capture and discard the last frame when leaving the route."""

        if self._camera_active:
            self.camera_stop_requested.emit()
        self._camera_active = False
        self._reset_camera()
        self._reset_inference()

    @Slot()
    def show_camera_ready(self) -> None:
        """Present a connected camera without claiming PPE analysis is active."""

        if not self._camera_active:
            return
        self.set_camera_state(
            SafetyCameraState.ACTIVE,
            "Câmera conectada. Aguardando o primeiro frame da captura.",
        )

    @Slot(QImage)
    def update_camera_frame(self, frame: QImage) -> None:
        """Render a worker-owned image while keeping PPE states untouched."""

        if not self._camera_active or frame.isNull():
            return
        self._camera_preview.set_frame(frame)
        self._camera_stack.setCurrentWidget(self._camera_preview)
        if self._camera_state is not SafetyCameraState.ACTIVE:
            self.show_camera_ready()

    @Slot(str, bool)
    def show_camera_failure(self, message: str, unavailable: bool) -> None:
        """Present recoverable capture failure and keep operation blocked."""

        if not self._camera_active:
            return
        state = SafetyCameraState.UNAVAILABLE if unavailable else SafetyCameraState.ERROR
        self.set_camera_state(state, message)
        self._set_operation_start_enabled(False)
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_status.setText("VERIFICAÇÃO BLOQUEADA")
        self._release_description.setText(
            f"{message} A operação permanece bloqueada."
        )
        self._set_release_banner_state("blocked")

    def set_camera_state(self, state: SafetyCameraState, message: str) -> None:
        """Update camera labels from an explicit lifecycle state."""

        labels = {
            SafetyCameraState.NOT_INITIALIZED: (
                "NÃO INICIALIZADA",
                "Captura ainda não iniciada",
            ),
            SafetyCameraState.STARTING: ("INICIALIZANDO", "Inicializando câmera"),
            SafetyCameraState.ACTIVE: ("ATIVA", "Câmera conectada"),
            SafetyCameraState.UNAVAILABLE: ("INDISPONÍVEL", "Câmera indisponível"),
            SafetyCameraState.ERROR: ("FALHA", "Falha na captura"),
        }
        status, title = labels[state]
        self._camera_state = state
        self._camera_status.setText(status)
        self._camera_status.setProperty("state", state.value)
        self._refresh_style(self._camera_status)
        self._camera_placeholder_title.setText(title)
        self._camera_placeholder_description.setText(message)
        failed = state in {SafetyCameraState.UNAVAILABLE, SafetyCameraState.ERROR}
        self._camera_retry_button.setVisible(failed)
        if state is not SafetyCameraState.ACTIVE:
            self._camera_preview.clear_frame()
            self._camera_stack.setCurrentWidget(self._camera_placeholder)

    @Slot()
    def show_inference_loading(self) -> None:
        """Reset stale observations while the local model is loaded."""

        if not self._camera_active:
            return
        self._set_inference_state(PpeInferenceState.LOADING, "CARREGANDO MODELO")
        self._set_all_ppe_waiting()
        self._camera_preview.clear_overlay()
        self._detection_overlay_status.setText("PREPARANDO CAIXAS DA IA")
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_status.setText("AGUARDANDO VERIFICAÇÃO")
        self._release_description.setText(
            "O modelo está sendo preparado. A operação permanece bloqueada."
        )
        self._set_release_banner_state("pending")
        self._set_operation_start_enabled(False)

    @Slot(object)
    def show_inference_ready(self, value: object) -> None:
        """Present model availability while the temporal window is empty."""

        if not self._camera_active or not isinstance(value, tuple):
            return
        if not all(isinstance(item, str) for item in value):
            self.show_inference_failure(
                "O modelo de EPIs retornou classes inválidas.",
                True,
            )
            return
        self._model_classes = frozenset(item.casefold() for item in value)
        self._set_inference_state(
            PpeInferenceState.ACTIVE,
            "IA ATIVA · COLETANDO AMOSTRAS",
        )
        self._set_all_ppe_waiting(mark_unmapped=True)
        self._detection_overlay_status.setText(
            "CAIXAS AZUIS = DETECÇÕES DO FRAME · NÃO INDICAM CONFORMIDADE"
        )
        self._release_status.setText("AGUARDANDO ESTABILIDADE")
        self._release_description.setText(
            "A IA está coletando observações para formar uma janela temporal segura."
        )
        self._set_release_banner_state("pending")
        self._set_operation_start_enabled(False)

    @Slot(object)
    def update_ppe_detection_overlay(self, value: object) -> None:
        """Render every raw model box without treating it as stable evidence."""

        if not self._camera_active or not isinstance(value, PpeDetectionBatch):
            return
        overlay = CameraFrameOverlay(
            boxes=tuple(
                CameraOverlayBox(
                    label=detection.class_name,
                    confidence=detection.confidence,
                    x1=detection.box.x1,
                    y1=detection.box.y1,
                    x2=detection.box.x2,
                    y2=detection.box.y2,
                )
                for detection in value.detections
            ),
            source_width=value.frame_width,
            source_height=value.frame_height,
        )
        self._camera_preview.set_overlay(
            overlay,
            maximum_age_ms=self._detection_overlay_maximum_age_ms,
        )
        count = len(overlay.boxes)
        suffix = "CAIXA" if count == 1 else "CAIXAS"
        self._detection_overlay_status.setText(
            f"FRAME ATUAL · {count} {suffix} DA IA · OBSERVAÇÃO BRUTA"
        )

    @Slot(object)
    def update_ppe_safety(self, value: object) -> None:
        """Present one operation-bound assessment and update its release gate."""

        operation = self._operation
        if (
            not self._camera_active
            or not isinstance(value, PpeSafetyAssessment)
            or operation is None
            or value.operation_id != operation.operation_id
        ):
            return

        for requirement in operation.required_ppe:
            assessment = value.assessment_for(requirement.ppe_id)
            if assessment is None:
                self._set_ppe_state(requirement.ppe_id, "SEM EVIDÊNCIA", "unmapped")
                continue
            labels = {
                PpeRequirementSafetyState.COLLECTING: ("COLETANDO", "collecting"),
                PpeRequirementSafetyState.CONFIRMED: ("CONFIRMADO", "confirmed"),
                PpeRequirementSafetyState.ABSENT: ("AUSENTE", "absent"),
                PpeRequirementSafetyState.UNSTABLE: ("INSTÁVEL", "unstable"),
                PpeRequirementSafetyState.UNMAPPED: ("SEM MAPEAMENTO", "unmapped"),
            }
            text, state = labels[assessment.state]
            self._set_ppe_state(requirement.ppe_id, text, state)

        suffix = "AMOSTRA" if value.sample_count == 1 else "AMOSTRAS"
        self._set_inference_state(
            PpeInferenceState.ACTIVE,
            f"IA ATIVA · {value.sample_count}/{value.window_size} {suffix}",
        )
        if value.status is PpeSafetyStatus.COMPLIANT:
            self._release_title.setText("VERIFICAÇÃO CONCLUÍDA")
            self._release_status.setText("EPIs CONFORMES")
            self._release_description.setText(
                "Todos os EPIs obrigatórios foram confirmados. "
                "A operação está apta para iniciar."
            )
            self._set_release_banner_state("compliant")
            self._set_operation_start_enabled(True)
        elif value.status is PpeSafetyStatus.BLOCKED:
            self._show_blocked_assessment(value)
        else:
            self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
            self._release_status.setText("AGUARDANDO ESTABILIDADE")
            self._release_description.setText(
                "A IA ainda está consolidando observações da janela temporal."
            )
            self._set_release_banner_state("pending")
            self._set_operation_start_enabled(False)

    @Slot(str, bool)
    def show_inference_failure(self, message: str, unavailable: bool) -> None:
        """Fail closed when the model cannot load or process a frame."""

        if not self._camera_active:
            return
        state = (
            PpeInferenceState.UNAVAILABLE if unavailable else PpeInferenceState.ERROR
        )
        self._set_inference_state(state, "IA INDISPONÍVEL")
        self._set_all_ppe_waiting()
        self._camera_preview.clear_overlay()
        self._detection_overlay_status.setText("CAIXAS DA IA INDISPONÍVEIS")
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_status.setText("VERIFICAÇÃO BLOQUEADA")
        self._release_description.setText(
            f"{message} A operação permanece bloqueada."
        )
        self._set_release_banner_state("blocked")
        self._set_operation_start_enabled(False)

    @Slot()
    def show_operation_start_rejected(self) -> None:
        """Revoke a stale or forged start intent at the presentation boundary."""

        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_status.setText("VERIFICAÇÃO EXPIRADA")
        self._release_description.setText(
            "As condições de segurança precisam ser confirmadas novamente."
        )
        self._set_release_banner_state("blocked")
        self._set_operation_start_enabled(False)

    @Slot()
    def show_operation_start_authorized(self) -> None:
        """Present the accepted one-shot intent before WorkSession creation."""

        self._release_title.setText("VERIFICAÇÃO CONCLUÍDA")
        self._release_status.setText("INÍCIO AUTORIZADO")
        self._release_description.setText("Preparando a sessão da operação.")
        self._set_release_banner_state("compliant")
        self._set_operation_start_enabled(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 22, 32, 26)
        layout.setSpacing(0)

        back_button = QPushButton("VOLTAR ÀS OPERAÇÕES")
        back_button.setObjectName("safetyBackButton")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.setAccessibleName("Voltar para a lista de operações")
        back_button.clicked.connect(self.back_requested)
        layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(17)

        layout.addWidget(self._label("SEGURANÇA OPERACIONAL", "safetyEyebrow"))
        layout.addSpacing(5)
        layout.addWidget(self._label("Verificação de segurança", "safetyTitle"))
        layout.addSpacing(6)
        description = self._label(
            "Confirme o contexto antes da futura captura e análise dos EPIs.",
            "safetyDescription",
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(20)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("safetySplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_camera_panel())
        splitter.addWidget(self._build_context_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([650, 430])
        layout.addWidget(splitter, 1)
        layout.addSpacing(16)
        layout.addWidget(self._build_release_banner())

    def _build_camera_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("safetyCameraPanel")
        panel.setMinimumWidth(340)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._label("Câmera de verificação", "safetyPanelTitle"))
        header.addStretch(1)
        self._camera_status = self._label("NÃO INICIALIZADA", "safetyCameraStatus")
        self._camera_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._camera_status)
        self._camera_retry_button = QPushButton("TENTAR NOVAMENTE")
        self._camera_retry_button.setObjectName("safetyCameraRetryButton")
        self._camera_retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_retry_button.setAccessibleName(
            "Tentar inicializar novamente a câmera de verificação"
        )
        self._camera_retry_button.clicked.connect(self._request_camera_retry)
        self._camera_retry_button.hide()
        header.addWidget(self._camera_retry_button)
        layout.addLayout(header)
        layout.addSpacing(8)

        self._detection_overlay_status = self._label(
            "CAIXAS DA IA NÃO INICIALIZADAS",
            "safetyDetectionOverlayStatus",
        )
        self._detection_overlay_status.setWordWrap(True)
        layout.addWidget(self._detection_overlay_status)
        layout.addSpacing(8)

        self._camera_stack = QStackedWidget()
        self._camera_stack.setObjectName("safetyCameraStack")

        self._camera_placeholder = QFrame()
        self._camera_placeholder.setObjectName("safetyCameraPlaceholder")
        placeholder_layout = QVBoxLayout(self._camera_placeholder)
        placeholder_layout.setContentsMargins(34, 34, 34, 34)
        placeholder_layout.setSpacing(0)
        placeholder_layout.addStretch(1)

        marker = self._label("CAM", "safetyCameraMarker")
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedSize(64, 52)
        placeholder_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignHCenter)
        placeholder_layout.addSpacing(17)

        self._camera_placeholder_title = self._label(
            "Captura ainda não iniciada",
            "safetyCameraPlaceholderTitle",
        )
        self._camera_placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(self._camera_placeholder_title)
        placeholder_layout.addSpacing(7)

        self._camera_placeholder_description = self._label(
            "A câmera será ativada ao abrir a verificação de segurança.",
            "safetyCameraPlaceholderDescription",
        )
        self._camera_placeholder_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._camera_placeholder_description.setWordWrap(True)
        placeholder_layout.addWidget(self._camera_placeholder_description)
        placeholder_layout.addStretch(1)

        self._camera_preview = CameraFrameView("safetyCameraPreview")
        self._camera_stack.addWidget(self._camera_placeholder)
        self._camera_stack.addWidget(self._camera_preview)
        layout.addWidget(self._camera_stack, 1)
        return panel

    def _build_context_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("safetyContextPanel")
        panel.setMinimumWidth(300)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(20, 18, 14, 18)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(self._label("Contexto da verificação", "safetyPanelTitle"))
        outer_layout.addSpacing(14)

        scroll = QScrollArea()
        scroll.setObjectName("safetyContextScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("safetyContextContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(0)

        layout.addWidget(self._label("OPERAÇÃO", "safetySectionLabel"))
        layout.addSpacing(4)
        self._operation_name = self._label(
            "Nenhuma operação selecionada",
            "safetyOperationName",
        )
        self._operation_name.setWordWrap(True)
        layout.addWidget(self._operation_name)
        self._operation_code = self._label("", "safetyMetadata")
        layout.addWidget(self._operation_code)
        layout.addSpacing(17)

        layout.addWidget(self._label("OPERADOR", "safetySectionLabel"))
        layout.addSpacing(4)
        self._operator_name = self._label(self._session.operator_name, "safetyOperatorName")
        self._operator_name.setWordWrap(True)
        layout.addWidget(self._operator_name)
        self._operator_detail = self._label(
            f"Operador #{self._session.operator_id}",
            "safetyMetadata",
        )
        layout.addWidget(self._operator_detail)
        layout.addSpacing(17)

        layout.addWidget(self._label("ÁREA DE RISCO", "safetySectionLabel"))
        layout.addSpacing(4)
        self._risk_area_name = self._label("Não configurada", "safetyRiskAreaName")
        self._risk_area_name.setWordWrap(True)
        layout.addWidget(self._risk_area_name)
        layout.addSpacing(18)

        ppe_header = QHBoxLayout()
        ppe_header.setSpacing(8)
        ppe_header.addWidget(self._label("EPIs OBRIGATÓRIOS", "safetySectionLabel"))
        ppe_header.addStretch(1)
        self._ppe_count = self._label("0 ITENS", "safetyPpeCount")
        self._ppe_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ppe_header.addWidget(self._ppe_count)
        layout.addLayout(ppe_header)
        layout.addSpacing(7)

        self._inference_status = self._label(
            "IA NÃO INICIALIZADA",
            "safetyInferenceStatus",
        )
        self._inference_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._inference_status, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(9)

        self._ppe_container = QWidget()
        self._ppe_container.setObjectName("safetyPpeContainer")
        self._ppe_layout = QVBoxLayout(self._ppe_container)
        self._ppe_layout.setContentsMargins(0, 0, 0, 0)
        self._ppe_layout.setSpacing(7)
        layout.addWidget(self._ppe_container)

        self._ppe_empty = self._label(
            "Nenhum EPI obrigatório configurado.",
            "safetyPpeEmptyState",
        )
        self._ppe_empty.setWordWrap(True)
        layout.addWidget(self._ppe_empty)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)
        return panel

    def _build_release_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("safetyReleaseBanner")
        banner.setProperty("state", "blocked")
        self._release_banner = banner
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(16)

        self._release_marker = self._label("!", "safetyReleaseMarker")
        self._release_marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._release_marker.setFixedSize(38, 38)
        layout.addWidget(self._release_marker)

        text = QVBoxLayout()
        text.setSpacing(2)
        self._release_title = self._label("OPERAÇÃO NÃO LIBERADA", "safetyReleaseTitle")
        text.addWidget(self._release_title)
        self._release_description = self._label(
            "A verificação de segurança ainda não foi executada.",
            "safetyReleaseDescription",
        )
        self._release_description.setWordWrap(True)
        text.addWidget(self._release_description)
        layout.addLayout(text, 1)

        self._release_status = self._label(
            "AGUARDANDO VERIFICAÇÃO",
            "safetyReleaseStatus",
        )
        self._release_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._release_status)

        self._start_operation_button = QPushButton("INICIAR OPERAÇÃO")
        self._start_operation_button.setObjectName("safetyStartOperationButton")
        self._start_operation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_operation_button.setAccessibleName(
            "Iniciar a operação após a verificação de segurança"
        )
        self._start_operation_button.setEnabled(False)
        self._start_operation_button.clicked.connect(self._request_operation_start)
        layout.addWidget(self._start_operation_button)
        return banner

    def _show_blocked_assessment(self, assessment: PpeSafetyAssessment) -> None:
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        if not assessment.operation_active:
            self._release_status.setText("OPERAÇÃO INATIVA")
            description = "A operação selecionada não está ativa."
        elif not assessment.requirements:
            self._release_status.setText("CONFIGURAÇÃO INVÁLIDA")
            description = "Nenhum EPI obrigatório foi configurado para esta operação."
        elif assessment.unmapped_requirement_names:
            self._release_status.setText("SEM MAPEAMENTO")
            names = ", ".join(assessment.unmapped_requirement_names)
            description = f"A IA não possui mapeamento verificável para: {names}."
        elif assessment.absent_requirement_names:
            names = ", ".join(assessment.absent_requirement_names)
            count = len(assessment.absent_requirement_names)
            self._release_status.setText(
                "EPI AUSENTE" if count == 1 else "EPIs AUSENTES"
            )
            description = f"EPI obrigatório ausente: {names}."
        else:
            self._release_status.setText("VERIFICAÇÃO BLOQUEADA")
            description = "Os requisitos de segurança ainda não foram atendidos."
        self._release_description.setText(description)
        self._set_release_banner_state("blocked")
        self._set_operation_start_enabled(False)

    def _render_required_ppe(self, operation: Operation) -> None:
        self._clear_ppe_rows()
        requirements = operation.required_ppe
        count = len(requirements)
        self._ppe_count.setText(f"{count} ITEM" if count == 1 else f"{count} ITENS")
        self._ppe_empty.setVisible(not requirements)

        for requirement in requirements:
            row = QFrame()
            row.setObjectName("safetyPpeRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(11, 9, 11, 9)
            row_layout.setSpacing(10)

            name = self._label(requirement.name, "safetyPpeName")
            name.setWordWrap(True)
            row_layout.addWidget(name, 1)
            state = self._label("AGUARDANDO", "safetyPpeState")
            state.setProperty("state", "waiting")
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(state)
            self._ppe_layout.addWidget(row)
            self._ppe_rows.append(row)
            self._ppe_state_labels[requirement.ppe_id] = state

    def _clear_ppe_rows(self) -> None:
        while self._ppe_layout.count():
            item = self._ppe_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._ppe_rows.clear()
        self._ppe_state_labels.clear()

    def _reset_camera(self) -> None:
        self.set_camera_state(
            SafetyCameraState.NOT_INITIALIZED,
            "A câmera será ativada ao abrir a verificação de segurança.",
        )

    def _reset_inference(self) -> None:
        self._model_classes = frozenset()
        self._set_inference_state(
            PpeInferenceState.NOT_INITIALIZED,
            "IA NÃO INICIALIZADA",
        )
        self._set_all_ppe_waiting()
        self._camera_preview.clear_overlay()
        self._detection_overlay_status.setText("CAIXAS DA IA NÃO INICIALIZADAS")
        self._set_operation_start_enabled(False)

    def _set_inference_state(
        self,
        state: PpeInferenceState,
        text: str,
    ) -> None:
        self._inference_state = state
        self._inference_status.setText(text)
        self._inference_status.setProperty("state", state.value)
        self._refresh_style(self._inference_status)

    def _set_all_ppe_waiting(self, *, mark_unmapped: bool = False) -> None:
        operation = self._operation
        if operation is None:
            return
        for requirement in operation.required_ppe:
            if mark_unmapped and (
                requirement.detection_class is None
                or requirement.detection_class not in self._model_classes
            ):
                self._set_ppe_state(requirement.ppe_id, "SEM MAPEAMENTO", "unmapped")
            else:
                self._set_ppe_state(requirement.ppe_id, "AGUARDANDO", "waiting")

    def _set_ppe_state(self, ppe_id: int, text: str, state: str) -> None:
        label = self._ppe_state_labels.get(ppe_id)
        if label is None:
            return
        label.setText(text)
        label.setProperty("state", state)
        self._refresh_style(label)

    def _set_release_banner_state(self, state: str) -> None:
        self._release_banner.setProperty("state", state)
        self._release_marker.setText("✓" if state == "compliant" else "!")
        self._refresh_style(self._release_banner)
        self._refresh_style(self._release_marker)
        self._refresh_style(self._release_title)
        self._refresh_style(self._release_description)
        self._refresh_style(self._release_status)

    def _set_operation_start_enabled(self, enabled: bool) -> None:
        self._start_operation_button.setEnabled(enabled)
        self._start_operation_button.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ForbiddenCursor
        )

    @Slot()
    def _request_operation_start(self) -> None:
        operation = self._operation
        if operation is None or not self._start_operation_button.isEnabled():
            return
        self.operation_start_requested.emit(operation.operation_id)

    @Slot()
    def _request_camera_retry(self) -> None:
        if not self._camera_active:
            return
        self.set_camera_state(
            SafetyCameraState.STARTING,
            "Reconectando à câmera configurada para esta estação.",
        )
        self.camera_start_requested.emit()

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
