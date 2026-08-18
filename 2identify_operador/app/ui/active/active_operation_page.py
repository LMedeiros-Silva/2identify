"""Presentation for a locally active industrial work session."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.session import OperatorSession
from app.domain import Operation, WorkSession
from app.engine import (
    AlertEngineUpdate,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyStatus,
)
from app.ui.components import (
    CameraFrameOverlay,
    CameraFrameView,
    CameraOverlayBox,
    CameraRiskZone,
)
from app.vision.ppe import PpeTrackingBatch

Clock = Callable[[], datetime]


class ActiveOperationPage(QWidget):
    """Show the local WorkSession and its continuous PPE monitoring state."""

    finish_requested = Signal(str)
    monitoring_start_requested = Signal()
    monitoring_stop_requested = Signal()

    def __init__(
        self,
        operator_session: OperatorSession,
        clock: Clock | None = None,
    ) -> None:
        super().__init__()
        self._operator_session = operator_session
        self._clock = clock or _utc_now
        self._work_session: WorkSession | None = None
        self._operation: Operation | None = None
        self._monitoring_active = False
        self._detection_overlay_maximum_age_ms = 2_000
        self._ppe_rows: list[QFrame] = []
        self._ppe_state_labels: dict[int, QLabel] = {}
        self._active_alert_count = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1_000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self.setObjectName("activeOperationPage")
        self._build_ui()

    @property
    def work_session(self) -> WorkSession | None:
        return self._work_session

    @property
    def operation(self) -> Operation | None:
        return self._operation

    @property
    def is_active(self) -> bool:
        return self._work_session is not None and self._work_session.is_active

    @property
    def is_monitoring_active(self) -> bool:
        return self._monitoring_active

    @property
    def active_alert_count(self) -> int:
        return self._active_alert_count

    def configure_detection_overlay(self, maximum_age_ms: int) -> None:
        if maximum_age_ms <= 0:
            raise ValueError("maximum_age_ms deve ser maior que zero")
        self._detection_overlay_maximum_age_ms = maximum_age_ms

    def set_work_session(
        self,
        work_session: WorkSession,
        operation: Operation,
    ) -> None:
        """Bind the page to matching validated domain snapshots."""

        if not work_session.is_active:
            raise ValueError("a tela ativa exige uma WorkSession ativa")
        if work_session.operator_id != self._operator_session.operator_id:
            raise ValueError("a WorkSession não pertence ao operador autenticado")
        if work_session.operation_id != operation.operation_id:
            raise ValueError("a WorkSession não pertence à operação informada")

        self._work_session = work_session
        self._operation = operation
        self._operation_name.setText(operation.name)
        self._operation_code.setText(f"OPERAÇÃO #{operation.operation_id}")
        self._operator_name.setText(self._operator_session.operator_name)
        self._operator_code.setText(
            f"Operador #{self._operator_session.operator_id}"
        )
        self._risk_area.setText(
            operation.risk_area.name
            if operation.risk_area is not None
            else "Área não configurada"
        )
        self._started_at.setText(
            work_session.started_at.astimezone().strftime("%d/%m/%Y · %H:%M:%S")
        )
        self._session_code.setText(str(work_session.session_id).upper())
        count = len(work_session.verified_ppe_ids)
        self._verified_ppe.setText(
            f"{count} EPI confirmado" if count == 1 else f"{count} EPIs confirmados"
        )
        self._finish_error.clear()
        self._finish_button.setText("ENCERRAR OPERAÇÃO")
        self._finish_button.setEnabled(True)
        self._render_required_ppe(operation)
        self._reset_monitoring_presentation()
        self._configure_risk_zone(operation)
        self._update_elapsed()
        self._elapsed_timer.start()

    def activate_monitoring(self) -> None:
        """Start continuous camera and PPE analysis for the active session."""

        if not self.is_active or self._monitoring_active:
            return
        self._monitoring_active = True
        self._camera_status.setText("INICIALIZANDO")
        self._camera_status.setProperty("state", "starting")
        self._monitoring_status.setText("INICIANDO MONITORAMENTO DE EPIs")
        self._monitoring_status.setProperty("state", "pending")
        self._refresh_style(self._camera_status)
        self._refresh_style(self._monitoring_status)
        self.monitoring_start_requested.emit()

    def deactivate_monitoring(self) -> None:
        if self._monitoring_active:
            self.monitoring_stop_requested.emit()
        self._monitoring_active = False
        self._reset_monitoring_presentation()

    def clear(self) -> None:
        """Discard the local presentation snapshot after completion/logout."""

        self.deactivate_monitoring()
        self._elapsed_timer.stop()
        self._work_session = None
        self._operation = None
        self._camera_preview.clear_risk_zones()
        self._elapsed.setText("00:00:00")
        self._finish_error.clear()
        self._finish_button.setText("ENCERRAR OPERAÇÃO")
        self._finish_button.setEnabled(False)

    @Slot()
    def show_monitoring_camera_ready(self) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("ATIVA")
        self._camera_status.setProperty("state", "active")
        self._camera_retry_button.hide()
        self._refresh_style(self._camera_status)

    @Slot(QImage)
    def update_monitoring_frame(self, frame: QImage) -> None:
        if not self._monitoring_active or frame.isNull():
            return
        self._camera_preview.set_frame(frame)
        self._camera_stack.setCurrentWidget(self._camera_preview)
        self.show_monitoring_camera_ready()

    @Slot(str, bool)
    def show_monitoring_camera_failure(self, message: str, unavailable: bool) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("INDISPONÍVEL" if unavailable else "FALHA")
        self._camera_status.setProperty(
            "state",
            "unavailable" if unavailable else "error",
        )
        self._camera_placeholder_description.setText(message)
        self._camera_preview.clear_frame()
        self._camera_stack.setCurrentWidget(self._camera_placeholder)
        self._camera_retry_button.show()
        self._monitoring_status.setText("MONITORAMENTO DE EPIs INTERROMPIDO")
        self._monitoring_status.setProperty("state", "blocked")
        self._set_all_ppe_state("SEM MONITORAMENTO", "unmapped")
        self._refresh_style(self._camera_status)
        self._refresh_style(self._monitoring_status)

    @Slot()
    def show_monitoring_inference_loading(self) -> None:
        if not self._monitoring_active:
            return
        self._inference_status.setText("CARREGANDO MODELO")
        self._inference_status.setProperty("state", "loading")
        self._set_all_ppe_state("COLETANDO", "collecting")
        self._refresh_style(self._inference_status)

    @Slot(object)
    def show_monitoring_inference_ready(self, value: object) -> None:
        if (
            not self._monitoring_active
            or not isinstance(value, tuple)
            or not all(isinstance(item, str) for item in value)
        ):
            return
        self._inference_status.setText("IA ATIVA · COLETANDO AMOSTRAS")
        self._inference_status.setProperty("state", "active")
        self._refresh_style(self._inference_status)

    @Slot(str, bool)
    def show_monitoring_inference_failure(
        self,
        message: str,
        unavailable: bool,
    ) -> None:
        del unavailable
        if not self._monitoring_active:
            return
        self._inference_status.setText("IA INDISPONÍVEL")
        self._inference_status.setProperty("state", "error")
        self._monitoring_status.setText(message)
        self._monitoring_status.setProperty("state", "blocked")
        self._camera_preview.clear_overlay()
        self._set_all_ppe_state("SEM MONITORAMENTO", "unmapped")
        self._refresh_style(self._inference_status)
        self._refresh_style(self._monitoring_status)

    @Slot(object)
    def update_monitoring_tracking_overlay(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, PpeTrackingBatch):
            return
        visible_tracks = value.visible_tracks
        overlay = CameraFrameOverlay(
            boxes=tuple(
                CameraOverlayBox(
                    f"#{track.track_id} {track.detection.class_name}",
                    track.detection.confidence,
                    track.detection.box.x1,
                    track.detection.box.y1,
                    track.detection.box.x2,
                    track.detection.box.y2,
                )
                for track in visible_tracks
            ),
            source_width=value.frame_width,
            source_height=value.frame_height,
        )
        self._camera_preview.set_overlay(
            overlay,
            maximum_age_ms=self._detection_overlay_maximum_age_ms,
        )
        count = len(visible_tracks)
        confirmed = len(value.confirmed_visible_tracks)
        suffix = "TRACK" if count == 1 else "TRACKS"
        if count == 0:
            detail = "AGUARDANDO DETECÇÕES"
        elif confirmed == count:
            detail = "CONFIRMADO" if count == 1 else "CONFIRMADOS"
        elif confirmed:
            detail = f"{confirmed} CONFIRMADOS"
        else:
            detail = "EM CONFIRMAÇÃO"
        self._overlay_status.setText(f"{count} {suffix} · {detail}")

    @Slot(object)
    def update_monitoring_assessment(self, value: object) -> None:
        operation = self._operation
        if (
            not self._monitoring_active
            or operation is None
            or not isinstance(value, PpeSafetyAssessment)
            or value.operation_id != operation.operation_id
        ):
            return
        labels = {
            PpeRequirementSafetyState.COLLECTING: ("COLETANDO", "collecting"),
            PpeRequirementSafetyState.CONFIRMED: ("CONFIRMADO", "confirmed"),
            PpeRequirementSafetyState.ABSENT: ("AUSENTE", "absent"),
            PpeRequirementSafetyState.UNSTABLE: ("INSTÁVEL", "unstable"),
            PpeRequirementSafetyState.UNMAPPED: ("SEM MAPEAMENTO", "unmapped"),
        }
        for requirement in value.requirements:
            text, state = labels[requirement.state]
            self._set_ppe_state(requirement.ppe_id, text, state)
        self._inference_status.setText(
            f"IA ATIVA · {value.sample_count}/{value.window_size} AMOSTRAS"
        )
        if value.status is PpeSafetyStatus.COMPLIANT:
            self._monitoring_status.setText("EPIs CONFORMES NO MONITORAMENTO ATUAL")
            state = "compliant"
        elif value.status is PpeSafetyStatus.BLOCKED:
            absent = ", ".join(value.absent_requirement_names)
            unmapped = ", ".join(value.unmapped_requirement_names)
            detail = absent or unmapped or "requisitos não atendidos"
            self._monitoring_status.setText(f"NÃO CONFORMIDADE OBSERVADA · {detail}")
            state = "blocked"
        else:
            self._monitoring_status.setText("CONSOLIDANDO EVIDÊNCIA TEMPORAL")
            state = "pending"
        self._monitoring_status.setProperty("state", state)
        self._refresh_style(self._monitoring_status)

    @Slot(object)
    def update_local_alerts(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, AlertEngineUpdate):
            return
        self._active_alert_count = len(value.active_alerts)
        if value.active_alerts:
            latest = value.active_alerts[-1]
            count = len(value.active_alerts)
            suffix = "ALERTA LOCAL ATIVO" if count == 1 else "ALERTAS LOCAIS ATIVOS"
            self._alert_badge.setText(f"{count} {suffix}")
            self._alert_badge.setProperty("state", "active")
            self._alert_message.setText(
                f"{latest.violation.summary} · NÃO SINCRONIZADO"
            )
            state = "active"
        elif value.resolved_alerts:
            latest = value.resolved_alerts[-1]
            self._alert_badge.setText("0 ALERTAS LOCAIS ATIVOS")
            self._alert_badge.setProperty("state", "resolved")
            self._alert_message.setText(
                f"Condição normalizada: {latest.violation.summary} · registro local"
            )
            state = "resolved"
        else:
            self._reset_alert_presentation()
            return
        self._alert_strip.setProperty("state", state)
        self._refresh_style(self._alert_strip)
        self._refresh_style(self._alert_badge)

    @Slot(str)
    def show_finish_failure(self, message: str) -> None:
        self._finish_error.setText(message)
        self._finish_button.setText("TENTAR ENCERRAR NOVAMENTE")
        self._finish_button.setEnabled(self.is_active)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 28)
        layout.setSpacing(0)

        header = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(4)
        title_group.addWidget(self._label("OPERAÇÃO EM EXECUÇÃO", "activeEyebrow"))
        title_group.addWidget(self._label("Operação ativa", "activeTitle"))
        header.addLayout(title_group)
        header.addStretch(1)
        status = self._label("ATIVA", "activeStatusBadge")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(status)
        layout.addLayout(header)
        layout.addSpacing(22)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self._build_operation_card(), 3)
        cards.addWidget(self._build_session_card(), 2)
        layout.addLayout(cards)
        layout.addSpacing(16)
        layout.addWidget(self._build_monitoring_notice(), 1)
        layout.addSpacing(16)

        footer = QFrame()
        footer.setObjectName("activeFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 14, 18, 14)
        footer_layout.setSpacing(16)
        footer_text = QVBoxLayout()
        footer_text.setSpacing(2)
        footer_text.addWidget(
            self._label("SESSÃO LOCAL EM ANDAMENTO", "activeFooterTitle")
        )
        self._finish_error = self._label("", "activeFinishError")
        self._finish_error.setWordWrap(True)
        footer_text.addWidget(self._finish_error)
        footer_layout.addLayout(footer_text, 1)
        self._finish_button = QPushButton("ENCERRAR OPERAÇÃO")
        self._finish_button.setObjectName("activeFinishButton")
        self._finish_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._finish_button.clicked.connect(self._request_finish)
        self._finish_button.setEnabled(False)
        footer_layout.addWidget(self._finish_button)
        layout.addWidget(footer)

    def _build_operation_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("activeOperationCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(0)
        layout.addWidget(self._label("OPERAÇÃO", "activeSectionLabel"))
        layout.addSpacing(6)
        self._operation_name = self._label("—", "activeOperationName")
        self._operation_name.setWordWrap(True)
        layout.addWidget(self._operation_name)
        self._operation_code = self._label("", "activeMetadata")
        layout.addWidget(self._operation_code)
        layout.addSpacing(22)

        details = QHBoxLayout()
        details.setSpacing(28)
        operator = QVBoxLayout()
        operator.setSpacing(3)
        operator.addWidget(self._label("OPERADOR", "activeSectionLabel"))
        self._operator_name = self._label("—", "activeDetailValue")
        operator.addWidget(self._operator_name)
        self._operator_code = self._label("", "activeMetadata")
        operator.addWidget(self._operator_code)
        details.addLayout(operator, 1)

        area = QVBoxLayout()
        area.setSpacing(3)
        area.addWidget(self._label("ÁREA DE RISCO", "activeSectionLabel"))
        self._risk_area = self._label("—", "activeDetailValue")
        self._risk_area.setWordWrap(True)
        area.addWidget(self._risk_area)
        details.addLayout(area, 1)
        layout.addLayout(details)
        layout.addStretch(1)
        return card

    def _build_session_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("activeSessionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(0)
        layout.addWidget(self._label("TEMPO DE OPERAÇÃO", "activeSectionLabel"))
        layout.addSpacing(5)
        self._elapsed = self._label("00:00:00", "activeElapsed")
        layout.addWidget(self._elapsed)
        layout.addSpacing(17)
        layout.addWidget(self._label("INÍCIO", "activeSectionLabel"))
        self._started_at = self._label("—", "activeDetailValue")
        layout.addWidget(self._started_at)
        layout.addSpacing(15)
        layout.addWidget(self._label("SEGURANÇA INICIAL", "activeSectionLabel"))
        self._verified_ppe = self._label("—", "activeSafetyValue")
        layout.addWidget(self._verified_ppe)
        layout.addSpacing(15)
        layout.addWidget(self._label("SESSÃO LOCAL", "activeSectionLabel"))
        self._session_code = self._label("—", "activeSessionCode")
        self._session_code.setWordWrap(True)
        layout.addWidget(self._session_code)
        layout.addStretch(1)
        return card

    def _build_monitoring_notice(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("activeMonitoringPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(
            self._label("MONITORAMENTO CONTÍNUO DE EPIs", "activeMonitoringTitle")
        )
        header.addStretch(1)
        self._overlay_status = self._label("0 TRACKS", "activeOverlayStatus")
        header.addWidget(self._overlay_status)
        self._inference_status = self._label(
            "IA NÃO INICIALIZADA",
            "activeInferenceStatus",
        )
        self._inference_status.setProperty("state", "idle")
        header.addWidget(self._inference_status)
        self._camera_status = self._label("NÃO INICIALIZADA", "activeCameraStatus")
        self._camera_status.setProperty("state", "idle")
        header.addWidget(self._camera_status)
        self._camera_retry_button = QPushButton("TENTAR CÂMERA NOVAMENTE")
        self._camera_retry_button.setObjectName("activeCameraRetryButton")
        self._camera_retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_retry_button.clicked.connect(self._request_camera_retry)
        self._camera_retry_button.hide()
        header.addWidget(self._camera_retry_button)
        layout.addLayout(header)
        layout.addSpacing(11)

        body = QHBoxLayout()
        body.setSpacing(14)
        self._camera_stack = QStackedWidget()
        self._camera_stack.setObjectName("activeCameraStack")
        self._camera_stack.setMinimumHeight(190)
        self._camera_placeholder = QFrame()
        self._camera_placeholder.setObjectName("activeCameraPlaceholder")
        placeholder_layout = QVBoxLayout(self._camera_placeholder)
        placeholder_layout.setContentsMargins(24, 20, 24, 20)
        placeholder_layout.addStretch(1)
        placeholder_title = self._label(
            "Inicializando câmera operacional",
            "activeCameraPlaceholderTitle",
        )
        placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(placeholder_title)
        self._camera_placeholder_description = self._label(
            "Aguardando captura para o monitoramento contínuo.",
            "activeCameraPlaceholderDescription",
        )
        self._camera_placeholder_description.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._camera_placeholder_description.setWordWrap(True)
        placeholder_layout.addWidget(self._camera_placeholder_description)
        placeholder_layout.addStretch(1)
        self._camera_preview = CameraFrameView("activeCameraPreview")
        self._camera_stack.addWidget(self._camera_placeholder)
        self._camera_stack.addWidget(self._camera_preview)
        body.addWidget(self._camera_stack, 3)

        ppe_panel = QFrame()
        ppe_panel.setObjectName("activePpePanel")
        ppe_layout = QVBoxLayout(ppe_panel)
        ppe_layout.setContentsMargins(14, 13, 14, 14)
        ppe_layout.setSpacing(0)
        ppe_layout.addWidget(self._label("EPIs OBRIGATÓRIOS", "activeSectionLabel"))
        ppe_layout.addSpacing(8)
        self._ppe_container = QWidget()
        self._ppe_container.setObjectName("activePpeContainer")
        self._ppe_layout = QVBoxLayout(self._ppe_container)
        self._ppe_layout.setContentsMargins(0, 0, 0, 0)
        self._ppe_layout.setSpacing(6)
        ppe_layout.addWidget(self._ppe_container)
        ppe_layout.addStretch(1)
        body.addWidget(ppe_panel, 2)
        layout.addLayout(body, 1)
        layout.addSpacing(10)

        self._monitoring_status = self._label(
            "MONITORAMENTO NÃO INICIADO",
            "activeMonitoringStatus",
        )
        self._monitoring_status.setProperty("state", "idle")
        self._monitoring_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._monitoring_status)
        layout.addSpacing(8)

        self._alert_strip = QFrame()
        self._alert_strip.setObjectName("activeAlertStrip")
        self._alert_strip.setProperty("state", "idle")
        alert_layout = QHBoxLayout(self._alert_strip)
        alert_layout.setContentsMargins(10, 7, 10, 7)
        alert_layout.setSpacing(10)
        self._alert_badge = self._label(
            "0 ALERTAS LOCAIS ATIVOS",
            "activeAlertBadge",
        )
        self._alert_badge.setProperty("state", "idle")
        alert_layout.addWidget(self._alert_badge)
        self._alert_message = self._label(
            "Nenhuma ocorrência local · SEM ENVIO À API",
            "activeAlertMessage",
        )
        self._alert_message.setWordWrap(True)
        alert_layout.addWidget(self._alert_message, 1)
        layout.addWidget(self._alert_strip)
        return frame

    def _render_required_ppe(self, operation: Operation) -> None:
        self._clear_ppe_rows()
        for requirement in operation.required_ppe:
            row = QFrame()
            row.setObjectName("activePpeRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(9, 7, 9, 7)
            layout.setSpacing(8)
            name = self._label(requirement.name, "activePpeName")
            name.setWordWrap(True)
            layout.addWidget(name, 1)
            state = self._label("AGUARDANDO", "activePpeState")
            state.setProperty("state", "waiting")
            layout.addWidget(state)
            self._ppe_layout.addWidget(row)
            self._ppe_rows.append(row)
            self._ppe_state_labels[requirement.ppe_id] = state

    def _configure_risk_zone(self, operation: Operation) -> None:
        risk_area = operation.risk_area
        if (
            risk_area is None
            or risk_area.geometry is None
            or not risk_area.geometry_calibrated
        ):
            self._camera_preview.clear_risk_zones()
            return
        self._camera_preview.set_risk_zones(
            (
                CameraRiskZone(
                    label=risk_area.name,
                    vertices=tuple(
                        (point.x, point.y)
                        for point in risk_area.geometry.vertices
                    ),
                ),
            )
        )

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

    def _reset_monitoring_presentation(self) -> None:
        self._camera_preview.clear_frame()
        self._camera_stack.setCurrentWidget(self._camera_placeholder)
        self._camera_status.setText("NÃO INICIALIZADA")
        self._camera_status.setProperty("state", "idle")
        self._inference_status.setText("IA NÃO INICIALIZADA")
        self._inference_status.setProperty("state", "idle")
        self._overlay_status.setText("0 TRACKS")
        self._monitoring_status.setText("MONITORAMENTO NÃO INICIADO")
        self._monitoring_status.setProperty("state", "idle")
        self._camera_placeholder_description.setText(
            "Aguardando captura para o monitoramento contínuo."
        )
        self._camera_retry_button.hide()
        self._reset_alert_presentation()
        self._set_all_ppe_state("AGUARDANDO", "waiting")
        self._refresh_style(self._camera_status)
        self._refresh_style(self._inference_status)
        self._refresh_style(self._monitoring_status)

    def _reset_alert_presentation(self) -> None:
        self._active_alert_count = 0
        self._alert_strip.setProperty("state", "idle")
        self._alert_badge.setText("0 ALERTAS LOCAIS ATIVOS")
        self._alert_badge.setProperty("state", "idle")
        self._alert_message.setText(
            "Nenhuma ocorrência local · SEM ENVIO À API"
        )
        self._refresh_style(self._alert_strip)
        self._refresh_style(self._alert_badge)

    def _set_all_ppe_state(self, text: str, state: str) -> None:
        for ppe_id in self._ppe_state_labels:
            self._set_ppe_state(ppe_id, text, state)

    def _set_ppe_state(self, ppe_id: int, text: str, state: str) -> None:
        label = self._ppe_state_labels.get(ppe_id)
        if label is None:
            return
        label.setText(text)
        label.setProperty("state", state)
        self._refresh_style(label)

    @Slot()
    def _request_camera_retry(self) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("REINICIANDO")
        self._camera_status.setProperty("state", "starting")
        self._camera_retry_button.hide()
        self._refresh_style(self._camera_status)
        self.monitoring_start_requested.emit()

    @Slot()
    def _request_finish(self) -> None:
        session = self._work_session
        if session is None or not session.is_active:
            return
        self._finish_button.setEnabled(False)
        self._finish_button.setText("ENCERRANDO...")
        self._finish_error.clear()
        self.finish_requested.emit(str(session.session_id))

    @Slot()
    def _update_elapsed(self) -> None:
        session = self._work_session
        if session is None:
            self._elapsed.setText("00:00:00")
            return
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            self._elapsed.setText("--:--:--")
            return
        elapsed_seconds = max(
            0,
            int((now.astimezone(UTC) - session.started_at).total_seconds()),
        )
        hours, remainder = divmod(elapsed_seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        self._elapsed.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def _utc_now() -> datetime:
    return datetime.now(UTC)
