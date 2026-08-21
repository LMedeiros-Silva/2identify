from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtTest import QSignalSpy

from app.domain import AdminCredentials, Administrator, DashboardSummary
from app.ui.dashboard.dashboard_page import DashboardPage
from app.ui.login.login_window import LoginWindow
from app.ui.main.main_window import MainWindow


def test_login_view_emits_credentials_and_enforces_contract_limits(qapp) -> None:
    view = LoginWindow()
    spy = QSignalSpy(view.login_requested)
    view.campo_usuario.setText("admin")
    view.campo_senha.setText("senha-segura")
    view.botao_entrar.click()

    assert spy.count() == 1
    credentials = spy.at(0)[0]
    assert isinstance(credentials, AdminCredentials)
    assert "senha-segura" not in repr(credentials)
    assert view.campo_usuario.maxLength() == 100
    assert view.campo_senha.maxLength() == 1024
    view.close()


def test_dashboard_starts_unknown_and_offline_state_has_retry(qapp) -> None:
    page = DashboardPage()
    assert page.card_funcionarios.valor_label.text() == "—"  # type: ignore[attr-defined]
    assert page.card_conformidade.valor_label.text() == "—"  # type: ignore[attr-defined]

    retry_spy = QSignalSpy(page.refresh_requested)
    page.show_error("Dashboard indisponível.")
    assert page.retry_button.isVisible() is False  # parent is not shown yet
    assert page.retry_button.isHidden() is False
    page.retry_button.click()
    assert retry_spy.count() == 1


def test_dashboard_renders_explicit_ppe_delivery_summary(qapp) -> None:
    page = DashboardPage()
    page.show_summary(
        DashboardSummary(
            active_employees=3,
            ppe_assignments=12,
            delivered_ppe=9,
            ppe_delivery_percentage=75,
            alerts=2,
            critical_alerts=1,
            generated_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        )
    )

    assert page.card_funcionarios.valor_label.text() == "3"  # type: ignore[attr-defined]
    assert page.card_conformidade.valor_label.text() == "75%"  # type: ignore[attr-defined]
    assert "9 de 12 associações" in page.texto_conformidade.text()
    assert "entregues" in page.texto_conformidade.text()


def test_main_window_exposes_logout_action(qapp) -> None:
    window = MainWindow(
        Administrator(
            id=1,
            name="Admin",
            username="admin",
            profile="administrador",
        )
    )
    spy = QSignalSpy(window.logout_requested)
    window.sidebar.botoes["sair"].click()
    assert spy.count() == 1
    window.close()
