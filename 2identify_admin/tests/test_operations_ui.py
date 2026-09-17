from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from app.domain import (
    CameraDraft,
    CameraOption,
    ManagedCamera,
    NormalizedPoint,
    OperationCatalog,
    OperationConfiguration,
    PolygonGeometry,
    PpeOption,
    RiskArea,
    SectorOption,
)
from app.ui.operations import CameraRegistrationDialog, OperationsPage, RiskAreaEditor


def test_editor_normalizes_only_the_real_letterboxed_image(qapp) -> None:
    editor = RiskAreaEditor()
    editor.resize(800, 600)
    editor.set_image(QImage(1600, 900, QImage.Format.Format_RGB32))
    editor.show()
    qapp.processEvents()

    image_rect = editor.image_rect()
    assert image_rect.top() == pytest.approx(75.0)
    assert image_rect.height() == pytest.approx(450.0)
    assert editor.normalized_point_at(QPointF(400, 20)) is None

    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=QPoint(160, 300))
    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=QPoint(640, 300))
    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=QPoint(400, 480))
    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=QPoint(400, 20))

    assert len(editor.points) == 3
    assert editor.points[0].x == pytest.approx(0.2)
    assert editor.points[0].y == pytest.approx(0.5)
    assert editor.close_polygon() is True
    saved = editor.geometry()

    editor.resize(1000, 500)
    qapp.processEvents()
    assert editor.geometry() == saved
    resized_rect = editor.image_rect()
    visual_first = QPointF(
        resized_rect.left() + saved.points[0].x * resized_rect.width(),
        resized_rect.top() + saved.points[0].y * resized_rect.height(),
    )
    normalized_again = editor.normalized_point_at(visual_first)
    assert normalized_again is not None
    assert normalized_again.x == pytest.approx(saved.points[0].x)
    assert normalized_again.y == pytest.approx(saved.points[0].y)


def test_editor_loads_existing_geometry_and_supports_undo_and_clear(qapp) -> None:
    geometry = PolygonGeometry(
        (
            NormalizedPoint(0.1, 0.1),
            NormalizedPoint(0.8, 0.1),
            NormalizedPoint(0.5, 0.8),
        )
    )
    editor = RiskAreaEditor()
    editor.set_image(QImage(640, 480, QImage.Format.Format_RGB32))
    editor.set_geometry(geometry)
    assert editor.is_closed is True
    assert editor.geometry() == geometry
    editor.undo_last_point()
    assert editor.is_closed is False
    assert len(editor.points) == 2
    editor.clear_points()
    assert editor.points == ()


def test_crossing_polygon_is_rejected_in_admin_domain() -> None:
    with pytest.raises(ValueError):
        PolygonGeometry(
            (
                NormalizedPoint(0.1, 0.1),
                NormalizedPoint(0.9, 0.9),
                NormalizedPoint(0.9, 0.1),
                NormalizedPoint(0.1, 0.9),
            )
        )


def test_operations_page_emits_area_edit_and_validated_operation_draft(qapp) -> None:
    now = datetime.now(UTC)
    camera = CameraOption(5, "Linha A", "0")
    ppe = PpeOption(1, "Capacete", "CAP")
    geometry = PolygonGeometry(
        (
            NormalizedPoint(0.1, 0.1),
            NormalizedPoint(0.8, 0.1),
            NormalizedPoint(0.5, 0.8),
        )
    )
    area = RiskArea(10, 5, "Linha A", "Área principal", geometry, True, now, now)
    operation = OperationConfiguration(20, "Soldagem", None, (ppe,), area, True, now, now)
    page = OperationsPage()
    page.set_data(OperationCatalog((camera,), (ppe,)), (area,), (operation,))

    area_requests: list[tuple[object, object]] = []
    drafts: list[tuple[object, object]] = []
    page.risk_area_configuration_requested.connect(
        lambda selected_camera, selected_area: area_requests.append(
            (selected_camera, selected_area)
        )
    )
    page.operation_save_requested.connect(
        lambda draft, operation_id: drafts.append((draft, operation_id))
    )

    page.operation_list.setCurrentRow(0)
    page.configure_area_button.click()
    page.save_button.click()
    qapp.processEvents()

    assert area_requests == [(camera, area)]
    assert drafts[0][0].name == "Soldagem"
    assert drafts[0][0].epi_ids == (1,)
    assert drafts[0][0].risk_area_id == 10
    assert drafts[0][1] == 20


def test_empty_catalog_allows_camera_registration_and_enables_area_after_save(qapp) -> None:
    ppe = PpeOption(1, "Capacete", "CAP")
    sector = SectorOption(1, "Produção")
    page = OperationsPage()
    page.set_data(OperationCatalog((), (ppe,), (sector,)), (), ())

    assert page.create_camera_button.isEnabled() is True
    assert page.configure_area_button.isEnabled() is False
    assert "Nenhuma câmera" in page.feedback.text()

    camera = CameraOption(7, "Webcam USB", "0")
    page.upsert_camera(camera)
    qapp.processEvents()

    assert page.camera_combo.currentData() == 7
    assert page.configure_area_button.isEnabled() is True


