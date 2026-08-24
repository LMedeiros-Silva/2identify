from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from PySide6.QtTest import QSignalSpy

from app.domain import (
    AdminCredentials,
    Administrator,
    DashboardAlertCategories,
    DashboardAlertStatus,
    DashboardAlertTrendPoint,
    DashboardSummary,
)
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


def test_dashboard_renders_alert_trend_categories_and_status(qapp) -> None:
    first_day = date(2026, 8, 18)
    page = DashboardPage()
    page.show_summary(
        DashboardSummary(
            active_employees=3,
            ppe_assignments=12,
            delivered_ppe=9,
            ppe_delivery_percentage=75,
            alerts=10,
            critical_alerts=4,
            generated_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            alert_status=DashboardAlertStatus(
                new=3,
                confirmed=2,
                closed=5,
            ),
            alert_categories=DashboardAlertCategories(
                ppe=4,
                ergonomics=2,
                risk_area=3,
                monitoring=1,
            ),
            alert_trend=tuple(
                DashboardAlertTrendPoint(
                    day=first_day + timedelta(days=offset),
                    alerts=value,
                )
                for offset, value in enumerate((0, 1, 2, 0, 3, 1, 3))
            ),
        )
    )

    assert page.alert_trend_chart.values == (0, 1, 2, 0, 3, 1, 3)
    assert page.alert_category_chart.values == (4, 2, 3, 1, 0)
    assert page.alert_status_chart.values == (3, 2, 5, 0)


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
