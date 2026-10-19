"""Phase 4 monitoring layout: camera grid, expansion and safety panel states."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtWidgets import QFrame, QLabel

from app.domain.alert import SafetyAlertSeverity, SafetyViolation, SafetyViolationType
from app.domain.camera_source import CameraStatus
from app.engine import (
    AlertEngine,
    PpeSafetyEngine,
    PpeStabilityDecision,
    PpeStabilitySnapshot,
    PpeStabilityState,
)
from app.ui.active import ActiveOperationPage
from app.ui.main import MainWindow
from tests.ui.test_multicamera_pages import _cameras, _operation, _operator, _work_session


def _page(qtbot, count: int) -> ActiveOperationPage:
    page = ActiveOperationPage(_operator())
    qtbot.addWidget(page)
    page.resize(1366, 700)
    page.set_work_session(_work_session(tuple(range(1, count + 1))), _operation())
    page.set_cameras(_cameras(count))
    page.activate_monitoring()
    return page


def _alerts(page: ActiveOperationPage, *violations: SafetyViolation) -> None:
    engine = AlertEngine(
        minimum_consecutive_observations=1,
        minimum_persistence_seconds=0,
        resolution_consecutive_observations=1,
        cooldown_seconds=30,
    )
    page.update_local_alerts(
        engine.observe(page.work_session, violations, datetime.now(UTC))
    )


def _overall(page: ActiveOperationPage) -> str:
    return page.findChild(QLabel, "activeOverallState").text()


def test_tiles_keep_video_proportion_and_five_cameras_scroll(qtbot) -> None:
    page = _page(qtbot, 5)
    page.show()
    qtbot.waitExposed(page)
    tiles = [page._tile_containers[camera_id] for camera_id in range(1, 6)]
    heights = {tile.height() for tile in tiles}
    assert len(heights) == 1
    tile = tiles[0]
    video_height = tile.height() - 38 - 30
    assert abs(video_height / tile.width() - 9 / 16) < 0.05
    scroll = page._camera_grid_scroll
    assert page._camera_grid_host.minimumSizeHint().height() > scroll.viewport().height()
    page.clear()


def test_single_camera_uses_whole_area_and_offline_tile_explains_state(qtbot) -> None:
    page = _page(qtbot, 1)
    page.show()
    qtbot.waitExposed(page)
    tile = page._tile_containers[1]
    assert tile.height() >= page._camera_grid_scroll.height() - 4
    page.set_camera_tile_status(1, CameraStatus.OFFLINE)
    assert "offline" in page._tile_placeholders[1].text()
    assert page.findChild(QLabel, "activeCameraTileStatus_1").text() == "OFFLINE"
    page.clear()


def test_expanding_one_camera_hides_the_others_and_returns_to_grid(qtbot) -> None:
    page = _page(qtbot, 5)
    page.focus_camera(3)
    assert page.focused_camera_id == 3
    assert page._camera_grid.count() == 1
    assert all(page._tile_containers[i].isHidden() for i in (1, 2, 4, 5))
    assert not page._camera_back_button.isHidden()
    page.focus_camera(None)
    assert page._camera_grid.count() == 5
    assert page._camera_back_button.isHidden()
    page.clear()


def test_overall_state_follows_real_assessment_and_alerts(qtbot) -> None:
    page = _page(qtbot, 1)
    assert _overall(page) == "AGUARDANDO EVIDÊNCIA"
    snapshot = PpeStabilitySnapshot(
        decisions=(
            PpeStabilityDecision("capacete", PpeStabilityState.CONFIRMED_PRESENT, 4, 4, 1.0),
        ),
        sample_count=4,
        window_size=4,
    )
    page.update_monitoring_assessment(
        PpeSafetyEngine().evaluate(_operation(), ("capacete",), snapshot)
    )
    assert _overall(page) == "SEGURO"

    _alerts(
        page,
        SafetyViolation(
            SafetyViolationType.MONITORING_INTERRUPTED,
            "ppe_inconclusive:1",
            "Monitoramento de EPI inconclusivo: Capacete",
            SafetyAlertSeverity.WARNING,
            ppe_id=1,
            ppe_name="Capacete",
            escalate=False,
        ),
    )
    assert _overall(page) == "INCONCLUSIVO"
    assert not page._ppe_alert_labels[1].isHidden()

    _alerts(
        page,
        SafetyViolation(
            SafetyViolationType.FALL_DETECTED,
            "fall:1",
            "Queda detectada",
            SafetyAlertSeverity.CRITICAL,
            camera_id=1,
            escalate=False,
        ),
    )
    assert _overall(page) == "CRÍTICO"
    assert page.findChild(QLabel, "activeFallStatus").text() == "QUEDA DETECTADA"
    # EPI conformity is worded as EPI-only and never reads as an all-clear.
    assert page.findChild(QLabel, "activeMonitoringStatus").text() == "EPIs CONFIRMADOS"
    note = page.findChild(QLabel, "activePpeScopeNote")
    assert not note.isHidden()
    assert "CRÍTICO" in note.text()
    page.clear()


def test_critical_alert_leads_the_active_risks_with_type_and_reason(qtbot) -> None:
    page = _page(qtbot, 1)
    _alerts(
        page,
        SafetyViolation(
            SafetyViolationType.MONITORING_INTERRUPTED,
            "ppe_inconclusive:1",
            "Monitoramento de EPI inconclusivo: Capacete",
            SafetyAlertSeverity.WARNING,
            ppe_id=1,
            ppe_name="Capacete",
            escalate=False,
        ),
        SafetyViolation(
            SafetyViolationType.FALL_DETECTED,
            "fall:1",
            "Queda detectada",
            SafetyAlertSeverity.CRITICAL,
            camera_id=1,
            escalate=False,
        ),
    )
    rows = page.findChildren(QFrame, "activeAlertRow")
    assert [row.property("state") for row in rows] == ["critical", "warning"]
    assert rows[0].findChild(QLabel, "activeAlertType").text() == "QUEDA"
    assert rows[0].findChild(QLabel, "activeAlertRowText").text() == "Queda detectada"
    assert rows[1].findChild(QLabel, "activeAlertType").text() == "EPI INCONCLUSIVO"
    assert rows[1].findChild(QLabel, "activeAlertSeverity").text() == "ATENÇÃO"
    assert page._alert_strip.property("state") == "critical"
    page.clear()


def test_grid_fills_height_with_legible_tiles() -> None:
    # 1920x1080 viewport: two large columns fill the height, the 5th camera scrolls.
    columns, width = ActiveOperationPage._grid_geometry(5, 1370, 920)
    assert columns == 2
    rows_height = 2 * (int(width * 9 / 16) + 68) + 10
    assert 880 <= rows_height <= 920
    # 1366x768 viewport: still two columns and never below the legible minimum.
    columns, width = ActiveOperationPage._grid_geometry(5, 890, 600)
    assert columns == 2 and width >= 400
    # Too small for a legible fit: falls back to full-width columns and scrolls.
    columns, width = ActiveOperationPage._grid_geometry(5, 700, 300)
    assert columns == 2 and width == 345


def test_fall_card_reports_disabled_installation(qtbot) -> None:
    page = _page(qtbot, 1)
    page.configure_fall_detection(enabled=False)
    page.show_ergonomics_ready()
    assert page.findChild(QLabel, "activeFallStatus").text() == "DESATIVADA"
    page.configure_fall_detection(enabled=True)
    assert page.findChild(QLabel, "activeFallStatus").text() == "MONITORANDO"
    page.clear()


def test_monitoring_collapses_shell_and_restores_it(qtbot) -> None:
    from datetime import timedelta

    from app.core.session import AuthenticationMethod, OperatorSession

    session = OperatorSession(
        15, "Operador", datetime.now(UTC) - timedelta(hours=1), AuthenticationMethod.CREDENTIALS
    )
    window = MainWindow(session=session, app_version="0.1.0")
    qtbot.addWidget(window)
    window.show_active_operation(_work_session((1, 2)), _operation(), _cameras(2))
    assert window._sidebar.is_compact
    assert window._header.isHidden()
    window.close_active_operation()
    assert not window._sidebar.is_compact
    assert not window._header.isHidden()
