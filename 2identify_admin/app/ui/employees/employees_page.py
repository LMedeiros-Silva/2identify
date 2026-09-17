"""Employee registration, editing, activation and Face ID entry point."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Settings
from app.domain.employees import EmployeeDraft, EmployeeRecord, FaceTemplateDraft
from app.domain.operations import SectorOption
from app.ui.employees.face_enrollment_dialog import FaceEnrollmentDialog


class EmployeesPage(QWidget):
    refresh_requested = Signal()
    save_requested = Signal(object, object, object)

    def __init__(
        self,
        settings: Settings,
        *,
        face_dialog_factory: Callable[..., FaceEnrollmentDialog] = FaceEnrollmentDialog,
    ) -> None:
        super().__init__()
        self.setObjectName("employees_page")
        self._settings = settings
        self._face_dialog_factory = face_dialog_factory
        self._records: dict[int, EmployeeRecord] = {}
        self._editing_id: int | None = None
        self._pending_face: FaceTemplateDraft | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        title = QLabel("Funcionários")
        title.setObjectName("pagina_titulo")
        layout.addWidget(title)
        description = QLabel("Cadastre funcionários e associe um Face ID central pela API.")
        description.setObjectName("pagina_subtitulo")
        layout.addWidget(description)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        self.refresh_button = QPushButton("Atualizar lista")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        list_layout.addWidget(self.refresh_button)
        self.employee_list = QListWidget()
        self.employee_list.setObjectName("employees_list")
        self.employee_list.currentItemChanged.connect(self._selected)
        list_layout.addWidget(self.employee_list)
        splitter.addWidget(list_panel)

        form_panel = QWidget()
        form_layout = QVBoxLayout(form_panel)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(150)
        self.name.setObjectName("employee_name")
        form.addRow("Nome *", self.name)
        self.registration = QLineEdit()
        self.registration.setMaxLength(50)
        self.registration.setObjectName("employee_registration")
        form.addRow("Matrícula *", self.registration)
        self.role = QLineEdit()
        self.role.setMaxLength(100)
        form.addRow("Cargo / função", self.role)
        self.shift = QLineEdit()
        self.shift.setMaxLength(50)
        form.addRow("Turno", self.shift)
        self.sector = QComboBox()
        self.sector.setObjectName("employee_sector")
        form.addRow("Setor *", self.sector)
        self.active = QCheckBox("Funcionário ativo")
        self.active.setChecked(True)
        form.addRow("Situação", self.active)
        form_layout.addLayout(form)

        self.face_button = QPushButton("Capturar Face ID")
        self.face_button.setObjectName("employee_face_button")
        self.face_button.clicked.connect(self._capture_face)
        form_layout.addWidget(self.face_button)
        self.face_status = QLabel("Face ID ainda não capturado nesta edição.")
        self.face_status.setObjectName("employee_face_status")
        form_layout.addWidget(self.face_status)

        actions = QHBoxLayout()
        self.new_button = QPushButton("Novo funcionário")
        self.new_button.clicked.connect(self.new_employee)
        actions.addWidget(self.new_button)
        self.save_button = QPushButton("Salvar funcionário")
        self.save_button.setObjectName("employee_save_button")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.save_button)
        form_layout.addLayout(actions)
        self.feedback = QLabel("Preencha nome, matrícula e setor.")
        self.feedback.setObjectName("employee_feedback")
        self.feedback.setWordWrap(True)
        form_layout.addWidget(self.feedback)
        form_layout.addStretch()
        splitter.addWidget(form_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    def set_data(
        self, records: tuple[EmployeeRecord, ...], sectors: tuple[SectorOption, ...]
    ) -> None:
        current_id = self._editing_id
        self._records = {item.id: item for item in records}
        self.sector.clear()
        for sector in sectors:
            self.sector.addItem(sector.name, sector.id)
        self._render_list()
        if current_id is not None and current_id in self._records:
            self.select_employee(current_id)
        elif not records:
            self.new_employee()
        self.save_button.setEnabled(True)
        self.feedback.setText(f"{len(records)} funcionário(s) carregado(s).")

    def _render_list(self) -> None:
        self.employee_list.blockSignals(True)
        self.employee_list.clear()
        for employee in sorted(self._records.values(), key=lambda item: item.name.casefold()):
            suffix = "" if employee.active else " · INATIVO"
            item = QListWidgetItem(f"{employee.name} · {employee.registration}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, employee.id)
            self.employee_list.addItem(item)
        self.employee_list.blockSignals(False)

    def select_employee(self, employee_id: int) -> None:
        employee = self._records.get(employee_id)
        if employee is None:
            return
        self._editing_id = employee.id
        self._pending_face = None
        self.name.setText(employee.name)
        self.registration.setText(employee.registration)
        self.role.setText(employee.role or "")
        self.shift.setText(employee.shift or "")
        self.active.setChecked(employee.active)
        index = self.sector.findData(employee.sector_id)
        if index >= 0:
            self.sector.setCurrentIndex(index)
        self.face_status.setText("Use Capturar Face ID para cadastrar ou atualizar.")
        for index in range(self.employee_list.count()):
            item = self.employee_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == employee_id:
                self.employee_list.setCurrentItem(item)
                break

    def _selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is not None:
            employee_id = current.data(Qt.ItemDataRole.UserRole)
            if isinstance(employee_id, int) and employee_id != self._editing_id:
                self.select_employee(employee_id)

    def new_employee(self) -> None:
        self._editing_id = None
        self._pending_face = None
        self.employee_list.clearSelection()
        self.name.clear()
        self.registration.clear()
        self.role.clear()
        self.shift.clear()
        self.active.setChecked(True)
        self.face_status.setText("Face ID ainda não capturado nesta edição.")
        self.feedback.setText("Preencha nome, matrícula e setor.")

    def _capture_face(self) -> None:
        dialog = self._face_dialog_factory(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.template is not None:
            self._pending_face = dialog.template
            self.face_status.setText("Frontal, esquerda e direita validadas. Pronto para salvar.")

    def _save(self) -> None:
        sector_id = self.sector.currentData()
        if not isinstance(sector_id, int):
            self.show_error("Selecione um setor cadastrado.")
            return
        try:
            draft = EmployeeDraft(
                name=self.name.text().strip(),
                registration=self.registration.text().strip(),
                role=self.role.text().strip() or None,
                shift=self.shift.text().strip() or None,
                sector_id=sector_id,
                active=self.active.isChecked(),
            )
        except ValueError as error:
            self.show_error(str(error))
            return
        self.save_requested.emit(draft, self._editing_id, self._pending_face)

    def show_loading(self, message: str = "Carregando funcionários...") -> None:
        self.save_button.setEnabled(False)
        self.feedback.setText(message)

    def show_error(self, message: str) -> None:
        self.save_button.setEnabled(True)
        self.feedback.setText(message)

    def employee_saved(self, employee: EmployeeRecord) -> None:
        self._records[employee.id] = employee
        self._editing_id = employee.id
        self._render_list()
        self.save_button.setEnabled(True)
        self.feedback.setText("Funcionário salvo pela API.")

    def face_saved(self) -> None:
        self._pending_face = None
        self.face_status.setText("Face ID cadastrado centralmente.")
        self.feedback.setText("Funcionário e Face ID salvos pela API.")


__all__ = ["EmployeesPage"]
