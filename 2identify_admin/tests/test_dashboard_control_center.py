from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from test_alerts_ui import sample_alert
from test_ppe_management_ui import _snapshot

from app.domain import AdminAlertPage, Administrator
from app.domain.ppe_management import (
    ActiveOperationOverallStatus,
    PpeLiveItem,
    PpeLiveState,
    WorkSessionLiveStatus,
)
from app.ui.dashboard.dashboard_page import DashboardPage
from app.ui.main.main_window import MainWindow


def _texts(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_dashboard_waits_for_real_operations_before_counting(qapp) -> None:
    page = DashboardPage()
    assert page.card_operacoes.valor_label.text() == "—"  # type: ignore[attr-defined]
    assert "Aguardando" in page.operations_empty.text()

    page.set_active_operations(())
    assert page.card_operacoes.valor_label.text() == "0"  # type: ignore[attr-defined]
    assert "Nenhuma operação ativa" in page.operations_empty.text()


def test_dashboard_lists_active_operations_with_ppe_state(qapp) -> None:
    page = DashboardPage()
    compliant = replace(
        _snapshot(),
        work_session_id=uuid4(),
        operator_id=16,
        operator_name="Ana Souza",
        ppe=(PpeLiveItem(1, "Capacete", PpeLiveState.CONFIRMED),),
        overall_status=ActiveOperationOverallStatus.COMPLIANT,
    )
    page.set_active_operations((compliant, _snapshot()))

    assert page.card_operacoes.valor_label.text() == "2"  # type: ignore[attr-defined]
    description = page.card_operacoes.descricao_label.text()  # type: ignore[attr-defined]
    assert "1 não conforme(s)" in description
    text = _texts(page)
    assert "Breno Barbosa" in text
    assert "Ausente: Luvas" in text
    assert "Não conforme" in text
    assert "Conforme" in text


def test_ppe_page_feeds_dashboard_and_ended_sessions_leave(qapp) -> None:
    window = MainWindow(Administrator(1, "Admin Teste", "admin", "administrador"))
    window.ppe_management.show_snapshot((_snapshot(),))
    assert window.dashboard.card_operacoes.valor_label.text() == "1"  # type: ignore[attr-defined]

    ended = replace(
        _snapshot(status=WorkSessionLiveStatus.ENDED),
        observed_at=_snapshot().observed_at + timedelta(seconds=5),
    )
    window.ppe_management.apply_update(ended)
    assert window.dashboard.card_operacoes.valor_label.text() == "0"  # type: ignore[attr-defined]
    window.close()


def test_recent_alerts_follow_alert_inbox_and_open_details(qapp) -> None:
    window = MainWindow(Administrator(1, "Admin Teste", "admin", "administrador"))
    now = datetime.now(UTC)
    base = sample_alert()
    older = replace(
        base, id=21, occurrence=replace(base.occurrence, detected_at=now - timedelta(hours=1))
    )
    newer = replace(
        base, id=22, summary="Luvas ausentes", occurrence=replace(base.occurrence, detected_at=now)
    )
    window.alerts.set_alerts(AdminAlertPage((older, newer), 2, 100, 0))

    assert window.dashboard._alerts_layout.count() == 2
    assert window.dashboard.alerts_empty.isHidden()
    first = window.dashboard._alerts_layout.itemAt(0).widget()
    assert "Luvas ausentes" in _texts(first)

    first.clicked.emit()
    assert window.stack.currentWidget() is window.alerts
    assert window.alerts.alert_list.currentItem().data(Qt.ItemDataRole.UserRole) == 22
    window.close()


def test_open_alert_badge_uses_summary_counts(qapp) -> None:
    from test_ui import DashboardAlertStatus, DashboardSummary

    window = MainWindow(Administrator(1, "Admin Teste", "admin", "administrador"))
    window.dashboard.show_summary(
        DashboardSummary(
            active_employees=3,
            ppe_assignments=4,
            delivered_ppe=4,
            ppe_delivery_percentage=100,
            alerts=9,
            critical_alerts=2,
            generated_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
            alert_status=DashboardAlertStatus(new=3, confirmed=2, closed=4),
        )
    )
    assert window.dashboard.card_alertas.valor_label.text() == "5"  # type: ignore[attr-defined]
    assert window.sidebar._badges["alertas"].text() == "5"
    assert not window.sidebar._badges["alertas"].isHidden()
    window.close()


def test_dashboard_shortcuts_navigate_and_update_header(qapp) -> None:
    window = MainWindow(Administrator(1, "Admin Teste", "admin", "administrador"))
    window.dashboard.navigate_requested.emit("epis")
    assert window.stack.currentWidget() is window.ppe_management
    assert window.titulo_header.text() == "Gestão de EPIs"
    window.set_realtime_status("Tempo real conectado.", state="connected")
    assert window.header_conexao.property("state") == "connected"
    assert window.header_conexao.toolTip() == "Tempo real conectado."
    window.close()
