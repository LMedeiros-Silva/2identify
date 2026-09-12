from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.domain.ppe_management import (
    ActiveOperationOverallStatus,
    ActiveOperationSnapshot,
    PpeLiveItem,
    PpeLiveState,
    WorkSessionLiveStatus,
)
from app.ui.ppe import PpeManagementPage


def _snapshot(*, status: WorkSessionLiveStatus = WorkSessionLiveStatus.ACTIVE):
    return ActiveOperationSnapshot(
        work_session_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_status=status,
        operator_id=15,
        operator_name="Breno Barbosa",
        operation_id=7,
        operation_name="Linha de montagem",
        started_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        observed_at=datetime(2026, 8, 25, 12, 0, 5, tzinfo=UTC),
        camera_id=3,
        camera_name="Câmera Linha A",
        ppe=(
            PpeLiveItem(1, "Capacete", PpeLiveState.CONFIRMED),
            PpeLiveItem(2, "Luvas", PpeLiveState.ABSENT),
        ),
        overall_status=ActiveOperationOverallStatus.NON_COMPLIANT,
    )


def test_page_renders_cards_filters_and_keeps_snapshot_when_offline(qapp) -> None:
    page = PpeManagementPage()
    page.show_snapshot((_snapshot(),))

    assert page.online_count_label.text() == "1"
    assert page.compliant_count_label.text() == "0"
    assert page.alert_count_label.text() == "1"
    assert page.card_count == 1
    assert "Breno Barbosa" in page.cards_text()
    assert "Capacete" in page.cards_text()
    assert "AUSENTE" in page.cards_text()

    page.set_connection_status("Tempo real indisponível.", state="offline")
    assert page.card_count == 1
    assert "indisponível" in page.connection_status.text()

    page.search_input.setText("outra operação")
    assert page.visible_card_count == 0
    page.search_input.clear()
    assert page.visible_card_count == 1

    page.apply_update(_snapshot(status=WorkSessionLiveStatus.ENDED))
    assert page.card_count == 0
    assert "Nenhuma operação ativa" in page.empty_state.text()
    page.close()
