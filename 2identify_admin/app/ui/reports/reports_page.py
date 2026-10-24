"""Admin report filters and XLSX export action."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.admin_reports_service import ReportFilters

_PERIODS = (
    ("all", "Todo o histórico"),
    ("today", "Hoje"),
    ("7", "Últimos 7 dias"),
    ("30", "Últimos 30 dias"),
    ("custom", "Personalizado"),
)
_SEVERITIES = (
    (None, "Todas"),
    ("critical", "Crítico"),
    ("warning", "Atenção"),
)
_COLUMNS = (
    "ID, severidade e status",
    "Categoria e resumo",
    "Observação",
    "Funcionário",
    "Câmera e setor",
    "Operação",
    "Criação e detecção (UTC)",
    "EPI e conformidade",
)


def _label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


class ReportsPage(QWidget):
    export_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("reports_page")
        self._period = "all"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        form_panel = QFrame()
        form_panel.setObjectName("reports_panel")
        form = QGridLayout(form_panel)
        form.setContentsMargins(20, 16, 20, 20)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        form.addWidget(_label("O que exportar", "reports_panel_title"), 0, 0, 1, 2)

        form.addWidget(_label("Período", "reports_field_label"), 1, 0, 1, 2)
        periods = QHBoxLayout()
        periods.setSpacing(6)
        self._period_group = QButtonGroup(self)
        self.period_buttons: dict[str, QPushButton] = {}
        for key, text in _PERIODS:
            button = QPushButton(text)
            button.setObjectName("reports_choice")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=key: self.select_period(value))
            self._period_group.addButton(button)
            periods.addWidget(button)
            self.period_buttons[key] = button
        periods.addStretch()
        form.addLayout(periods, 2, 0, 1, 2)

        form.addWidget(_label("De", "reports_field_label"), 3, 0)
        form.addWidget(_label("Até", "reports_field_label"), 3, 1)
        self.start_date = self._date_edit(QDate.currentDate().addMonths(-1))
        self.end_date = self._date_edit(QDate.currentDate())
        form.addWidget(self.start_date, 4, 0)
        form.addWidget(self.end_date, 4, 1)

        form.addWidget(_label("Gravidade", "reports_field_label"), 5, 0, 1, 2)
        severities = QHBoxLayout()
        severities.setSpacing(6)
        self._severity_group = QButtonGroup(self)
        self.severity_buttons: dict[str | None, QPushButton] = {}
        for value, text in _SEVERITIES:
            button = QPushButton(text)
            button.setObjectName("reports_choice")
            button.setCheckable(True)
            button.setChecked(value is None)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self._update_summary)
            self._severity_group.addButton(button)
            severities.addWidget(button)
            self.severity_buttons[value] = button
        severities.addStretch()
        form.addLayout(severities, 6, 0, 1, 2)

        self.sector = self._choice(form, 7, 0, "Setor", "Todos os setores")
        self.employee = self._choice(form, 7, 1, "Funcionário", "Todos os funcionários")
        self.operation = self._choice(form, 9, 0, "Operação", "Todas as operações")
        self.camera = self._choice(form, 9, 1, "Câmera", "Todas as câmeras")
        form.setRowStretch(11, 1)
        for row in (3, 5, 7, 9):
            form.setRowMinimumHeight(row, 26)
        layout.addWidget(form_panel, 13, Qt.AlignmentFlag.AlignTop)

        summary_panel = QFrame()
        summary_panel.setObjectName("reports_panel")
        summary = QVBoxLayout(summary_panel)
        summary.setContentsMargins(20, 16, 20, 20)
        summary.setSpacing(12)
        summary.addWidget(_label("Resumo da exportação", "reports_panel_title"))
        self.summary_label = _label("", "reports_summary", wrap=True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary.addWidget(self.summary_label)
        summary.addWidget(_label("Colunas da planilha de alertas", "reports_field_label"))
        columns = QGridLayout()
        columns.setHorizontalSpacing(16)
        columns.setVerticalSpacing(2)
        half = (len(_COLUMNS) + 1) // 2
        for index, name in enumerate(_COLUMNS):
            columns.addWidget(_label(f"•  {name}", "reports_column"), index % half, index // half)
        summary.addLayout(columns)
        summary.addWidget(
            _label(
                "O arquivo também traz as abas Resumo, Ocorrências e EPIs.",
                "reports_hint",
                wrap=True,
            )
        )
        self.export_button = QPushButton("Exportar planilha (.xlsx)")
        self.export_button.setObjectName("reports_export_button")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.clicked.connect(self._request_export)
        summary.addWidget(self.export_button)
        self.status = _label("", "reports_status", wrap=True)
        self.status.hide()
        summary.addWidget(self.status)
        summary.addStretch()
        layout.addWidget(summary_panel, 10, Qt.AlignmentFlag.AlignTop)

        self.start_date.dateChanged.connect(self._date_edited)
        self.end_date.dateChanged.connect(self._date_edited)
        self.select_period("all")

    # ======================================================
    # CATÁLOGOS (carregados pelas telas de cadastro)
    # ======================================================

    def set_sectors(self, items: tuple[tuple[int, str], ...]) -> None:
        self._fill(self.sector, items)

    def set_employees(self, items: tuple[tuple[int, str], ...]) -> None:
        self._fill(self.employee, items)

    def set_operations(self, items: tuple[tuple[int, str], ...]) -> None:
        self._fill(self.operation, items)

    def set_cameras(self, items: tuple[tuple[int, str], ...]) -> None:
        self._fill(self.camera, items)

    def _fill(self, combo: QComboBox, items: tuple[tuple[int, str], ...]) -> None:
        selected = combo.currentData()
        placeholder = combo.itemText(0)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for item_id, name in sorted(items, key=lambda item: item[1].casefold()):
            combo.addItem(name, item_id)
        index = combo.findData(selected)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)
        self._update_summary()

    # ======================================================
    # FILTROS
    # ======================================================

    def select_period(self, period: str) -> None:
        self._period = period
        self.period_buttons[period].setChecked(True)
        today = QDate.currentDate()
        starts = {"today": today, "7": today.addDays(-6), "30": today.addDays(-29)}
        for edit in (self.start_date, self.end_date):
            edit.blockSignals(True)
        if period in starts:
            self.start_date.setDate(starts[period])
            self.end_date.setDate(today)
        for edit in (self.start_date, self.end_date):
            edit.blockSignals(False)
            edit.setEnabled(period != "all")
        self._update_summary()

    def filters(self) -> ReportFilters:
        dated = self._period != "all"
        severity = next(
            (value for value, button in self.severity_buttons.items() if button.isChecked()),
            None,
        )
        return ReportFilters(
            date_from=self.start_date.date().toPython() if dated else None,
            date_to=self.end_date.date().toPython() if dated else None,
            sector_id=self.sector.currentData(),
            employee_id=self.employee.currentData(),
            operation_id=self.operation.currentData(),
            camera_id=self.camera.currentData(),
            severity=severity,
        )

    def _date_edited(self) -> None:
        if self._period not in ("custom", "all"):
            self._period = "custom"
            self.period_buttons["custom"].setChecked(True)
        self._update_summary()

    def _update_summary(self) -> None:
        if self._period == "all":
            period = "de <b>todo o histórico</b>"
        else:
            start = self.start_date.date().toPython()
            end = self.end_date.date().toPython()
            period = f"de <b>{start:%d/%m/%Y}</b> a <b>{end:%d/%m/%Y}</b>"
        severity = {
            "critical": "críticos",
            "warning": "de atenção",
        }.get(
            next(
                (str(value) for value, button in self.severity_buttons.items()
                 if button.isChecked() and value),
                "",
            ),
            "",
        )
        scope = []
        for combo, everyone in (
            (self.sector, "todos os setores"),
            (self.employee, "todos os funcionários"),
            (self.operation, "todas as operações"),
            (self.camera, "todas as câmeras"),
        ):
            scope.append(
                everyone if combo.currentData() is None else f"<b>{combo.currentText()}</b>"
            )
        kind = f"Alertas {severity} e ocorrências" if severity else "Todos os alertas e ocorrências"
        self.summary_label.setText(f"{kind} {period}, de {', '.join(scope[:-1])} e {scope[-1]}.")

    def _request_export(self) -> None:
        if self._period != "all" and self.start_date.date() > self.end_date.date():
            self.show_error(
                "A data inicial é depois da data final. Ajuste o período e exporte de novo."
            )
            return
        try:
            filters = self.filters()
        except ValueError as error:
            self.show_error(str(error))
            return
        self.export_requested.emit(filters)

    # ======================================================
    # ESTADOS DA EXPORTAÇÃO
    # ======================================================

    def show_loading(self) -> None:
        self.export_button.setEnabled(False)
        self._set_status("Preparando a planilha...", "loading")

    def show_success(self, path: str) -> None:
        self.export_button.setEnabled(True)
        self._set_status(f"Planilha salva em {path}", "success")

    def show_error(self, message: str) -> None:
        self.export_button.setEnabled(True)
        self._set_status(message, "error")

    def show_cancelled(self) -> None:
        self.export_button.setEnabled(True)
        self._set_status("Exportação cancelada.")

    def _set_status(self, message: str, state: str = "info") -> None:
        self.status.setText(message)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.show()

    def _choice(
        self, form: QGridLayout, row: int, column: int, title: str, everyone: str
    ) -> QComboBox:
        form.addWidget(_label(title, "reports_field_label"), row, column)
        combo = QComboBox()
        combo.setObjectName("reports_select")
        combo.addItem(everyone, None)
        combo.currentIndexChanged.connect(self._update_summary)
        form.addWidget(combo, row + 1, column)
        return combo

    @staticmethod
    def _date_edit(value: QDate) -> QDateEdit:
        edit = QDateEdit(value)
        edit.setObjectName("reports_date")
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd/MM/yyyy")
        return edit

