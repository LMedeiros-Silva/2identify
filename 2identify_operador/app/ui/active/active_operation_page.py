"""Presentation for a locally active industrial work session.

Layout: compact session header, cameras as the dominant area and a narrow
safety panel. Everything shown comes from the controllers' real signals;
the page never derives safety decisions of its own.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.session import OperatorSession
from app.domain import Operation, WorkSession
from app.domain.alert import SafetyAlertSeverity, SafetyViolationType
from app.domain.camera_source import CameraSource, CameraStatus
from app.engine import (
    AlertEngineUpdate,
    ErgonomicAssessment,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyStatus,
    RiskAreaAssessment,
)
from app.ui.components import (
    CameraFrameOverlay,
    CameraFrameView,
    CameraOverlayBox,
    CameraPoseKeypoint,
    CameraPoseOverlay,
    CameraPoseSkeleton,
    CameraRiskZone,
    ExpandedCameraDialog,
)
from app.vision.pose import PoseDetectionBatch
from app.vision.ppe import PpeTrackingBatch

Clock = Callable[[], datetime]

_TILE_STATUS_TEXT = {
    CameraStatus.CONNECTING: "CONECTANDO",
    CameraStatus.ONLINE: "ONLINE",
    CameraStatus.OFFLINE: "OFFLINE",
    CameraStatus.RECONNECTING: "RECONECTANDO",
}
_TILE_PLACEHOLDER_TEXT = {
    CameraStatus.CONNECTING: "Conectando à câmera…",
    CameraStatus.ONLINE: "Aguardando o primeiro quadro…",
    CameraStatus.OFFLINE: "Câmera offline\nAs demais câmeras seguem monitorando.",
    CameraStatus.RECONNECTING: "Reconectando à câmera…",
}
_EVIDENCE_TEXT = {"present": "PRESENTE", "absent": "AUSENTE", "unknown": "INCONCLUSIVO"}
_HELMET_TEXT = {
    "na_cabeca": "NA CABEÇA",
    "na_mao": "NA MÃO",
    "indeterminado": "VERIFICANDO",
}
_REQUIREMENT_TEXT = {
    PpeRequirementSafetyState.COLLECTING: ("AGUARDANDO EVIDÊNCIA", "collecting"),
    PpeRequirementSafetyState.CONFIRMED: ("CONFIRMADO", "confirmed"),
    PpeRequirementSafetyState.ABSENT: ("AUSENTE", "absent"),
    PpeRequirementSafetyState.UNSTABLE: ("INCONCLUSIVO", "unstable"),
    PpeRequirementSafetyState.UNMAPPED: ("SEM MAPEAMENTO", "unmapped"),
}
_OVERALL_TEXT = {
    "idle": "NÃO INICIADO",
    "waiting": "AGUARDANDO EVIDÊNCIA",
    "safe": "SEGURO",
    "inconclusive": "INCONCLUSIVO",
    "attention": "ATENÇÃO",
    "critical": "CRÍTICO",
    "offline": "SEM MONITORAMENTO",
}
_TILE_HEADER_HEIGHT = 38
_TILE_FOOTER_HEIGHT = 30
_GRID_SPACING = 10
_MAX_ALERT_ROWS = 4
# Smallest tile width (px) that keeps a camera readable on a projector.
_MIN_GRID_TILE_WIDTH = 400
_ALERT_TYPE_TEXT = {
    SafetyViolationType.PPE_ABSENT: "EPI AUSENTE",
    SafetyViolationType.PERSON_IN_RISK_AREA: "ÁREA DE RISCO",
    SafetyViolationType.MONITORING_INTERRUPTED: "MONITORAMENTO INTERROMPIDO",
    SafetyViolationType.ERGONOMIC_RISK: "ERGONOMIA",
    SafetyViolationType.FALL_DETECTED: "QUEDA",
}


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
        self._pose_overlay_maximum_age_ms = 1_000
        self._pose_keypoint_confidence_threshold = 0.50
        self._ppe_rows: list[QFrame] = []
        self._ppe_state_labels: dict[int, QLabel] = {}
        self._ppe_alert_labels: dict[int, QLabel] = {}
        self._active_alert_count = 0
        self._active_alerts: tuple = ()
        self._ppe_status: PpeSafetyStatus | None = None
        self._ppe_absent = False
        self._monitoring_failed = False
        self._pose_state = "idle"
        self._fall_detection_enabled: bool | None = None
        self._expanded_camera_dialog: ExpandedCameraDialog | None = None
        self._selected_cameras: tuple[CameraSource, ...] = ()
        self._camera_tiles: dict[int, CameraFrameView] = {}
        self._tile_statuses: dict[int, QLabel] = {}
        self._tile_status_values: dict[int, CameraStatus] = {}
        self._tile_ppe_statuses: dict[int, QLabel] = {}
        self._tile_containers: dict[int, QFrame] = {}
        self._tile_stacks: dict[int, QStackedWidget] = {}
        self._tile_placeholders: dict[int, QLabel] = {}
        self._tile_expand_buttons: dict[int, QPushButton] = {}
        self._focused_camera_id: int | None = None
        self._arranging = False
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
    def selected_cameras(self) -> tuple[CameraSource, ...]:
        return self._selected_cameras

    @property
    def focused_camera_id(self) -> int | None:
        return self._focused_camera_id

    # ======================================================
    # CÂMERAS SELECIONADAS (GRADE)
    # ======================================================

    def set_cameras(self, cameras: tuple[CameraSource, ...]) -> None:
        for container in self._tile_containers.values():
            self._camera_grid.removeWidget(container)
            container.hide()
            container.deleteLater()
        self._camera_tiles.clear()
        self._tile_statuses.clear()
        self._tile_status_values.clear()
        self._tile_ppe_statuses.clear()
        self._tile_containers.clear()
        self._tile_stacks.clear()
        self._tile_placeholders.clear()
        self._tile_expand_buttons.clear()
        self._focused_camera_id = None
        self._selected_cameras = tuple(cameras)
        for camera in cameras:
            self._build_camera_tile(camera)
        self._arrange_camera_tiles()
        self._camera_grid_scroll.setVisible(bool(cameras))
        self._camera_stack.setVisible(not cameras)
        self._camera_expand_button.setVisible(not cameras)
        self._camera_back_button.hide()
        self._camera_retry_button.setVisible(False)
        if not cameras:
            self._camera_count.setText("")
        multi = len(cameras) > 1
        self._ppe_scope.setText(
            f"Estado consolidado das {len(cameras)} câmeras (fusão multicâmera)."
            if multi
            else "Evidência da câmera de monitoramento."
        )
        self._ppe_multicamera_notice.setVisible(multi)
        self._session_cameras.setText(
            ", ".join(camera.name for camera in cameras) if cameras else "Câmera da estação"
        )
        if self._operation is not None:
            self._configure_risk_zone(self._operation)

    def _build_camera_tile(self, camera: CameraSource) -> None:
        camera_id = camera.camera_id
        tile = QFrame()
        tile.setObjectName(f"activeCameraTile_{camera_id}")
        tile.setProperty("role", "cameraTile")
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setSpacing(0)

        header = QFrame()
        header.setProperty("role", "tileHeader")
        header.setFixedHeight(_TILE_HEADER_HEIGHT)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 6, 0)
        header_layout.setSpacing(8)
        name = self._label(camera.name, "activeCameraTileName")
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name.setToolTip(camera.name)
        header_layout.addWidget(name, 1)
        status = self._label(
            _TILE_STATUS_TEXT[CameraStatus.CONNECTING], f"activeCameraTileStatus_{camera_id}"
        )
        status.setProperty("role", "tileStatus")
        status.setProperty("state", "connecting")
        status.setFixedHeight(20)
        header_layout.addWidget(status)
        expand = QPushButton("EXPANDIR")
        expand.setObjectName(f"activeCameraTileExpand_{camera_id}")
        expand.setProperty("role", "tileButton")
        expand.setCursor(Qt.CursorShape.PointingHandCursor)
        expand.setAccessibleName(f"Expandir {camera.name}")
        expand.clicked.connect(lambda: self._toggle_tile_focus(camera_id))
        header_layout.addWidget(expand)
        tile_layout.addWidget(header)

        stack = QStackedWidget()
        stack.setProperty("role", "tileStack")
        placeholder = self._label(
            _TILE_PLACEHOLDER_TEXT[CameraStatus.CONNECTING], "activeCameraTilePlaceholder"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        view = CameraFrameView(
            f"activeCameraTilePreview_{camera_id}",
            aspect_ratio_mode=Qt.AspectRatioMode.KeepAspectRatio,
        )
        stack.addWidget(placeholder)
        stack.addWidget(view)
        tile_layout.addWidget(stack, 1)

        ppe_status = self._label("EPI: AGUARDANDO EVIDÊNCIA", f"activeCameraTilePpe_{camera_id}")
        ppe_status.setProperty("role", "tilePpe")
        ppe_status.setProperty("state", "waiting")
        ppe_status.setFixedHeight(_TILE_FOOTER_HEIGHT)
        ppe_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        tile_layout.addWidget(ppe_status)

        self._camera_tiles[camera_id] = view
        self._tile_statuses[camera_id] = status
        self._tile_status_values[camera_id] = CameraStatus.CONNECTING
        self._tile_ppe_statuses[camera_id] = ppe_status
        self._tile_containers[camera_id] = tile
        self._tile_stacks[camera_id] = stack
        self._tile_placeholders[camera_id] = placeholder
        self._tile_expand_buttons[camera_id] = expand

    @Slot(int, object)
    def update_camera_tile(self, camera_id: int, value: object) -> None:
        view = self._camera_tiles.get(camera_id)
        if self._monitoring_active and view is not None and isinstance(value, QImage):
            view.set_frame(value)
            stack = self._tile_stacks[camera_id]
            if stack.currentWidget() is not view:
                stack.setCurrentWidget(view)

    @Slot(int, object)
    def set_camera_tile_status(self, camera_id: int, value: object) -> None:
        status = self._tile_statuses.get(camera_id)
        if not self._monitoring_active or status is None or not isinstance(value, CameraStatus):
            return
        self._tile_status_values[camera_id] = value
        status.setText(_TILE_STATUS_TEXT[value])
        self._set_state(status, value.value.casefold())
        view = self._camera_tiles[camera_id]
        self._tile_placeholders[camera_id].setText(_TILE_PLACEHOLDER_TEXT[value])
        if value is CameraStatus.OFFLINE:
            view.clear_frame()
            view.clear_overlay()
            view.clear_pose_overlay()
            self._tile_stacks[camera_id].setCurrentWidget(self._tile_placeholders[camera_id])
            self._set_tile_ppe(camera_id, "EPI: INCONCLUSIVO · OFFLINE", "unknown")
        elif not view.has_frame:
            self._tile_stacks[camera_id].setCurrentWidget(self._tile_placeholders[camera_id])
        online = sum(item is CameraStatus.ONLINE for item in self._tile_status_values.values())
        total = len(self._tile_status_values)
        self._camera_status.setText(f"{online}/{total} ONLINE")
        self._set_state(
            self._camera_status,
            "active" if online == total else "unavailable" if online == 0 else "partial",
        )

    def update_camera_ppe_assessment(
        self, camera_id: int, assessment: PpeSafetyAssessment, helmet_placement=None
    ) -> None:
        label = self._tile_ppe_statuses.get(camera_id)
        if label is None:
            return
        parts: list[str] = []
        evidences: set[str] = set()
        for item in assessment.requirements:
            if item.detection_class == "capacete" and helmet_placement is not None:
                text = _HELMET_TEXT.get(helmet_placement.value, "VERIFICANDO")
                evidences.add("unknown" if text == "VERIFICANDO" else item.evidence.value)
            else:
                text = _EVIDENCE_TEXT.get(item.evidence.value, item.evidence.value.upper())
                evidences.add(item.evidence.value)
            parts.append(f"{item.name}: {text}")
        if "absent" in evidences:
            state = "absent"
        elif "unknown" in evidences:
            state = "unknown"
        elif evidences:
            state = "present"
        else:
            state = "waiting"
        self._set_tile_ppe(camera_id, ", ".join(parts) or "EPI: AGUARDANDO EVIDÊNCIA", state)
        if len(self._selected_cameras) == 1:
            self.update_monitoring_assessment(assessment)

    def mark_camera_ppe_unknown(self, camera_id: int, reason: str) -> None:
        if camera_id in self._tile_ppe_statuses:
            self._set_tile_ppe(camera_id, f"EPI: INCONCLUSIVO · {reason}", "unknown")

    def focus_camera(self, camera_id: int | None) -> None:
        """Expand one grid camera in place, or return to the grid with ``None``."""

        if camera_id is not None and camera_id not in self._tile_containers:
            return
        self._focused_camera_id = camera_id
        for tile_id, button in self._tile_expand_buttons.items():
            button.setText("GRADE" if tile_id == camera_id else "EXPANDIR")
            button.setVisible(len(self._selected_cameras) > 1)
        self._camera_back_button.setVisible(camera_id is not None)
        self._arrange_camera_tiles()

    def _toggle_tile_focus(self, camera_id: int) -> None:
        self.focus_camera(None if self._focused_camera_id == camera_id else camera_id)

    def _set_tile_ppe(self, camera_id: int, text: str, state: str) -> None:
        label = self._tile_ppe_statuses[camera_id]
        label.setText(text)
        label.setToolTip(text)
        self._set_state(label, state)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._side_scroll.setFixedWidth(400 if self.width() >= 1500 else 330)
        self._arrange_camera_tiles()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._camera_grid_scroll and event.type() == QEvent.Type.Resize:
            self._arrange_camera_tiles()
        return super().eventFilter(watched, event)

    def _arrange_camera_tiles(self) -> None:
        if not hasattr(self, "_camera_grid") or self._arranging:
            return
        self._arranging = True
        try:
            while self._camera_grid.count():
                self._camera_grid.takeAt(0)
            focused = self._focused_camera_id
            visible = [
                camera
                for camera in self._selected_cameras
                if focused is None or camera.camera_id == focused
            ]
            for camera in self._selected_cameras:
                self._tile_containers[camera.camera_id].setVisible(camera in visible)
            if not visible:
                return
            scrollbar = self._camera_grid_scroll.verticalScrollBar().sizeHint().width()
            width = max(240, self._camera_grid_scroll.width() - scrollbar)
            height = max(200, self._camera_grid_scroll.height())
            count = len(visible)
            chrome = _TILE_HEADER_HEIGHT + _TILE_FOOTER_HEIGHT
            if count == 1:
                # One camera (or an expanded one) uses all the room it has.
                columns, tile_width, tile_height = 1, width, max(260, height)
            else:
                columns, tile_width = self._grid_geometry(count, width, height)
                tile_height = int(tile_width * 9 / 16) + chrome
            used = columns * tile_width + (columns - 1) * _GRID_SPACING
            side = max(0, (width - used) // 2)
            self._camera_grid.setContentsMargins(side, 0, side, 0)
            for index, camera in enumerate(visible):
                tile = self._tile_containers[camera.camera_id]
                tile.setFixedHeight(tile_height)
                self._camera_grid.addWidget(tile, index // columns, index % columns)
            for column in range(3):
                self._camera_grid.setColumnStretch(column, 1 if column < columns else 0)
            rows = math.ceil(count / columns)
            needs_scroll = rows * tile_height + (rows - 1) * _GRID_SPACING > height
            total = len(self._selected_cameras)
            text = f"{total} selecionada(s)"
            if focused is not None:
                text += " · câmera expandida"
            elif needs_scroll:
                text += " · role para ver todas"
            self._camera_count.setText(text)
        finally:
            self._arranging = False

    @staticmethod
    def _grid_geometry(count: int, width: int, height: int) -> tuple[int, int]:
        """Columns and 16:9 tile width that show the most video in the viewport.

        Each candidate sizes its rows to fill the visible height exactly; the
        remaining rows scroll. Tiles never shrink below the legible minimum.
        """

        chrome = _TILE_HEADER_HEIGHT + _TILE_FOOTER_HEIGHT
        best: tuple[float, int, int] | None = None
        for columns in range(2, min(count, 3) + 1):
            column_width = (width - (columns - 1) * _GRID_SPACING) / columns
            for visible_rows in range(1, math.ceil(count / columns) + 1):
                row_height = (height - (visible_rows - 1) * _GRID_SPACING) / visible_rows
                tile_width = min(column_width, (row_height - chrome) * 16 / 9)
                if tile_width < _MIN_GRID_TILE_WIDTH:
                    continue
                score = min(count, visible_rows * columns) * tile_width * tile_width
                if best is None or score > best[0]:
                    best = (score, columns, int(tile_width))
        if best is not None:
            return best[1], best[2]
        columns = 2 if width >= 2 * 300 + _GRID_SPACING else 1
        return columns, int((width - (columns - 1) * _GRID_SPACING) / columns)

    @property
    def active_alert_count(self) -> int:
        return self._active_alert_count

    def configure_detection_overlay(self, maximum_age_ms: int) -> None:
        if maximum_age_ms <= 0:
            raise ValueError("maximum_age_ms deve ser maior que zero")
        self._detection_overlay_maximum_age_ms = maximum_age_ms

    def configure_pose_overlay(
        self,
        *,
        minimum_keypoint_confidence: float,
        maximum_age_ms: int,
    ) -> None:
        if not 0.0 < minimum_keypoint_confidence <= 1.0:
            raise ValueError("minimum_keypoint_confidence deve estar entre zero e um")
        if maximum_age_ms <= 0:
            raise ValueError("maximum_age_ms deve ser maior que zero")
        self._pose_keypoint_confidence_threshold = minimum_keypoint_confidence
        self._pose_overlay_maximum_age_ms = maximum_age_ms

    def configure_fall_detection(self, *, enabled: bool) -> None:
        """Record whether this installation runs fall detection (display only)."""

        self._fall_detection_enabled = bool(enabled)
        self._refresh_fall_presentation()

    # ======================================================
    # SESSÃO
    # ======================================================

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
        self._operation_name.setToolTip(operation.name)
        self._operation_code.setText(f"OPERAÇÃO #{operation.operation_id}")
        self._operator_name.setText(self._operator_session.operator_name)
        self._operator_code.setText(f"Operador #{self._operator_session.operator_id}")
        self._risk_area.setText(
            operation.risk_area.name if operation.risk_area is not None else "Área não configurada"
        )
        self._risk_area_camera.setText(
            operation.risk_area.camera_name or "Câmera não vinculada"
            if operation.risk_area is not None
            else "Sem polígono de risco"
        )
        self._started_at.setText(
            work_session.started_at.astimezone().strftime("%d/%m/%Y · %H:%M:%S")
        )
        self._session_code.setText(str(work_session.session_id).upper())
        count = len(work_session.verified_ppe_ids)
        self._verified_ppe.setText(
            f"{count} EPI confirmado" if count == 1 else f"{count} EPIs confirmados"
        )
        self._set_finish_error("")
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
        self._set_state(self._camera_status, "starting")
        self._monitoring_status.setText("INICIANDO MONITORAMENTO DE EPIs")
        self._set_state(self._monitoring_status, "pending")
        self._refresh_overall_state()
        self._refresh_fall_presentation()
        self.monitoring_start_requested.emit()

    def deactivate_monitoring(self) -> None:
        if self._monitoring_active:
            self.monitoring_stop_requested.emit()
        self._monitoring_active = False
        self._reset_monitoring_presentation()

    def clear(self) -> None:
        """Discard the local presentation snapshot after completion/logout."""

        self.deactivate_monitoring()
        self._close_expanded_camera()
        self._elapsed_timer.stop()
        self._work_session = None
        self._operation = None
        self.set_cameras(())
        self._camera_preview.clear_risk_zones()
        self._elapsed.setText("00:00:00")
        self._set_finish_error("")
        self._finish_button.setText("ENCERRAR OPERAÇÃO")
        self._finish_button.setEnabled(False)

    # ======================================================
    # CÂMERA ÚNICA DA ESTAÇÃO
    # ======================================================

    @Slot()
    def show_monitoring_camera_ready(self) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("ATIVA")
        self._set_state(self._camera_status, "active")
        self._camera_retry_button.hide()
        if self._monitoring_failed and self._camera_failure:
            self._monitoring_failed = False
            self._camera_failure = False
            self._refresh_overall_state()

    @Slot(QImage)
    def update_monitoring_frame(self, frame: QImage) -> None:
        if not self._monitoring_active or frame.isNull():
            return
        for camera_view in self._camera_views():
            camera_view.set_frame(frame)
        if self._camera_stack.currentWidget() is not self._camera_preview:
            self._camera_stack.setCurrentWidget(self._camera_preview)
        self._camera_expand_button.setEnabled(True)
        if self._camera_status.text() != "ATIVA":
            self.show_monitoring_camera_ready()

    @Slot(str, bool)
    def show_monitoring_camera_failure(self, message: str, unavailable: bool) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("INDISPONÍVEL" if unavailable else "FALHA")
        self._set_state(self._camera_status, "unavailable" if unavailable else "error")
        self._camera_placeholder_title.setText(
            "Câmera indisponível" if unavailable else "Falha na câmera"
        )
        self._camera_placeholder_description.setText(message)
        self._close_expanded_camera()
        self._camera_preview.clear_frame()
        self._camera_stack.setCurrentWidget(self._camera_placeholder)
        self._camera_expand_button.setEnabled(False)
        self._camera_retry_button.show()
        self._monitoring_status.setText("MONITORAMENTO DE EPIs INTERROMPIDO")
        self._set_state(self._monitoring_status, "blocked")
        self._set_all_ppe_state("SEM MONITORAMENTO", "unmapped")
        self._monitoring_failed = True
        self._camera_failure = True
        self._refresh_overall_state()

    # ======================================================
    # IA DE EPI
    # ======================================================

    @Slot()
    def show_monitoring_inference_loading(self) -> None:
        if not self._monitoring_active:
            return
        self._inference_status.setText("CARREGANDO MODELO")
        self._set_state(self._inference_status, "loading")
        self._set_all_ppe_state("AGUARDANDO EVIDÊNCIA", "collecting")

    @Slot(object)
    def show_monitoring_inference_ready(self, value: object) -> None:
        if (
            not self._monitoring_active
            or not isinstance(value, tuple)
            or not all(isinstance(item, str) for item in value)
        ):
            return
        self._inference_status.setText("IA ATIVA · COLETANDO AMOSTRAS")
        self._set_state(self._inference_status, "active")

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
        self._set_state(self._inference_status, "error")
        self._monitoring_status.setText(message)
        self._set_state(self._monitoring_status, "blocked")
        for camera_view in self._camera_views():
            camera_view.clear_overlay()
        self._set_all_ppe_state("SEM MONITORAMENTO", "unmapped")
        self._monitoring_failed = True
        self._refresh_overall_state()

    # ======================================================
    # POSE, ERGONOMIA, QUEDA E ÁREA DE RISCO
    # ======================================================

    @Slot()
    def show_ergonomics_loading(self) -> None:
        if not self._monitoring_active:
            return
        self._pose_state = "loading"
        self._ergonomics_status.setText("CARREGANDO POSE")
        self._set_state(self._ergonomics_status, "loading")
        self._ergonomics_detail.setText("Aguardando a primeira avaliação ergonômica.")
        self._refresh_fall_presentation()
        if self._has_calibrated_risk_area():
            self._risk_area_status.setText("AGUARDANDO POSE")
            self._set_state(self._risk_area_status, "loading")
            self._risk_area_detail.setText(
                "A área será verificada assim que o modelo detectar uma pessoa."
            )
        else:
            self.show_risk_area_monitoring_unavailable()

    @Slot()
    def show_ergonomics_ready(self) -> None:
        if not self._monitoring_active:
            return
        self._pose_state = "active"
        self._ergonomics_status.setText("POSE ATIVA")
        self._set_state(self._ergonomics_status, "active")
        self._ergonomics_detail.setText("Procurando postura humana no quadro.")
        self._refresh_fall_presentation()
        if self._has_calibrated_risk_area():
            self._risk_area_status.setText("MONITORANDO")
            self._set_state(self._risk_area_status, "loading")
            self._risk_area_detail.setText("Procurando pessoas dentro do polígono configurado.")
        else:
            self.show_risk_area_monitoring_unavailable()

    @Slot()
    def show_ergonomics_disabled(self) -> None:
        if not self._monitoring_active:
            return
        self._pose_state = "disabled"
        self._ergonomics_status.setText("DESATIVADA")
        self._set_state(self._ergonomics_status, "idle")
        self._ergonomics_detail.setText("A avaliação ergonômica está desativada nesta instalação.")
        for camera_view in self._all_views():
            camera_view.clear_pose_overlay()
        self._refresh_fall_presentation()
        self.show_risk_area_monitoring_unavailable(
            "A detecção da área de risco depende do modelo de pose."
        )

    @Slot(str, bool)
    def show_ergonomics_failure(self, message: str, unavailable: bool) -> None:
        del unavailable
        if not self._monitoring_active:
            return
        self._pose_state = "error"
        self._ergonomics_status.setText("POSE INDISPONÍVEL")
        self._set_state(self._ergonomics_status, "error")
        self._ergonomics_detail.setText(message)
        for camera_view in self._all_views():
            camera_view.clear_pose_overlay()
        self._refresh_fall_presentation()
        self.show_risk_area_monitoring_unavailable(
            "A área não pode ser verificada enquanto o modelo de pose está indisponível."
        )

    @Slot(object)
    def update_monitoring_pose_overlay(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, PoseDetectionBatch):
            return
        overlay = CameraPoseOverlay(
            skeletons=tuple(
                CameraPoseSkeleton(
                    confidence=pose.confidence,
                    keypoints=tuple(
                        CameraPoseKeypoint(
                            x=keypoint.x,
                            y=keypoint.y,
                            confidence=keypoint.confidence,
                        )
                        for keypoint in pose.keypoints
                    ),
                )
                for pose in value.poses
            ),
            source_width=value.frame_width,
            source_height=value.frame_height,
            minimum_keypoint_confidence=(self._pose_keypoint_confidence_threshold),
        )
        for camera_view in self._views_for(value.camera_id):
            camera_view.set_pose_overlay(
                overlay,
                maximum_age_ms=self._pose_overlay_maximum_age_ms,
            )

    @Slot(object)
    def update_ergonomic_assessment(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, ErgonomicAssessment):
            return
        if value.violations:
            critical_count = sum(
                violation.severity.value == "critical" for violation in value.violations
            )
            self._ergonomics_status.setText(
                "RISCO CRÍTICO" if critical_count else "ATENÇÃO À POSTURA"
            )
            self._set_state(self._ergonomics_status, "error" if critical_count else "warning")
            self._ergonomics_detail.setText(
                " · ".join(violation.summary for violation in value.violations)
            )
        elif value.evaluated_people:
            self._ergonomics_status.setText("POSTURA SEM ALERTA")
            self._set_state(self._ergonomics_status, "active")
            self._ergonomics_detail.setText(
                f"{value.evaluated_people} pessoa(s) avaliada(s) no quadro."
            )
        else:
            self._ergonomics_status.setText("POSE ATIVA")
            self._set_state(self._ergonomics_status, "loading")
            self._ergonomics_detail.setText("Nenhuma postura avaliável no quadro.")

    @Slot(object)
    def update_risk_area_assessment(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, RiskAreaAssessment):
            return
        if value.people_inside:
            self._risk_area_status.setText("ENTRADA DETECTADA")
            self._set_state(self._risk_area_status, "error")
            self._risk_area_detail.setText(
                f"{value.people_inside} pessoa(s) dentro da área de risco."
            )
        elif value.evaluated_people:
            self._risk_area_status.setText("ÁREA LIVRE")
            self._set_state(self._risk_area_status, "active")
            self._risk_area_detail.setText(
                f"{value.evaluated_people} pessoa(s) detectada(s) fora da área."
            )
        elif value.detected_people:
            self._risk_area_status.setText("POSE INSUFICIENTE")
            self._set_state(self._risk_area_status, "loading")
            self._risk_area_detail.setText(
                "Pessoa detectada, mas sem pontos corporais confiáveis para avaliar."
            )
        else:
            self._risk_area_status.setText("MONITORANDO")
            self._set_state(self._risk_area_status, "loading")
            self._risk_area_detail.setText("Nenhuma pessoa detectada no quadro.")

    def show_risk_area_monitoring_unavailable(
        self,
        message: str = "Nenhuma área de risco calibrada para esta operação.",
    ) -> None:
        if not self._monitoring_active:
            return
        self._risk_area_status.setText("INDISPONÍVEL")
        self._set_state(self._risk_area_status, "idle")
        self._risk_area_detail.setText(message)

    def _refresh_fall_presentation(self) -> None:
        falls = [
            alert
            for alert in self._active_alerts
            if alert.violation.violation_type is SafetyViolationType.FALL_DETECTED
        ]
        if falls:
            text, state = "QUEDA DETECTADA", "error"
            detail = falls[-1].violation.summary
        elif not self._monitoring_active:
            text, state, detail = "NÃO INICIADA", "idle", "Aguardando o monitoramento."
        elif self._fall_detection_enabled is False:
            text, state = "DESATIVADA", "idle"
            detail = "A detecção de queda está desativada nesta instalação."
        elif self._pose_state in {"disabled", "error"}:
            text, state = "INDISPONÍVEL", "idle"
            detail = "A detecção de queda depende do modelo de pose."
        elif self._pose_state == "active":
            text, state = "MONITORANDO", "active"
            detail = "Nenhuma queda confirmada no momento."
        else:
            text, state = "AGUARDANDO POSE", "loading"
            detail = "A detecção de queda inicia com o modelo de pose."
        self._fall_status.setText(text)
        self._set_state(self._fall_status, state)
        self._fall_detail.setText(detail)

    # ======================================================
    # OVERLAYS E AVALIAÇÃO DE EPI
    # ======================================================

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
        for camera_view in self._views_for(value.camera_id):
            camera_view.set_overlay(
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
        for requirement in value.requirements:
            text, state = _REQUIREMENT_TEXT[requirement.state]
            if requirement.detection_class == "capacete" and value.helmet_placement is not None:
                text = _HELMET_TEXT[value.helmet_placement.value]
            self._set_ppe_state(requirement.ppe_id, text, state)
        self._inference_status.setText(
            f"IA ATIVA · {value.sample_count}/{value.window_size} AMOSTRAS"
        )
        if value.status is PpeSafetyStatus.COMPLIANT:
            self._monitoring_status.setText("EPIs CONFIRMADOS")
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
        self._set_state(self._monitoring_status, state)
        self._ppe_status = value.status
        self._ppe_absent = bool(value.absent_requirement_names)
        if not getattr(self, "_camera_failure", False):
            self._monitoring_failed = False
        self._refresh_overall_state()

    # ======================================================
    # ALERTAS LOCAIS
    # ======================================================

    @Slot(object)
    def update_local_alerts(self, value: object) -> None:
        if not self._monitoring_active or not isinstance(value, AlertEngineUpdate):
            return
        self._active_alert_count = len(value.active_alerts)
        self._active_alerts = tuple(value.active_alerts)
        self._render_alert_rows()
        self._refresh_ppe_inconclusive_flags()
        self._refresh_fall_presentation()
        self._refresh_overall_state()
        if value.active_alerts:
            latest = value.active_alerts[-1]
            count = len(value.active_alerts)
            suffix = "ALERTA LOCAL ATIVO" if count == 1 else "ALERTAS LOCAIS ATIVOS"
            self._alert_badge.setText(f"{count} {suffix}")
            self._set_state(self._alert_badge, "active")
            self._alert_message.setText(f"{latest.violation.summary} · NÃO SINCRONIZADO")
            critical = any(
                alert.violation.severity is SafetyAlertSeverity.CRITICAL
                for alert in value.active_alerts
            )
            state = "critical" if critical else "active"
            self._set_state(self._alert_badge, state)
        elif value.resolved_alerts:
            latest = value.resolved_alerts[-1]
            self._alert_badge.setText("0 ALERTAS LOCAIS ATIVOS")
            self._set_state(self._alert_badge, "resolved")
            self._alert_message.setText(
                f"Condição normalizada: {latest.violation.summary} · registro local"
            )
            state = "resolved"
        else:
            self._reset_alert_presentation()
            return
        self._set_state(self._alert_strip, state)

    @Slot(str, int)
    def show_alert_delivery_succeeded(self, event_id: str, alert_id: int) -> None:
        if not self._monitoring_active or not event_id or alert_id <= 0:
            return
        self._alert_message.setText(
            f"Alerta #{alert_id} registrado e enviado ao Admin em tempo real."
        )

    @Slot(str, str)
    def show_alert_delivery_failure(self, event_id: str, message: str) -> None:
        if not self._monitoring_active or not event_id:
            return
        normalized = message.strip()
        self._alert_message.setText(
            normalized or "Alerta mantido localmente; envio ao Admin não confirmado."
        )

    @Slot(str)
    def show_finish_failure(self, message: str) -> None:
        self._set_finish_error(message)
        self._finish_button.setText("TENTAR ENCERRAR NOVAMENTE")
        self._finish_button.setEnabled(self.is_active)

    def _render_alert_rows(self) -> None:
        while self._alert_rows_layout.count():
            item = self._alert_rows_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        ordered = sorted(
            self._active_alerts,
            key=lambda alert: (
                alert.violation.severity is not SafetyAlertSeverity.CRITICAL,
                -alert.raised_at.timestamp(),
            ),
        )
        for alert in ordered[:_MAX_ALERT_ROWS]:
            self._alert_rows_layout.addWidget(self._alert_row(alert))
        hidden = len(ordered) - _MAX_ALERT_ROWS
        self._alert_more.setText(f"+ {hidden} alerta(s) ativo(s)" if hidden > 0 else "")
        self._alert_more.setVisible(hidden > 0)

    def _alert_row(self, alert) -> QFrame:
        """One active alert: severity, risk type, origin and the engine's reason."""

        violation = alert.violation
        critical = violation.severity is SafetyAlertSeverity.CRITICAL
        state = "critical" if critical else "warning"
        row = QFrame()
        row.setObjectName("activeAlertRow")
        row.setProperty("state", state)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8 if critical else 6, 10, 8 if critical else 6)
        layout.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(8)
        chip = self._label("CRÍTICO" if critical else "ATENÇÃO", "activeAlertSeverity")
        chip.setProperty("state", state)
        top.addWidget(chip)
        risk_type = _ALERT_TYPE_TEXT[violation.violation_type]
        if violation.subject_key.startswith("ppe_inconclusive:"):
            risk_type = "EPI INCONCLUSIVO"
        kind = self._label(risk_type, "activeAlertType")
        kind.setProperty("state", state)
        top.addWidget(kind, 1)
        layout.addLayout(top)
        reason = self._label(violation.summary, "activeAlertRowText")
        reason.setProperty("state", state)
        reason.setWordWrap(True)
        layout.addWidget(reason)
        origin = []
        camera_id = violation.camera_id or violation.evidence_camera_id
        if camera_id is not None:
            origin.append(self._camera_name(camera_id))
        origin.append(f"desde {alert.raised_at.astimezone().strftime('%H:%M:%S')}")
        meta = self._label(" · ".join(origin), "activeAlertMeta")
        meta.setProperty("state", state)
        layout.addWidget(meta)
        return row

    def _camera_name(self, camera_id: int) -> str:
        for camera in self._selected_cameras:
            if camera.camera_id == camera_id:
                return camera.name
        return f"Câmera {camera_id}"

    def _refresh_ppe_inconclusive_flags(self) -> None:
        inconclusive = {
            alert.violation.ppe_id
            for alert in self._active_alerts
            if alert.violation.violation_type is SafetyViolationType.MONITORING_INTERRUPTED
            and alert.violation.subject_key.startswith("ppe_inconclusive:")
        }
        for ppe_id, label in self._ppe_alert_labels.items():
            label.setVisible(ppe_id in inconclusive)

    # ======================================================
    # ESTADO GERAL
    # ======================================================

    def _overall_state(self) -> str:
        if not self._monitoring_active:
            return "idle"
        if self._monitoring_failed:
            return "offline"
        severities = [alert.violation for alert in self._active_alerts]
        if any(item.severity is SafetyAlertSeverity.CRITICAL for item in severities):
            return "critical"
        if self._ppe_status is PpeSafetyStatus.BLOCKED and self._ppe_absent:
            return "critical"
        inconclusive = [
            item
            for item in severities
            if item.violation_type is SafetyViolationType.MONITORING_INTERRUPTED
        ]
        if len(inconclusive) < len(severities) or self._ppe_status is PpeSafetyStatus.BLOCKED:
            return "attention"
        if inconclusive:
            return "inconclusive"
        if self._ppe_status is PpeSafetyStatus.COMPLIANT:
            return "safe"
        return "waiting"

    def _refresh_overall_state(self) -> None:
        state = self._overall_state()
        self._overall_label.setText(_OVERALL_TEXT[state])
        self._set_state(self._overall_label, state)
        self._set_state(self._header_bar, state)
        # EPI conformity never speaks for the whole operation: say so when
        # another active risk keeps the overall state below SEGURO.
        other_risk = (
            self._ppe_status is PpeSafetyStatus.COMPLIANT
            and state in {"critical", "attention", "inconclusive"}
        )
        if other_risk:
            self._ppe_scope_note.setText(
                f"Somente os EPIs. Estado geral {_OVERALL_TEXT[state]} por outro risco ativo."
            )
        self._ppe_scope_note.setVisible(other_risk)

    # ======================================================
    # CONSTRUÇÃO DA INTERFACE
    # ======================================================

    def _build_ui(self) -> None:
        self._camera_failure = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(12)
        layout.addWidget(self._build_header_bar())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_camera_panel(), 1)
        body.addWidget(self._build_side_panel())
        layout.addLayout(body, 1)
        self._refresh_overall_state()

    def _build_header_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("activeHeaderBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(18)
        self._header_bar = bar

        overall = QVBoxLayout()
        overall.setSpacing(3)
        overall.addWidget(self._label("ESTADO GERAL", "activeHeaderCaption"))
        self._overall_label = self._label(_OVERALL_TEXT["idle"], "activeOverallState")
        self._overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overall_label.setMinimumWidth(176)
        overall.addWidget(self._overall_label)
        layout.addLayout(overall)
        layout.addWidget(self._divider())

        operation = QVBoxLayout()
        operation.setSpacing(1)
        self._operation_code = self._label("", "activeHeaderCaption")
        operation.addWidget(self._operation_code)
        self._operation_name = self._label("—", "activeOperationName")
        self._operation_name.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        operation.addWidget(self._operation_name)
        layout.addLayout(operation, 3)

        operator = QVBoxLayout()
        operator.setSpacing(1)
        operator.addWidget(self._label("FUNCIONÁRIO", "activeHeaderCaption"))
        self._operator_name = self._label("—", "activeDetailValue")
        operator.addWidget(self._operator_name)
        self._operator_code = self._label("", "activeMetadata")
        operator.addWidget(self._operator_code)
        layout.addLayout(operator, 2)

        area = QVBoxLayout()
        area.setSpacing(1)
        area.addWidget(self._label("ÁREA DE RISCO", "activeHeaderCaption"))
        self._risk_area = self._label("—", "activeHeaderValue")
        self._risk_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        area.addWidget(self._risk_area)
        self._risk_area_camera = self._label("", "activeMetadata")
        self._risk_area_camera.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        area.addWidget(self._risk_area_camera)
        layout.addLayout(area, 2)

        duration = QVBoxLayout()
        duration.setSpacing(1)
        duration.addWidget(self._label("DURAÇÃO", "activeHeaderCaption"))
        self._elapsed = self._label("00:00:00", "activeElapsed")
        duration.addWidget(self._elapsed)
        layout.addLayout(duration)
        layout.addWidget(self._divider())

        finish = QVBoxLayout()
        finish.setSpacing(3)
        self._finish_button = QPushButton("ENCERRAR OPERAÇÃO")
        self._finish_button.setObjectName("activeFinishButton")
        self._finish_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._finish_button.clicked.connect(self._request_finish)
        self._finish_button.setEnabled(False)
        finish.addWidget(self._finish_button)
        self._finish_error = self._label("", "activeFinishError")
        self._finish_error.setWordWrap(True)
        self._finish_error.setMaximumWidth(260)
        self._finish_error.hide()
        finish.addWidget(self._finish_error)
        layout.addLayout(finish)
        return bar

    def _build_camera_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("activeMonitoringPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("activeCameraToolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(14, 8, 10, 8)
        bar.setSpacing(8)
        bar.addWidget(self._label("CÂMERAS", "activeMonitoringTitle"))
        self._camera_count = self._label("", "activeMetadata")
        bar.addWidget(self._camera_count)
        bar.addStretch(1)
        self._overlay_status = self._label("0 TRACKS", "activeOverlayStatus")
        bar.addWidget(self._overlay_status)
        self._inference_status = self._label("IA NÃO INICIALIZADA", "activeInferenceStatus")
        self._inference_status.setProperty("state", "idle")
        bar.addWidget(self._inference_status)
        self._camera_status = self._label("NÃO INICIALIZADA", "activeCameraStatus")
        self._camera_status.setProperty("state", "idle")
        bar.addWidget(self._camera_status)
        self._camera_back_button = QPushButton("VOLTAR À GRADE")
        self._camera_back_button.setObjectName("activeCameraBackButton")
        self._camera_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_back_button.clicked.connect(lambda: self.focus_camera(None))
        self._camera_back_button.hide()
        bar.addWidget(self._camera_back_button)
        self._camera_expand_button = QPushButton("EXPANDIR CÂMERA")
        self._camera_expand_button.setObjectName("activeCameraExpandButton")
        self._camera_expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_expand_button.setEnabled(False)
        self._camera_expand_button.clicked.connect(self._toggle_expanded_camera)
        bar.addWidget(self._camera_expand_button)
        self._camera_retry_button = QPushButton("TENTAR CÂMERA NOVAMENTE")
        self._camera_retry_button.setObjectName("activeCameraRetryButton")
        self._camera_retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_retry_button.clicked.connect(self._request_camera_retry)
        self._camera_retry_button.hide()
        bar.addWidget(self._camera_retry_button)
        layout.addWidget(toolbar)

        content = QVBoxLayout()
        content.setContentsMargins(10, 10, 10, 10)
        content.setSpacing(0)
        self._camera_stack = QStackedWidget()
        self._camera_stack.setObjectName("activeCameraStack")
        self._camera_stack.setMinimumHeight(420)
        self._camera_placeholder = QFrame()
        self._camera_placeholder.setObjectName("activeCameraPlaceholder")
        placeholder_layout = QVBoxLayout(self._camera_placeholder)
        placeholder_layout.setContentsMargins(24, 20, 24, 20)
        placeholder_layout.addStretch(1)
        self._camera_placeholder_title = self._label(
            "Inicializando câmera operacional",
            "activeCameraPlaceholderTitle",
        )
        self._camera_placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(self._camera_placeholder_title)
        self._camera_placeholder_description = self._label(
            "Aguardando captura para o monitoramento contínuo.",
            "activeCameraPlaceholderDescription",
        )
        self._camera_placeholder_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._camera_placeholder_description.setWordWrap(True)
        placeholder_layout.addWidget(self._camera_placeholder_description)
        placeholder_layout.addStretch(1)
        self._camera_preview = CameraFrameView(
            "activeCameraPreview",
            aspect_ratio_mode=Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._camera_stack.addWidget(self._camera_placeholder)
        self._camera_stack.addWidget(self._camera_preview)
        content.addWidget(self._camera_stack, 1)

        self._camera_grid_scroll = QScrollArea()
        self._camera_grid_scroll.setObjectName("activeCameraGridScroll")
        self._camera_grid_scroll.setWidgetResizable(True)
        self._camera_grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._camera_grid_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._camera_grid_host = QWidget()
        self._camera_grid_host.setObjectName("activeCameraGrid")
        # Opaque host: hidden or moved tiles never leave stale pixels behind.
        self._camera_grid_host.setAutoFillBackground(True)
        self._camera_grid = QGridLayout(self._camera_grid_host)
        self._camera_grid.setContentsMargins(0, 0, 0, 0)
        self._camera_grid.setSpacing(_GRID_SPACING)
        self._camera_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._camera_grid_scroll.setWidget(self._camera_grid_host)
        self._camera_grid_scroll.installEventFilter(self)
        self._camera_grid_scroll.hide()
        content.addWidget(self._camera_grid_scroll, 1)
        layout.addLayout(content, 1)
        return panel

    def _build_side_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("activeSidePanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(330)
        self._side_scroll = scroll
        host = QWidget()
        host.setObjectName("activeSidePanel")
        host.setMinimumWidth(0)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)
        scroll.setWidget(host)

        # Riscos ativos (alertas locais) ficam no topo: são o que exige ação.
        self._alert_strip = QFrame()
        self._alert_strip.setObjectName("activeAlertStrip")
        self._alert_strip.setProperty("state", "idle")
        alert_layout = QVBoxLayout(self._alert_strip)
        alert_layout.setContentsMargins(14, 12, 14, 12)
        alert_layout.setSpacing(6)
        alert_layout.addWidget(self._label("RISCOS ATIVOS", "activeSectionLabel"))
        self._alert_badge = self._label("0 ALERTAS LOCAIS ATIVOS", "activeAlertBadge")
        self._alert_badge.setProperty("state", "idle")
        alert_layout.addWidget(self._alert_badge)
        self._alert_rows_layout = QVBoxLayout()
        self._alert_rows_layout.setSpacing(6)
        alert_layout.addLayout(self._alert_rows_layout)
        self._alert_more = self._label("", "activeMetadata")
        self._alert_more.hide()
        alert_layout.addWidget(self._alert_more)
        self._alert_message = self._label(
            "Nenhuma ocorrência local · SEM ENVIO À API", "activeAlertMessage"
        )
        self._alert_message.setWordWrap(True)
        alert_layout.addWidget(self._alert_message)
        layout.addWidget(self._alert_strip)

        # EPIs: conformidade dos EPIs, separada do estado geral da operação.
        ppe_panel, ppe_layout = self._card("activePpePanel", "EPIs OBRIGATÓRIOS")
        ppe_layout.addWidget(self._label("CONFORMIDADE DOS EPIs", "activeHeaderCaption"))
        self._monitoring_status = self._label(
            "MONITORAMENTO NÃO INICIADO", "activeMonitoringStatus"
        )
        self._monitoring_status.setProperty("state", "idle")
        self._monitoring_status.setWordWrap(True)
        ppe_layout.addWidget(self._monitoring_status)
        self._ppe_scope_note = self._label(
            "",
            "activePpeScopeNote",
        )
        self._ppe_scope_note.setWordWrap(True)
        self._ppe_scope_note.hide()
        ppe_layout.addWidget(self._ppe_scope_note)
        self._ppe_scope = self._label("Evidência da câmera de monitoramento.", "activeMetadata")
        self._ppe_scope.setWordWrap(True)
        ppe_layout.addWidget(self._ppe_scope)
        self._ppe_container = QWidget()
        self._ppe_container.setObjectName("activePpeContainer")
        self._ppe_layout = QVBoxLayout(self._ppe_container)
        self._ppe_layout.setContentsMargins(0, 0, 0, 0)
        self._ppe_layout.setSpacing(6)
        ppe_layout.addWidget(self._ppe_container)
        self._ppe_multicamera_notice = self._label(
            "Cada quadro mostra a evidência da própria câmera; "
            "INCONCLUSIVO não significa ausente.",
            "activeMetadata",
        )
        self._ppe_multicamera_notice.setWordWrap(True)
        self._ppe_multicamera_notice.hide()
        ppe_layout.addWidget(self._ppe_multicamera_notice)
        layout.addWidget(ppe_panel)

        # Riscos monitorados
        risk_panel, risk_layout = self._card("activeRiskPanel", "RISCOS MONITORADOS")
        self._ergonomics_status, self._ergonomics_detail = self._risk_row(
            risk_layout, "Ergonomia", "activeErgonomicsStatus", "activeErgonomicsDetail"
        )
        self._fall_status, self._fall_detail = self._risk_row(
            risk_layout, "Queda", "activeFallStatus", "activeFallDetail"
        )
        self._risk_area_status, self._risk_area_detail = self._risk_row(
            risk_layout, "Área de risco", "activeRiskAreaStatus", "activeRiskAreaDetail"
        )
        layout.addWidget(risk_panel)

        # Detalhes da sessão (recolhível)
        self._details_toggle = QPushButton("DETALHES DA SESSÃO  ▸")
        self._details_toggle.setObjectName("activeDetailsToggle")
        self._details_toggle.setCheckable(True)
        self._details_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._details_toggle)
        details = QFrame()
        details.setObjectName("activeSessionCard")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(14, 12, 14, 12)
        details_layout.setSpacing(2)
        self._started_at = self._detail_row(details_layout, "INÍCIO", "activeHeaderValue")
        self._verified_ppe = self._detail_row(
            details_layout, "SEGURANÇA INICIAL", "activeSafetyValue"
        )
        self._session_cameras = self._detail_row(
            details_layout, "CÂMERAS", "activeHeaderValue"
        )
        self._session_cameras.setText("Câmera da estação")
        self._session_code = self._detail_row(details_layout, "SESSÃO LOCAL", "activeSessionCode")
        details.hide()
        self._details_toggle.toggled.connect(
            lambda checked: (
                details.setVisible(checked),
                self._details_toggle.setText(
                    "DETALHES DA SESSÃO  ▾" if checked else "DETALHES DA SESSÃO  ▸"
                ),
            )
        )
        layout.addWidget(details)
        layout.addStretch(1)
        return scroll

    def _card(self, object_name: str, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        card.setProperty("role", "sideCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self._label(title, "activeSectionLabel"))
        return card, layout

    def _risk_row(
        self, layout: QVBoxLayout, title: str, status_name: str, detail_name: str
    ) -> tuple[QLabel, QLabel]:
        row = QFrame()
        row.setObjectName("activeRiskRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 4)
        row_layout.setSpacing(3)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self._label(title, "activePpeName"))
        header.addStretch(1)
        status = self._label("NÃO INICIALIZADA", status_name)
        status.setProperty("state", "idle")
        status.setProperty("role", "riskStatus")
        header.addWidget(status)
        row_layout.addLayout(header)
        detail = self._label("Aguardando o monitoramento.", detail_name)
        detail.setProperty("role", "riskDetail")
        detail.setWordWrap(True)
        row_layout.addWidget(detail)
        layout.addWidget(row)
        return status, detail

    def _detail_row(self, layout: QVBoxLayout, caption: str, value_name: str) -> QLabel:
        layout.addSpacing(4)
        layout.addWidget(self._label(caption, "activeHeaderCaption"))
        value = self._label("—", value_name)
        value.setWordWrap(True)
        layout.addWidget(value)
        return value

    def _divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("activeHeaderDivider")
        divider.setFixedWidth(1)
        return divider

    def _render_required_ppe(self, operation: Operation) -> None:
        self._clear_ppe_rows()
        for requirement in operation.required_ppe:
            row = QFrame()
            row.setObjectName("activePpeRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(8)
            names = QVBoxLayout()
            names.setSpacing(1)
            name = self._label(requirement.name, "activePpeName")
            name.setWordWrap(True)
            names.addWidget(name)
            flag = self._label("Alerta: monitoramento inconclusivo", "activePpeFlag")
            flag.setWordWrap(True)
            flag.hide()
            names.addWidget(flag)
            layout.addLayout(names, 1)
            state = self._label("AGUARDANDO", "activePpeState")
            state.setProperty("state", "waiting")
            layout.addWidget(state, 0, Qt.AlignmentFlag.AlignVCenter)
            self._ppe_layout.addWidget(row)
            self._ppe_rows.append(row)
            self._ppe_state_labels[requirement.ppe_id] = state
            self._ppe_alert_labels[requirement.ppe_id] = flag
        if not operation.required_ppe:
            empty = self._label("Nenhum EPI obrigatório nesta operação.", "activeMetadata")
            self._ppe_layout.addWidget(empty)

    def _configure_risk_zone(self, operation: Operation) -> None:
        risk_area = operation.risk_area
        if risk_area is None or risk_area.geometry is None or not risk_area.geometry_calibrated:
            for camera_view in (*self._camera_views(), *self._camera_tiles.values()):
                camera_view.clear_risk_zones()
            return
        zones = (
            CameraRiskZone(
                label=risk_area.name,
                vertices=tuple((point.x, point.y) for point in risk_area.geometry.vertices),
            ),
        )
        if not self._selected_cameras:
            for camera_view in self._camera_views():
                camera_view.set_risk_zones(zones)
        for camera_id, camera_view in self._camera_tiles.items():
            if camera_id == risk_area.camera_id:
                camera_view.set_risk_zones(zones)
            else:
                camera_view.clear_risk_zones()

    def _has_calibrated_risk_area(self) -> bool:
        operation = self._operation
        if operation is None or operation.risk_area is None:
            return False
        risk_area = operation.risk_area
        return risk_area.geometry is not None and risk_area.geometry_calibrated

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
        self._ppe_alert_labels.clear()

    def _reset_monitoring_presentation(self) -> None:
        self._close_expanded_camera()
        self._camera_preview.clear_frame()
        self._camera_stack.setCurrentWidget(self._camera_placeholder)
        self._camera_status.setText("NÃO INICIALIZADA")
        self._set_state(self._camera_status, "idle")
        self._inference_status.setText("IA NÃO INICIALIZADA")
        self._set_state(self._inference_status, "idle")
        self._overlay_status.setText("0 TRACKS")
        self._monitoring_status.setText("MONITORAMENTO NÃO INICIADO")
        self._set_state(self._monitoring_status, "idle")
        self._camera_placeholder_title.setText("Inicializando câmera operacional")
        self._camera_placeholder_description.setText(
            "Aguardando captura para o monitoramento contínuo."
        )
        self._camera_retry_button.hide()
        self._camera_expand_button.setText("EXPANDIR CÂMERA")
        self._camera_expand_button.setEnabled(False)
        self._ergonomics_status.setText("NÃO INICIALIZADA")
        self._set_state(self._ergonomics_status, "idle")
        self._ergonomics_detail.setText("Aguardando o monitoramento.")
        self._risk_area_status.setText("NÃO INICIALIZADA")
        self._set_state(self._risk_area_status, "idle")
        self._risk_area_detail.setText("Aguardando o monitoramento.")
        self._ppe_status = None
        self._ppe_absent = False
        self._monitoring_failed = False
        self._camera_failure = False
        self._pose_state = "idle"
        self._reset_alert_presentation()
        self._set_all_ppe_state("AGUARDANDO", "waiting")
        self._refresh_fall_presentation()
        self._refresh_overall_state()

    def _reset_alert_presentation(self) -> None:
        self._active_alert_count = 0
        self._active_alerts = ()
        self._render_alert_rows()
        self._refresh_ppe_inconclusive_flags()
        self._set_state(self._alert_strip, "idle")
        self._alert_badge.setText("0 ALERTAS LOCAIS ATIVOS")
        self._set_state(self._alert_badge, "idle")
        self._alert_message.setText("Nenhuma ocorrência local · SEM ENVIO À API")
        if hasattr(self, "_fall_status"):
            self._refresh_fall_presentation()
            self._refresh_overall_state()

    def _set_all_ppe_state(self, text: str, state: str) -> None:
        for ppe_id in self._ppe_state_labels:
            self._set_ppe_state(ppe_id, text, state)

    def _set_ppe_state(self, ppe_id: int, text: str, state: str) -> None:
        label = self._ppe_state_labels.get(ppe_id)
        if label is None:
            return
        label.setText(text)
        self._set_state(label, state)

    def _set_finish_error(self, message: str) -> None:
        self._finish_error.setText(message)
        self._finish_error.setVisible(bool(message))

    # ======================================================
    # CÂMERA EXPANDIDA (CÂMERA ÚNICA DA ESTAÇÃO)
    # ======================================================

    @Slot()
    def _toggle_expanded_camera(self) -> None:
        dialog = self._expanded_camera_dialog
        if dialog is not None:
            dialog.close()
            return
        if not self._monitoring_active or not self._camera_preview.has_frame:
            return

        dialog = ExpandedCameraDialog(
            parent=self,
            window_title="2Identify · Câmera expandida",
            header_text="MONITORAMENTO OPERACIONAL · CÂMERA EXPANDIDA",
            preview_object_name="expandedCameraPreview",
            aspect_ratio_mode=Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._camera_preview.copy_presentation_to(dialog.camera_view)
        dialog.closed.connect(self._handle_expanded_camera_closed)
        self._expanded_camera_dialog = dialog
        self._camera_expand_button.setText("RESTAURAR CÂMERA")
        dialog.showFullScreen()

    @Slot()
    def _handle_expanded_camera_closed(self) -> None:
        dialog = self._expanded_camera_dialog
        self._expanded_camera_dialog = None
        self._camera_expand_button.setText("EXPANDIR CÂMERA")
        self._camera_expand_button.setEnabled(
            self._monitoring_active and self._camera_preview.has_frame
        )
        if dialog is not None:
            dialog.deleteLater()

    def _close_expanded_camera(self) -> None:
        dialog = self._expanded_camera_dialog
        if dialog is not None:
            dialog.close()

    def _camera_views(self) -> tuple[CameraFrameView, ...]:
        dialog = self._expanded_camera_dialog
        if dialog is None:
            return (self._camera_preview,)
        return self._camera_preview, dialog.camera_view

    def _all_views(self) -> tuple[CameraFrameView, ...]:
        return (*self._camera_views(), *self._camera_tiles.values())

    def _views_for(self, camera_id: int | None) -> tuple[CameraFrameView, ...]:
        if self._selected_cameras:
            view = self._camera_tiles.get(camera_id) if camera_id is not None else None
            return (view,) if view is not None else ()
        return self._camera_views()

    @Slot()
    def _request_camera_retry(self) -> None:
        if not self._monitoring_active:
            return
        self._camera_status.setText("REINICIANDO")
        self._set_state(self._camera_status, "starting")
        self._camera_retry_button.hide()
        self.monitoring_start_requested.emit()

    @Slot()
    def _request_finish(self) -> None:
        session = self._work_session
        if session is None or not session.is_active:
            return
        self._finish_button.setEnabled(False)
        self._finish_button.setText("ENCERRANDO...")
        self._set_finish_error("")
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

    def _set_state(self, widget: QWidget, state: str) -> None:
        """Repolish only when the state really changes, to keep the video FPS."""

        if widget.property("state") == state:
            return
        widget.setProperty("state", state)
        self._refresh_style(widget)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def _utc_now() -> datetime:
    return datetime.now(UTC)
