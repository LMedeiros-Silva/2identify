"""Administrative operation registry and risk-area entry point."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.domain import (
    CameraOption,
    OperationCatalog,
    OperationConfiguration,
    OperationDraft,
    RiskArea,
)
from app.ui.operations.camera_registration_dialog import CameraRegistrationDialog


class OperationsPage(QWidget):
    refresh_requested = Signal()
    camera_save_requested = Signal(object)
    risk_area_configuration_requested = Signal(object, object)
    operation_save_requested = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("operations_page")
        self._catalog = OperationCatalog((), ())
        self._risk_areas: dict[int, RiskArea] = {}
        self._operations: dict[int, OperationConfiguration] = {}
        self._ppe_checks: dict[int, QCheckBox] = {}
        self._editing_operation_id: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("Cadastro de operações")
        title.setObjectName("pagina_titulo")
        title_column.addWidget(title)
        subtitle = QLabel(
            "Defina a operação, os EPIs obrigatórios e a área de risco calibrada na câmera."
        )
        subtitle.setObjectName("pagina_subtitulo")
        title_column.addWidget(subtitle)
        heading.addLayout(title_column, 1)
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)

        self.feedback = QLabel()
        self.feedback.setObjectName("operations_feedback")
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        layout.addWidget(self.feedback)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        list_panel = QFrame()
        list_panel.setObjectName("operations_panel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.addWidget(QLabel("Operações cadastradas"))
        self.operation_list = QListWidget()
        self.operation_list.currentItemChanged.connect(self._operation_selected)
        list_layout.addWidget(self.operation_list, 1)
        new_button = QPushButton("Nova operação")
        new_button.clicked.connect(self.reset_form)
        list_layout.addWidget(new_button)
        splitter.addWidget(list_panel)

        form_panel = QFrame()
        form_panel.setObjectName("operations_panel")
        form_layout = QVBoxLayout(form_panel)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ex.: Soldagem industrial")
        form.addRow("Nome da operação*", self.name_edit)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Descrição opcional")
        form.addRow("Descrição", self.description_edit)
        self.active_check = QCheckBox("Operação ativa")
        self.active_check.setChecked(True)
        form.addRow("Status", self.active_check)
        form_layout.addLayout(form)

        ppe_label = QLabel("EPIs obrigatórios*")
        ppe_label.setObjectName("operations_section_title")
        form_layout.addWidget(ppe_label)
        self.ppe_container = QWidget()
        self.ppe_layout = QVBoxLayout(self.ppe_container)
        self.ppe_layout.setContentsMargins(4, 4, 4, 4)
        self.ppe_layout.addStretch()
        ppe_scroll = QScrollArea()
        ppe_scroll.setWidgetResizable(True)
        ppe_scroll.setMaximumHeight(150)
        ppe_scroll.setWidget(self.ppe_container)
        form_layout.addWidget(ppe_scroll)

        camera_form = QFormLayout()
        camera_selector = QWidget()
        camera_selector_layout = QHBoxLayout(camera_selector)
        camera_selector_layout.setContentsMargins(0, 0, 0, 0)
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._camera_changed)
        camera_selector_layout.addWidget(self.camera_combo, 1)
        self.create_camera_button = QPushButton("Cadastrar câmera")
        self.create_camera_button.clicked.connect(self._register_camera)
        camera_selector_layout.addWidget(self.create_camera_button)
        camera_form.addRow("Câmera*", camera_selector)
        self.risk_area_combo = QComboBox()
        camera_form.addRow("Área de risco*", self.risk_area_combo)
        form_layout.addLayout(camera_form)
        area_actions = QHBoxLayout()
        self.configure_area_button = QPushButton("Configurar área de risco")
        self.configure_area_button.clicked.connect(self._configure_area)
        area_actions.addWidget(self.configure_area_button)
        area_hint = QLabel("Selecione uma área para editar ou “Nova área” para cadastrar.")
        area_hint.setWordWrap(True)
        area_actions.addWidget(area_hint, 1)
        form_layout.addLayout(area_actions)
        form_layout.addStretch()
        self.save_button = QPushButton("Salvar operação")
        self.save_button.setObjectName("primary_action")
        self.save_button.clicked.connect(self._save_operation)
        form_layout.addWidget(self.save_button)
        splitter.addWidget(form_panel)
        splitter.setSizes([330, 720])
        layout.addWidget(splitter, 1)

    def set_data(
        self,
        catalog: OperationCatalog,
        risk_areas: tuple[RiskArea, ...],
        operations: tuple[OperationConfiguration, ...],
    ) -> None:
        self._catalog = catalog
        self._risk_areas = {item.id: item for item in risk_areas}
        self._operations = {item.id: item for item in operations}
        self._rebuild_cameras()
        self._rebuild_ppe()
        self.operation_list.clear()
        for operation in operations:
            status = "Ativa" if operation.active else "Inativa"
            item = QListWidgetItem(f"{operation.name}\n{status} · {operation.risk_area.name}")
            item.setData(Qt.ItemDataRole.UserRole, operation.id)
            self.operation_list.addItem(item)
        self.refresh_button.setEnabled(True)
        if not catalog.cameras:
            message = (
                "Nenhuma câmera ativa está cadastrada. Clique em “Cadastrar câmera” "
                "para liberar a configuração da área de risco."
                if catalog.sectors
                else "Nenhum setor ativo está disponível para cadastrar uma câmera."
            )
            self._set_feedback(message, "loading")
        else:
            self._set_feedback(
                f"{len(operations)} operação(ões) e {len(risk_areas)} área(s) carregadas.",
                "success",
            )
        self.reset_form()

    def upsert_risk_area(self, area: RiskArea) -> None:
        self._risk_areas[area.id] = area
        self._rebuild_risk_areas(preferred_id=area.id)
        self.show_ready()
        self._set_feedback("Área de risco salva com sucesso.", "success")

    def upsert_camera(self, camera: CameraOption) -> None:
        cameras = tuple(
            sorted(
                (*self._catalog.cameras, camera),
                key=lambda item: (item.name.casefold(), item.id),
            )
        )
        self._catalog = OperationCatalog(cameras, self._catalog.epis, self._catalog.sectors)
        self._rebuild_cameras()
        index = self.camera_combo.findData(camera.id)
        if index >= 0:
            self.camera_combo.setCurrentIndex(index)
        self.show_ready()
        self._set_feedback(
            "Câmera cadastrada. Agora clique em “Configurar área de risco”.",
            "success",
        )

    def upsert_operation(self, operation: OperationConfiguration) -> None:
        self._operations[operation.id] = operation
        items = tuple(sorted(self._operations.values(), key=lambda item: item.name.casefold()))
        self.set_data(self._catalog, tuple(self._risk_areas.values()), items)
        self._set_feedback("Operação salva com sucesso.", "success")

    def show_loading(self, message: str = "Carregando configurações...") -> None:
        self.refresh_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.configure_area_button.setEnabled(False)
        self.create_camera_button.setEnabled(False)
        self._set_feedback(message, "loading")

    def show_ready(self) -> None:
        self.refresh_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.configure_area_button.setEnabled(bool(self._catalog.cameras))
        self.create_camera_button.setEnabled(bool(self._catalog.sectors))

    def show_error(self, message: str) -> None:
        self.show_ready()
        self._set_feedback(message, "error")

    def reset_form(self) -> None:
        self._editing_operation_id = None
        self.operation_list.clearSelection()
        self.name_edit.clear()
        self.description_edit.clear()
        self.active_check.setChecked(True)
        for checkbox in self._ppe_checks.values():
            checkbox.setChecked(False)
        if self.camera_combo.count():
            self.camera_combo.setCurrentIndex(0)
        self._rebuild_risk_areas()
        self.save_button.setText("Cadastrar operação")
        self.show_ready()

    def _rebuild_cameras(self) -> None:
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        if not self._catalog.cameras:
            self.camera_combo.addItem("Nenhuma câmera cadastrada", None)
        for camera in self._catalog.cameras:
            self.camera_combo.addItem(camera.name, camera.id)
        self.camera_combo.blockSignals(False)
        self._rebuild_risk_areas()

    def _rebuild_ppe(self) -> None:
        while self.ppe_layout.count() > 1:
            item = self.ppe_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._ppe_checks.clear()
        for ppe in self._catalog.epis:
            label = f"{ppe.name} ({ppe.code})" if ppe.code else ppe.name
            checkbox = QCheckBox(label)
            checkbox.setToolTip(ppe.description or ppe.name)
            self._ppe_checks[ppe.id] = checkbox
            self.ppe_layout.insertWidget(self.ppe_layout.count() - 1, checkbox)

    def _rebuild_risk_areas(self, preferred_id: int | None = None) -> None:
        camera_id = self.camera_combo.currentData()
        self.risk_area_combo.clear()
        self.risk_area_combo.addItem("Nova área de risco...", None)
        for area in sorted(self._risk_areas.values(), key=lambda item: item.name.casefold()):
            if area.camera_id == camera_id:
                self.risk_area_combo.addItem(area.name, area.id)
                if area.id == preferred_id:
                    self.risk_area_combo.setCurrentIndex(self.risk_area_combo.count() - 1)

    def _camera_changed(self) -> None:
        self._rebuild_risk_areas()

    def _register_camera(self) -> None:
        if not self._catalog.sectors:
            self.show_error("Cadastre ou ative um setor antes de cadastrar a câmera.")
            return
        dialog = CameraRegistrationDialog(self._catalog.sectors, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_draft is not None:
            self.camera_save_requested.emit(dialog.result_draft)

    def _operation_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        operation = self._operations.get(current.data(Qt.ItemDataRole.UserRole))
        if operation is None:
            return
        self._editing_operation_id = operation.id
        self.name_edit.setText(operation.name)
        self.description_edit.setPlainText(operation.description or "")
        self.active_check.setChecked(operation.active)
        required = {ppe.id for ppe in operation.required_ppe}
        for ppe_id, checkbox in self._ppe_checks.items():
            checkbox.setChecked(ppe_id in required)
        camera_index = self.camera_combo.findData(operation.risk_area.camera_id)
        if camera_index >= 0:
            self.camera_combo.setCurrentIndex(camera_index)
        self._rebuild_risk_areas(preferred_id=operation.risk_area.id)
        self.save_button.setText("Atualizar operação")

    def _configure_area(self) -> None:
        camera_id = self.camera_combo.currentData()
        camera = next((item for item in self._catalog.cameras if item.id == camera_id), None)
        if camera is None:
            self.show_error("Nenhuma câmera ativa está disponível.")
            return
        area_id = self.risk_area_combo.currentData()
        self.risk_area_configuration_requested.emit(camera, self._risk_areas.get(area_id))

    def _save_operation(self) -> None:
        name = self.name_edit.text().strip()
        epi_ids = tuple(
            ppe_id for ppe_id, checkbox in self._ppe_checks.items() if checkbox.isChecked()
        )
        risk_area_id = self.risk_area_combo.currentData()
        if not name:
            self.show_error("Informe o nome da operação.")
            return
        if not epi_ids:
            self.show_error("Selecione pelo menos um EPI obrigatório.")
            return
        if risk_area_id is None:
            self.show_error("Cadastre ou selecione uma área de risco antes de salvar.")
            return
        draft = OperationDraft(
            name=name,
            description=self.description_edit.toPlainText().strip() or None,
            epi_ids=epi_ids,
            risk_area_id=int(risk_area_id),
            active=self.active_check.isChecked(),
        )
        self.operation_save_requested.emit(draft, self._editing_operation_id)

    def _set_feedback(self, message: str, state: str) -> None:
        self.feedback.setText(message)
        self.feedback.setProperty("state", state)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        self.feedback.show()


__all__ = ["OperationsPage"]
