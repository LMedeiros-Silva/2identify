"""Presentation-only safety verification page for a selected operation."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QCheckBox,
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
from app.domain.camera_source import CameraSource
from app.domain.operation import Operation
from app.engine import (
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyStatus,
)
from app.ui.components import CameraFrameOverlay, CameraFrameView, CameraOverlayBox
from app.ui.safety_widgets import state_pixmap
from app.ui.theme import TOKENS
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


_STATE_TONE = {
    "confirmed": "safe",
    "absent": "crit",
    "unstable": "inc",
    "collecting": "inc",
    "waiting": "neutral",
    "unmapped": "neutral",
}
_STATE_DETAIL = {
    PpeRequirementSafetyState.COLLECTING: "Coletando quadros da câmera.",
    PpeRequirementSafetyState.CONFIRMED: "Confirmado em vários quadros seguidos.",
    PpeRequirementSafetyState.ABSENT: "Não aparece nos quadros recentes.",
    PpeRequirementSafetyState.UNSTABLE: "Aparece só em parte dos quadros.",
    PpeRequirementSafetyState.UNMAPPED: "A IA desta estação não reconhece este item.",
}
# Release banner state -> word, tone and shape colour for the state band.
_BAND = {
    "compliant": ("LIBERADA", "safe"),
    "pending": ("VERIFICANDO", "inc"),
    "blocked": ("BLOQUEADA", "crit"),
}


class SafetyVerificationPage(QWidget):
    """Present camera and stable PPE evidence without releasing the operation."""

    back_requested = Signal()
    camera_start_requested = Signal()
    camera_stop_requested = Signal()
    operation_start_requested = Signal(int)
    catalog_requested = Signal(int)

    def __init__(self, session: OperatorSession) -> None:
        super().__init__()
        self._session = session
        self._operation: Operation | None = None
        self._ppe_rows: list[QFrame] = []
        self._ppe_state_labels: dict[int, QLabel] = {}
        self._ppe_icons: dict[int, QLabel] = {}
        self._ppe_details: dict[int, QLabel] = {}
        self._ppe_names: dict[str, int] = {}
        self._camera_state = SafetyCameraState.NOT_INITIALIZED
        self._inference_state = PpeInferenceState.NOT_INITIALIZED
        self._model_classes: frozenset[str] = frozenset()
        self._detection_overlay_maximum_age_ms = 2_000
        self._camera_active = False
        self._catalog_mode = False
        self._available_cameras: tuple[CameraSource, ...] = ()
        self._camera_checks: dict[int, QCheckBox] = {}
        self._selected_cameras: tuple[CameraSource, ...] = ()
        self.setObjectName("safetyVerificationPage")
        self._build_ui()

    @property
    def operation(self) -> Operation | None:
        """Return the operation currently prepared for verification."""

        return self._operation

    @property
    def selected_cameras(self) -> tuple[CameraSource, ...]:
        return self._selected_cameras

    @property
    def verification_camera(self) -> CameraSource | None:
        primary_id = (
            self._operation.risk_area.camera_id
            if self._operation and self._operation.risk_area
            else None
        )
        return next(
            (item for item in self._selected_cameras if item.camera_id == primary_id),
            self._selected_cameras[0] if self._selected_cameras else None,
        )

    def enable_multicamera_catalog(self) -> None:
        self._catalog_mode = True
        self._catalog_notice.show()
        self._catalog_container.show()
        self._catalog_start_button.show()

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
        self._available_cameras = ()
        self._selected_cameras = ()
        self._clear_camera_checks()
        self._operation_name.setText(operation.name)
        self._operation_code.setText(f"#{operation.operation_id}")
        self._operator_name.setText(self._session.operator_name)
        self._operator_detail.setText(f"Operador #{self._session.operator_id}")
        self._risk_area_name.setText(
            operation.risk_area.name
            if operation.risk_area is not None
            else "Não configurada"
        )
        self._risk_area_camera.setText(
            (operation.risk_area.camera_name or "Câmera não vinculada")
            if operation.risk_area is not None
            else ""
        )
        self._render_required_ppe(operation)
        self._set_person("waiting", "AGUARDANDO", "Aguardando a câmera.")
        self._reset_camera()
        self._reset_inference()
        self._release_status.setText("AGUARDANDO VERIFICAÇÃO")
        self._release_title.setText("OPERAÇÃO NÃO LIBERADA")
        self._release_description.setText(
            "A verificação de segurança ainda não foi executada."
        )
        self._set_release_banner_state("blocked")
        self._set_band("AGUARDANDO", "neutral")
        self._release_marker.setPixmap(state_pixmap("neutral", 26))
        self._set_operation_start_enabled(False)

    def activate(self) -> None:
        """Request camera capture when the page becomes the active route."""

        if self._catalog_mode:
            self._catalog_notice.setText("Carregando câmeras ativas do setor…")
            self._catalog_start_button.setEnabled(False)
            if self._operation is not None:
                self.catalog_requested.emit(self._operation.operation_id)
            return
        self._camera_active = True
        self.set_camera_state(
            SafetyCameraState.STARTING,
            "Conectando à câmera configurada para esta estação.",
        )
        self.camera_start_requested.emit()

    def set_cameras(self, operation_id: int, cameras: tuple[CameraSource, ...]) -> None:
        if self._operation is None or self._operation.operation_id != operation_id:
            return
        self._clear_camera_checks()
        self._available_cameras = cameras
        primary_id = self._operation.risk_area.camera_id if self._operation.risk_area else None
        for camera in cameras:
            check = QCheckBox(f"{camera.name} · {camera.source_type.value.upper()}")
            check.setObjectName(f"safetyCameraChoice_{camera.camera_id}")
            check.setChecked(camera.camera_id == primary_id)
            check.stateChanged.connect(self._refresh_camera_selection)
            self._camera_checks[camera.camera_id] = check
            self._catalog_layout.addWidget(check)
        if cameras and not any(check.isChecked() for check in self._camera_checks.values()):
            self._camera_checks[cameras[0].camera_id].setChecked(True)
        self._catalog_notice.setText(
            f"{len(cameras)} câmera(s) disponível(is). Escolha as que participarão."
            if cameras else "Nenhuma câmera ativa no setor desta operação."
        )
        self._refresh_camera_selection()

    def show_camera_catalog_failure(self, operation_id: int, message: str) -> None:
        if self._operation is not None and self._operation.operation_id == operation_id:
            self._catalog_notice.setText(message)
            self._catalog_start_button.setEnabled(False)

    def _clear_camera_checks(self) -> None:
        for check in self._camera_checks.values():
            self._catalog_layout.removeWidget(check)
            check.deleteLater()
        self._camera_checks.clear()

    def _refresh_camera_selection(self) -> None:
        if not self._camera_active:
            self._selected_cameras = tuple(
                camera for camera in self._available_cameras
                if self._camera_checks[camera.camera_id].isChecked()
            )
            self._catalog_start_button.setEnabled(bool(self._selected_cameras))

    def _begin_selected_monitoring(self) -> None:
        self._refresh_camera_selection()
        if self._camera_active or not self._selected_cameras:
            return
        self._camera_active = True
        for check in self._camera_checks.values():
            check.setEnabled(False)
        self._catalog_start_button.setEnabled(False)
        self.set_camera_state(
            SafetyCameraState.STARTING,
            "Conectando à câmera de verificação selecionada.",
        )
        self.camera_start_requested.emit()

    def deactivate(self) -> None:
        """Stop capture and discard the last frame when leaving the route."""

        if self._camera_active:
            self.camera_stop_requested.emit()
        self._camera_active = False
        for check in self._camera_checks.values():
            check.setEnabled(True)
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
                PpeRequirementSafetyState.COLLECTING: ("AGUARDANDO EVIDÊNCIA", "collecting"),
                PpeRequirementSafetyState.CONFIRMED: ("CONFIRMADO", "confirmed"),
                PpeRequirementSafetyState.ABSENT: ("AUSENTE", "absent"),
                PpeRequirementSafetyState.UNSTABLE: ("INCONCLUSIVO", "unstable"),
                PpeRequirementSafetyState.UNMAPPED: ("SEM MAPEAMENTO", "unmapped"),
            }
            text, state = labels[assessment.state]
            detail = _STATE_DETAIL[assessment.state]
            if assessment.detection_class == "capacete" and value.helmet_placement is not None:
                text = {
                    "na_cabeca": "NA CABEÇA",
                    "na_mao": "NA MÃO",
                    "indeterminado": "VERIFICANDO",
                }[value.helmet_placement.value]
                if text == "NA CABEÇA" and state == "confirmed":
                    detail = "Na cabeça em vários quadros seguidos."
            self._set_ppe_state(requirement.ppe_id, text, state)
            self._set_ppe_detail(requirement.ppe_id, detail)

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
            # The gate only confirms EPIs on exactly one identified person.
            self._set_person("ok", "OK", "Só o operador no quadro.")
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

    def show_pending_reasons(self, reasons: tuple[str, ...]) -> None:
        """Say which required PPE is still missing and why, as the engine sees it."""

        if not self._camera_active or not reasons:
            return
        self._release_description.setText(
            "Falta confirmar: " + "; ".join(reasons) + "."
        )
        person = next((item for item in reasons if item.startswith("Pessoa: ")), None)
        if person is not None:
            self._set_person("waiting", "AGUARDANDO", _sentence(person.removeprefix("Pessoa: ")))
        else:
            self._set_person("ok", "OK", "Só o operador no quadro.")
        for reason in reasons:
            name, _, detail = reason.partition(": ")
            ppe_id = self._ppe_names.get(name)
            if ppe_id is not None and detail:
                self._set_ppe_detail(ppe_id, _sentence(detail))

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
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(12)
        layout.addWidget(self._build_header_band())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("safetySplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        splitter.addWidget(self._build_camera_panel())
        splitter.addWidget(self._build_context_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([820, 360])
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_release_banner())

    def _build_header_band(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("safetyHeaderBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 18, 0)
        layout.setSpacing(0)

        block = QFrame()
        block.setObjectName("safetyStateBlock")
        block.setMinimumWidth(236)
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(20, 12, 24, 12)
        block_layout.setSpacing(2)
        self._band_caption = self._label("Liberação", "safetyStateCaption")
        block_layout.addWidget(self._band_caption)
        word = QHBoxLayout()
        word.setSpacing(10)
        self._band_icon = QLabel()
        self._band_icon.setObjectName("safetyStateIcon")
        word.addWidget(self._band_icon)
        self._band_word = self._label("AGUARDANDO", "safetyStateWord")
        word.addWidget(self._band_word)
        word.addStretch(1)
        block_layout.addLayout(word)
        self._state_block = block
        layout.addWidget(block)

        self._operation_name = self._label("Nenhuma operação selecionada", "safetyOperationName")
        self._operation_code = self._label("", "safetyMetadata")
        layout.addWidget(self._fact("Operação", self._operation_name, self._operation_code), 3)
        layout.addWidget(self._divider())
        self._operator_name = self._label(self._session.operator_name, "safetyOperatorName")
        self._operator_detail = self._label(
            f"Operador #{self._session.operator_id}", "safetyMetadata"
        )
        layout.addWidget(self._fact("Funcionário", self._operator_name, self._operator_detail), 2)
        layout.addWidget(self._divider())
        self._risk_area_name = self._label("Não configurada", "safetyRiskAreaName")
        self._risk_area_camera = self._label("", "safetyMetadata")
        layout.addWidget(
            self._fact("Área de risco", self._risk_area_name, self._risk_area_camera), 2
        )
        layout.addStretch(1)

        back_button = QPushButton("Voltar às operações")
        back_button.setObjectName("safetyBackButton")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.setAccessibleName("Voltar para a lista de operações")
        back_button.clicked.connect(self.back_requested)
        layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._set_band("AGUARDANDO", "neutral")
        return bar

    def _fact(self, caption: str, value: QLabel, detail: QLabel) -> QWidget:
        fact = QWidget()
        fact.setObjectName("safetyFact")
        column = QVBoxLayout(fact)
        column.setContentsMargins(18, 10, 18, 10)
        column.setSpacing(1)
        column.addStretch(1)
        column.addWidget(self._label(caption, "safetyFactCaption"))
        for label in (value, detail):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            column.addWidget(label)
        column.addStretch(1)
        return fact

    def _divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("safetyHeaderDivider")
        divider.setFixedWidth(1)
        return divider

    def _build_camera_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("safetyCameraPanel")
        panel.setMinimumWidth(340)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._label("Câmera de verificação", "safetyPanelTitle"))
        header.addWidget(
            self._label("Fique de frente para a câmera, sozinho no quadro", "safetyPanelHint")
        )
        header.addStretch(1)
        self._inference_status = self._label("IA NÃO INICIALIZADA", "safetyInferenceStatus")
        self._inference_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._inference_status)
        self._camera_status = self._label("NÃO INICIALIZADA", "safetyCameraStatus")
        self._camera_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._camera_status)
        self._camera_retry_button = QPushButton("Tentar de novo")
        self._camera_retry_button.setObjectName("safetyCameraRetryButton")
        self._camera_retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_retry_button.setAccessibleName(
            "Tentar inicializar novamente a câmera de verificação"
        )
        self._camera_retry_button.clicked.connect(self._request_camera_retry)
        self._camera_retry_button.hide()
        header.addWidget(self._camera_retry_button)
        layout.addLayout(header)
        layout.addSpacing(10)

        self._camera_stack = QStackedWidget()
        self._camera_stack.setObjectName("safetyCameraStack")

        self._camera_placeholder = QFrame()
        self._camera_placeholder.setObjectName("safetyCameraPlaceholder")
        placeholder_layout = QVBoxLayout(self._camera_placeholder)
        placeholder_layout.setContentsMargins(34, 34, 34, 34)
        placeholder_layout.setSpacing(0)
        placeholder_layout.addStretch(1)

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
        layout.addSpacing(8)

        legend = QHBoxLayout()
        legend.setSpacing(8)
        swatch = QFrame()
        swatch.setObjectName("safetyLegendSwatch")
        swatch.setFixedSize(16, 11)
        legend.addWidget(swatch)
        legend.addWidget(
            self._label(
                "As caixas mostram o que a IA vê agora. A liberação exige confirmação "
                "em vários quadros seguidos.",
                "safetyLegend",
            ),
            1,
        )
        # Raw detection counts stay available for diagnostics, not on screen.
        self._detection_overlay_status = self._label(
            "CAIXAS DA IA NÃO INICIALIZADAS",
            "safetyDetectionOverlayStatus",
        )
        self._detection_overlay_status.hide()
        legend.addWidget(self._detection_overlay_status)
        layout.addLayout(legend)
        return panel

    def _build_context_panel(self) -> QWidget:
        panel = QScrollArea()
        panel.setObjectName("safetyContextScrollArea")
        panel.setWidgetResizable(True)
        panel.setFrameShape(QFrame.Shape.NoFrame)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel.setMinimumWidth(300)

        content = QWidget()
        content.setObjectName("safetyContextContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)

        checklist = QFrame()
        checklist.setObjectName("safetyContextPanel")
        checklist_layout = QVBoxLayout(checklist)
        checklist_layout.setContentsMargins(16, 14, 16, 14)
        checklist_layout.setSpacing(8)
        title = QHBoxLayout()
        title.addWidget(self._label("Para liberar a operação", "safetyPanelTitle"))
        title.addStretch(1)
        self._ppe_count = self._label("Nenhum item", "safetyPpeCount")
        title.addWidget(self._ppe_count)
        checklist_layout.addLayout(title)

        self._catalog_container = QWidget()
        self._catalog_container.setObjectName("safetyCameraCatalog")
        self._catalog_layout = QVBoxLayout(self._catalog_container)
        self._catalog_layout.setContentsMargins(0, 0, 0, 0)
        self._catalog_notice = self._label("", "safetyCameraCatalogNotice")
        self._catalog_notice.setWordWrap(True)
        checklist_layout.addWidget(self._catalog_notice)
        checklist_layout.addWidget(self._catalog_container)
        self._catalog_start_button = QPushButton("Iniciar a verificação")
        self._catalog_start_button.setObjectName("safetyBeginMonitoringButton")
        self._catalog_start_button.clicked.connect(self._begin_selected_monitoring)
        self._catalog_start_button.setEnabled(False)
        checklist_layout.addWidget(self._catalog_start_button)
        self._catalog_notice.hide()
        self._catalog_container.hide()
        self._catalog_start_button.hide()

        (
            self._person_row,
            self._person_icon,
            self._person_detail,
            self._person_state,
        ) = self._checklist_row("Uma pessoa na câmera", "safetyPerson")
        checklist_layout.addWidget(self._person_row)

        self._ppe_container = QWidget()
        self._ppe_container.setObjectName("safetyPpeContainer")
        self._ppe_layout = QVBoxLayout(self._ppe_container)
        self._ppe_layout.setContentsMargins(0, 0, 0, 0)
        self._ppe_layout.setSpacing(8)
        checklist_layout.addWidget(self._ppe_container)

        self._ppe_empty = self._label(
            "Nenhum EPI obrigatório configurado.",
            "safetyPpeEmptyState",
        )
        self._ppe_empty.setWordWrap(True)
        checklist_layout.addWidget(self._ppe_empty)
        layout.addWidget(checklist)

        how = QFrame()
        how.setObjectName("safetyHowPanel")
        how_layout = QVBoxLayout(how)
        how_layout.setContentsMargins(16, 14, 16, 14)
        how_layout.setSpacing(6)
        how_layout.addWidget(self._label("Como funciona", "safetyPanelTitle"))
        how_text = self._label(
            "Cada EPI precisa aparecer em vários quadros seguidos, e o capacete precisa "
            "estar na cabeça. Só o operador pode estar no quadro: se outra pessoa entrar, "
            "a verificação recomeça.",
            "safetyHowText",
        )
        how_text.setWordWrap(True)
        how_layout.addWidget(how_text)
        layout.addWidget(how)
        layout.addStretch(1)
        panel.setWidget(content)
        return panel

    def _checklist_row(self, name: str, prefix: str) -> tuple[QFrame, QLabel, QLabel, QLabel]:
        row = QFrame()
        row.setObjectName("safetyCheckRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(10)
        icon = QLabel()
        icon.setObjectName("safetyCheckIcon")
        icon.setPixmap(state_pixmap("neutral", 18))
        row_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = self._label(name, f"{prefix}Name")
        title.setWordWrap(True)
        text.addWidget(title)
        detail = self._label("Aguardando a câmera.", f"{prefix}Detail")
        detail.setWordWrap(True)
        text.addWidget(detail)
        row_layout.addLayout(text, 1)
        state = self._label("AGUARDANDO", f"{prefix}State")
        state.setProperty("state", "waiting")
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(state, 0, Qt.AlignmentFlag.AlignTop)
        return row, icon, detail, state

    def _build_release_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("safetyReleaseBanner")
        banner.setProperty("state", "blocked")
        self._release_banner = banner
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(16)

        self._release_marker = QLabel()
        self._release_marker.setObjectName("safetyReleaseMarker")
        self._release_marker.setFixedSize(26, 26)
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

        self._start_operation_button = QPushButton("Iniciar operação")
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
        self._ppe_empty.setVisible(not requirements)

        for requirement in requirements:
            row, icon, detail, state = self._checklist_row(requirement.name, "safetyPpe")
            row.setObjectName("safetyPpeRow")
            self._ppe_layout.addWidget(row)
            self._ppe_rows.append(row)
            self._ppe_state_labels[requirement.ppe_id] = state
            self._ppe_icons[requirement.ppe_id] = icon
            self._ppe_details[requirement.ppe_id] = detail
            self._ppe_names[requirement.name] = requirement.ppe_id
        self._refresh_checklist_count()

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
        self._ppe_icons.clear()
        self._ppe_details.clear()
        self._ppe_names.clear()

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
        waiting = "Aguardando a IA." if self._camera_active else "Aguardando a câmera."
        self._set_person("waiting", "AGUARDANDO", waiting)
        for requirement in operation.required_ppe:
            if mark_unmapped and (
                requirement.detection_class is None
                or requirement.detection_class not in self._model_classes
            ):
                self._set_ppe_state(requirement.ppe_id, "SEM MAPEAMENTO", "unmapped")
                detail = _STATE_DETAIL[PpeRequirementSafetyState.UNMAPPED]
            else:
                self._set_ppe_state(requirement.ppe_id, "AGUARDANDO", "waiting")
                detail = waiting
            self._set_ppe_detail(requirement.ppe_id, detail)

    def _set_ppe_state(self, ppe_id: int, text: str, state: str) -> None:
        label = self._ppe_state_labels.get(ppe_id)
        if label is None:
            return
        label.setText(text)
        if label.property("state") != state:
            label.setProperty("state", state)
            self._refresh_style(label)
            self._ppe_icons[ppe_id].setPixmap(state_pixmap(_STATE_TONE.get(state, "neutral"), 18))
            self._refresh_checklist_count()

    def _set_ppe_detail(self, ppe_id: int, text: str) -> None:
        label = self._ppe_details.get(ppe_id)
        if label is not None:
            label.setText(text)

    def _set_person(self, state: str, text: str, detail: str) -> None:
        self._person_state.setText(text)
        self._person_detail.setText(detail)
        if self._person_state.property("state") != state:
            self._person_state.setProperty("state", state)
            self._refresh_style(self._person_state)
            self._person_icon.setPixmap(
                state_pixmap("safe" if state == "ok" else "neutral", 18)
            )
            self._refresh_checklist_count()

    def _refresh_checklist_count(self) -> None:
        if not hasattr(self, "_person_state"):
            return
        total = len(self._ppe_state_labels) + 1
        done = sum(
            label.property("state") == "confirmed" for label in self._ppe_state_labels.values()
        ) + (self._person_state.property("state") == "ok")
        self._ppe_count.setText(
            f"{done} de {total} confirmados" if self._ppe_state_labels else "Nenhum item"
        )

    def _set_band(self, word: str, tone: str) -> None:
        self._band_word.setText(word)
        mark = {"safe": TOKENS["safe_600"], "crit": TOKENS["crit_600"]}.get(tone)
        self._band_icon.setPixmap(
            state_pixmap(tone, 26, color="#fff", mark=mark)
            if mark is not None
            else state_pixmap(tone, 26)
        )
        if self._state_block.property("tone") != tone:
            for widget in (self._state_block, self._band_word, self._band_caption):
                widget.setProperty("tone", tone)
                self._refresh_style(widget)

    def _set_release_banner_state(self, state: str) -> None:
        self._release_banner.setProperty("state", state)
        word, tone = _BAND[state]
        self._release_marker.setPixmap(state_pixmap(tone, 26))
        self._set_band(word, tone)
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


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return f"{text[:1].upper()}{text[1:]}." if text else ""