def test_camera_registration_dialog_builds_local_camera_draft(qapp) -> None:
    dialog = CameraRegistrationDialog((SectorOption(1, "Produção"),))
    dialog.name_edit.setText("Webcam USB")
    dialog.source_edit.setText("0")
    dialog._validate_and_accept()

    assert dialog.result_draft is not None
    assert dialog.result_draft.name == "Webcam USB"
    assert dialog.result_draft.stream_source == "0"
    assert dialog.result_draft.sector_id == 1


def test_camera_registration_dialog_distinguishes_ip_and_usb(qapp) -> None:
    dialog = CameraRegistrationDialog((SectorOption(1, "Produção"),))
    dialog.name_edit.setText("Fresa IP")
    dialog.source_edit.setText("rtsp://camera.local/live")
    dialog._validate_and_accept()
    assert dialog.result_draft is None
    assert not dialog.feedback.isHidden()

    dialog.type_combo.setCurrentIndex(1)
    dialog._validate_and_accept()
    assert dialog.result_draft is not None
    assert dialog.result_draft.stream_source == "rtsp://camera.local/live"


def test_camera_edit_dialog_prefills_sector_source_and_active_status(qapp) -> None:
    camera = ManagedCamera(7, "Fresa", "rtsp://camera.local/live", None, 2, False)
    dialog = CameraRegistrationDialog(
        (SectorOption(1, "Produção"), SectorOption(2, "Manutenção")), existing=camera
    )
    assert dialog.name_edit.text() == "Fresa"
    assert dialog.source_edit.text() == "rtsp://camera.local/live"
    assert dialog.sector_combo.currentData() == 2
    assert dialog.active_check.isChecked() is False
    dialog.active_check.setChecked(True)
    dialog._validate_and_accept()
    assert dialog.result_draft is not None
    assert dialog.result_draft.active is True


def test_operations_page_lists_inactive_cameras_for_management(qapp) -> None:
    managed = (
        ManagedCamera(7, "Fresa", "rtsp://camera.local/live", None, 1, True),
        ManagedCamera(8, "USB", "0", None, 1, False),
    )
    page = OperationsPage()
    page.set_data(
        OperationCatalog((CameraOption(7, "Fresa", "rtsp://camera.local/live"),), (),
                         (SectorOption(1, "Produção"),)),
        (),
        (),
        managed,
    )
    assert page.managed_camera_combo.count() == 2
    assert "Inativa" in page.managed_camera_combo.itemText(1)
    page.managed_camera_combo.setCurrentIndex(1)
    assert page.edit_camera_button.isEnabled()


def test_operations_page_filters_managed_cameras_by_sector(qapp) -> None:
    managed = (
        ManagedCamera(7, "Fresa", "rtsp://camera.local/live", None, 1, True),
        ManagedCamera(8, "USB", "0", None, 1, False),
        ManagedCamera(9, "SICK", "rtsp://sick.local/live", None, 2, True),
    )
    page = OperationsPage()
    page.set_data(
        OperationCatalog((), (), (
            SectorOption(1, "Produção"), SectorOption(2, "Manutenção")
        )), (), (), managed,
    )
    assert page.managed_camera_combo.count() == 3
    page.camera_sector_filter.setCurrentIndex(page.camera_sector_filter.findData(1))
    assert {page.managed_camera_combo.itemData(index) for index in range(2)} == {7, 8}
    page.camera_sector_filter.setCurrentIndex(page.camera_sector_filter.findData(2))
    assert page.managed_camera_combo.count() == 1
    assert page.managed_camera_combo.currentData() == 9


def test_operations_page_routes_camera_edit_with_selected_id(qapp, monkeypatch) -> None:
    camera = ManagedCamera(8, "USB", "0", None, 1, False)
    page = OperationsPage()
    page.set_data(
        OperationCatalog((), (), (SectorOption(1, "Produção"),)), (), (), (camera,)
    )
    emitted: list[tuple[CameraDraft, int]] = []
    page.camera_update_requested.connect(
        lambda draft, camera_id: emitted.append((draft, camera_id))
    )

    def accept_edit(dialog: CameraRegistrationDialog) -> QDialog.DialogCode:
        dialog.active_check.setChecked(True)
        dialog._validate_and_accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CameraRegistrationDialog, "exec", accept_edit)
    page.edit_camera_button.click()

    assert len(emitted) == 1
    assert emitted[0][1] == 8
    assert emitted[0][0].active is True


def test_saving_operation_keeps_inactive_camera_visible_for_management(qapp) -> None:
    camera = ManagedCamera(8, "USB", "0", None, 1, False)
    page = OperationsPage()
    page.set_data(
        OperationCatalog((), (), (SectorOption(1, "Produção"),)), (), (), (camera,)
    )
    now = datetime.now(UTC)
    area = RiskArea(
        10, 8, "USB", "Área", PolygonGeometry((
            NormalizedPoint(0.1, 0.1), NormalizedPoint(0.8, 0.1), NormalizedPoint(0.5, 0.8)
        )), True, now, now,
    )
    page.upsert_operation(OperationConfiguration(20, "Soldagem", None, (), area, True, now, now))
    assert page.managed_camera_combo.count() == 1
    assert page.managed_camera_combo.currentData() == 8
