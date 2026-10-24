"""Configurações shows the real API address, its last answer and the session."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtTest import QSignalSpy
from test_employees import _record
from test_ui import DashboardSummary

from app.core.config import Settings
from app.domain import Administrator
from app.domain.operations import SectorOption
from app.ui.main.main_window import MainWindow


def _window() -> MainWindow:
    return MainWindow(
        Administrator(1, "Admin Teste", "admin", "administrador"),
        Settings(_env_file=None, API_URL="http://api.test:8000"),
    )


def test_settings_route_shows_connection_and_session(qapp) -> None:
    window = _window()
    window.sidebar.selecionar("configuracoes")

    page = window.settings_page
    assert window.stack.currentWidget() is page
    assert window.titulo_header.text() == "Configurações"
    assert page.api_chip.text() == "Aguardando"

    window.dashboard.show_summary(
        DashboardSummary(
            active_employees=1,
            ppe_assignments=1,
            delivered_ppe=1,
            ppe_delivery_percentage=100,
            alerts=0,
            critical_alerts=0,
            generated_at=datetime(2026, 10, 24, 12, 30, tzinfo=UTC),
        )
    )
    assert page.api_chip.text() == "Conectada"
    assert "24/10/2026" in page.last_response.text()

    window.dashboard.show_error("A API não respondeu.")
    assert page.api_chip.text() == "Sem resposta"
    assert page.last_response.text() == "A API não respondeu."

    window.set_realtime_status("Tempo real conectado.", state="connected")
    assert page.realtime_chip.text() == "Conectado"
    window.close()


def test_settings_connection_test_asks_the_dashboard_for_a_fresh_summary(qapp) -> None:
    window = _window()
    spy = QSignalSpy(window.dashboard.refresh_requested)
    window.settings_page.test_button.click()
    assert spy.count() == 1
    assert not window.settings_page.test_button.isEnabled()
    window.close()


def test_report_filters_use_names_loaded_by_the_registration_pages(qapp) -> None:
    window = _window()
    window.employees.set_data((_record(),), (SectorOption(1, "Usinagem"),))
    assert window.reports.sector.findText("Usinagem") > 0
    assert window.reports.employee.findData(_record().id) > 0
    window.close()
