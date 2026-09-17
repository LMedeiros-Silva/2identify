from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from PySide6.QtTest import QSignalSpy

from app.controllers.alerts_controller import AlertsController
from app.core.session import AdminSessionContext
from app.domain import (
    AdminAlert,
    AdminAlertPage,
    AdminAuthentication,
    Administrator,
    AlertActor,
    AlertCamera,
    AlertEmployee,
    AlertOccurrence,
    AlertOperationalContext,
    AlertSector,
)
from app.services.admin_alerts_service import AdminAlertsService
from app.ui.alerts import AlertsPage


def sample_alert(*, status: str = "nao_lido") -> AdminAlert:
    now = datetime(2026, 8, 23, 14, 30, tzinfo=UTC)
    actor = AlertActor(1, "Administradora Teste")
    return AdminAlert(
        id=20,
        category="ergonomics",
        level="critical",
        status=status,  # type: ignore[arg-type]
        summary="Tronco inclinado 52° em relação à vertical",
        observation="Triagem ergonômica automática",
        created_at=now,
        received_at=now,
        confirmed_at=now if status != "nao_lido" else None,
        confirmed_by=actor if status != "nao_lido" else None,
        closed_at=now if status == "encerrado" else None,
        closed_by=actor if status == "encerrado" else None,
        occurrence=AlertOccurrence(
            id=10,
            type="ergonomic_risk",
            description="Postura inadequada detectada",
            confidence=0.94,
            image_reference="evidencias/alerta-10.jpg",
            video_reference=None,
            detected_at=now,
            employee=AlertEmployee(
                id=4,
                name="Funcionário Teste",
                registration="MAT-004",
                role="Montador",
                shift="Manhã",
                sector=AlertSector(3, "Montagem"),
            ),
            camera=AlertCamera(
                id=5,
                name="Câmera Posto 5",
                description="Linha de montagem",
                sector=AlertSector(3, "Montagem"),
            ),
        ),
        operational_context=AlertOperationalContext(
            event_id=uuid4(),
            work_session_id=uuid4(),
            operation_id=12,
            risk_area_id=7,
            violation_type="ergonomic_risk",
            subject_key="ergonomics:trunk_inclination",
            operator=AlertActor(2, "Operador Ergonomia"),
            received_at=now,
        ),
    )


def wait_until(qapp, predicate, timeout: float = 3) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("A condição Qt não foi atendida dentro do prazo.")


def test_alert_page_shows_complete_details_and_enforces_action_order(qapp) -> None:
    page = AlertsPage()
    alert = sample_alert()
    page.set_alerts(AdminAlertPage((alert,), 1, 100, 0))

    assert page.detail_title.text() == "Alerta #20"
    assert "Ergonomia" in page.detail_status.text()
    assert page.confirm_button is not None and page.confirm_button.isEnabled()
    assert page.close_button is not None and not page.close_button.isEnabled()
    rendered_text = " ".join(label.text() for label in page.findChildren(type(page.count_label)))
    assert "MAT-004" in rendered_text
    assert "Câmera Posto 5" in rendered_text
    assert "Operador Ergonomia" in rendered_text
    assert "evidencias/alerta-10.jpg" in rendered_text

    confirm_spy = QSignalSpy(page.confirm_requested)
    page.confirm_button.click()
    assert confirm_spy.count() == 1
    page.update_alert(replace(alert, status="lido"))
    assert page.confirm_button is not None and not page.confirm_button.isEnabled()
    assert page.close_button is not None and page.close_button.isEnabled()
    page.close()


class RecordingAlertsProvider:
    def __init__(self) -> None:
        self.alert = sample_alert()
        self.calls: list[str] = []

    def get_alerts(self, _token: str) -> AdminAlertPage:
        self.calls.append("list")
        return AdminAlertPage((self.alert,), 1, 100, 0)

    def confirm_alert(self, _token: str, _alert_id: int) -> AdminAlert:
        self.calls.append("confirm")
        self.alert = replace(
            self.alert,
            status="lido",
            confirmed_at=datetime.now(UTC),
            confirmed_by=AlertActor(1, "Administradora Teste"),
        )
        return self.alert

    def close_alert(self, _token: str, _alert_id: int) -> AdminAlert:
        self.calls.append("close")
        self.alert = replace(
            self.alert,
            status="encerrado",
            closed_at=datetime.now(UTC),
            closed_by=AlertActor(1, "Administradora Teste"),
        )
        return self.alert


def test_alert_controller_loads_confirms_closes_and_refreshes(qapp) -> None:
    provider = RecordingAlertsProvider()
    context = AdminSessionContext()
    context.open(
        AdminAuthentication(
            administrator=Administrator(1, "Admin", "admin", "administrador"),
            access_token="token",
            expires_in=300,
        )
    )
    page = AlertsPage()
    controller = AlertsController(
        page,
        AdminAlertsService(provider),
        context,
        shutdown_timeout_ms=2_000,
    )
    changes = QSignalSpy(controller.alerts_changed)
    controller.start()
    wait_until(qapp, lambda: provider.calls == ["list"])

    controller.confirm_alert(20)
    wait_until(qapp, lambda: "confirm" in provider.calls and changes.count() == 1)
    assert provider.alert.status == "lido"
    wait_until(qapp, lambda: provider.calls.count("list") == 2)

    controller.close_alert(20)
    wait_until(qapp, lambda: "close" in provider.calls and changes.count() == 2)
    assert provider.alert.status == "encerrado"
    assert controller.shutdown()
    page.close()


@pytest.mark.parametrize("with_alerts", [False, True])
def test_alert_page_clears_loading_and_old_error_after_success(qapp, with_alerts) -> None:
    page = AlertsPage()
    page.show_loading()
    page.show_error("Não foi possível carregar os alertas. Verifique a conexão.")
    page.show_loading()
    items = (sample_alert(),) if with_alerts else ()

    page.set_alerts(AdminAlertPage(items, len(items), 100, 0))

    assert page.feedback_label.isHidden()
    assert "Carregando" not in page.count_label.text()
    assert page.refresh_button.isEnabled()
    assert page.alert_list.count() == len(items)
    assert page.empty_label.isHidden() == with_alerts


def test_alert_page_failure_stops_loading_without_claiming_empty_history(qapp) -> None:
    page = AlertsPage()
    page.show_loading()

    page.show_error("Falha na API.")

    assert "Carregando" not in page.count_label.text()
    assert "indisponível" in page.count_label.text().casefold()
    assert page.refresh_button.isEnabled()
    assert not page.feedback_label.isHidden()
