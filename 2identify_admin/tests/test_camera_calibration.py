from __future__ import annotations

import os

import cv2
import numpy as np
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog

from app.controllers.operations_controller import OperationsController
from app.core import config
from app.core.session import AdminSessionContext
from app.domain import CameraOption, OperationCatalog
from app.services.admin_operations_service import AdminOperationsService
from app.ui.operations import OperationsPage, RiskAreaEditorDialog

PUBLIC_SOURCE = "rtsp://camera.test:554/cam/realmonitor"
PRIVATE_SOURCE = "rtsp://test:local-secret@camera.test:554/cam/realmonitor?channel=1&subtype=0"


@pytest.fixture
def local_projects(tmp_path, monkeypatch):
    admin = tmp_path / "2identify_admin"
    operator = tmp_path / "2identify_operador"
    admin.mkdir()
    operator.mkdir()
    monkeypatch.setattr(config, "PROJECT_ROOT", admin)
    for key in tuple(os.environ):
        if key.startswith("CAMERA_SOURCE"):
            monkeypatch.delenv(key)
    return admin, operator


def _configure_area(qapp, monkeypatch, camera, accepted_source):
    class CameraCapture:
        released = False

        def set(self, *_args):
            return True

        def open(self, source):
            return source == accepted_source

        def read(self):
            frame = np.full((2, 4, 3), (10, 20, 30), dtype=np.uint8)
            return True, frame

        def release(self):
            self.released = True

    capture = CameraCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda: capture)
    images = []
    original_init = RiskAreaEditorDialog.__init__

    def record_image(dialog, selected_camera, image, *args):
        images.append(image.copy())
        original_init(dialog, selected_camera, image, *args)

    monkeypatch.setattr(RiskAreaEditorDialog, "__init__", record_image)
    monkeypatch.setattr(RiskAreaEditorDialog, "exec", lambda _self: QDialog.Rejected)
    page = OperationsPage()
    page.set_data(OperationCatalog((camera,), ()), (), ())
    controller = OperationsController(
        page,
        AdminOperationsService(object()),
        AdminSessionContext(),
        shutdown_timeout_ms=2_000,
    )
    page.configure_area_button.click()
    worker = controller._camera_worker
    assert worker is not None
    assert worker.wait(2_000)
    qapp.processEvents()
    assert controller.shutdown()
    return images, page.feedback.text(), capture


@pytest.mark.parametrize("location", ["operator", "admin", "environment"])
def test_calibration_opens_private_source_for_selected_camera(
    qapp, monkeypatch, local_projects, location
):
    admin, operator = local_projects
    if location == "environment":
        monkeypatch.setenv("CAMERA_SOURCE_5", PRIVATE_SOURCE)
    else:
        directory = operator if location == "operator" else admin
        (directory / ".env").write_text(f'CAMERA_SOURCE_5="{PRIVATE_SOURCE}"\n')
    camera = CameraOption(5, "Fresa1", PUBLIC_SOURCE)

    images, feedback, capture = _configure_area(qapp, monkeypatch, camera, PRIVATE_SOURCE)

    assert len(images) == 1, feedback
    assert images[0].size().width() == 4
    assert images[0].pixelColor(0, 0).getRgb() == (30, 20, 10, 255)
    assert capture.released
    assert camera.stream_source == PUBLIC_SOURCE


@pytest.mark.parametrize("catalog_source", [PUBLIC_SOURCE, "0"])
def test_calibration_keeps_catalog_fallback_without_matching_local_id(
    qapp, monkeypatch, local_projects, catalog_source
):
    _, operator = local_projects
    (operator / ".env").write_text(f'CAMERA_SOURCE_6="{PRIVATE_SOURCE}"\n')
    monkeypatch.setenv("CAMERA_SOURCE", PRIVATE_SOURCE)
    expected_source = 0 if catalog_source == "0" else PUBLIC_SOURCE

    images, feedback, capture = _configure_area(
        qapp, monkeypatch, CameraOption(5, "Fresa1", catalog_source), expected_source
    )

    assert len(images) == 1, feedback
    assert capture.released


def test_calibration_keeps_local_image_support(qapp, monkeypatch, local_projects):
    admin, _ = local_projects
    image_path = admin / "reference.png"
    image = QImage(4, 2, QImage.Format.Format_RGB32)
    image.fill(0xFF102030)
    assert image.save(str(image_path))

    images, feedback, capture = _configure_area(
        qapp, monkeypatch, CameraOption(5, "Arquivo", str(image_path)), None
    )

    assert len(images) == 1, feedback
    assert images[0].pixelColor(0, 0).getRgb() == (16, 32, 48, 255)
    assert not capture.released


@pytest.mark.parametrize("environment_override", [False, True])
def test_calibration_prefers_explicit_admin_configuration(
    qapp, monkeypatch, local_projects, environment_override
):
    admin, operator = local_projects
    (operator / ".env").write_text('CAMERA_SOURCE_5="rtsp://other.test/live"\n')
    admin_source = "rtsp://admin.test/live" if environment_override else PRIVATE_SOURCE
    (admin / ".env").write_text(f'CAMERA_SOURCE_5="{admin_source}"\n')
    if environment_override:
        monkeypatch.setenv("CAMERA_SOURCE_5", PRIVATE_SOURCE)

    images, feedback, _ = _configure_area(
        qapp, monkeypatch, CameraOption(5, "Fresa1", PUBLIC_SOURCE), PRIVATE_SOURCE
    )

    assert len(images) == 1, feedback


@pytest.mark.parametrize(
    "invalid_source",
    ["file:///local-secret", "rtsp://test:local-secret@camera.test:bad/live", "0"],
)
def test_invalid_private_source_fails_without_fallback_or_secret_in_feedback(
    qapp, monkeypatch, local_projects, caplog, invalid_source
):
    admin, _ = local_projects
    (admin / ".env").write_text(f'CAMERA_SOURCE_5="{invalid_source}"\n')

    images, feedback, capture = _configure_area(
        qapp, monkeypatch, CameraOption(5, "Fresa1", PUBLIC_SOURCE), PUBLIC_SOURCE
    )

    assert images == []
    assert "CAMERA_SOURCE_5" in feedback
    assert "local-secret" not in feedback + caplog.text
    assert not capture.released


def test_calibration_uses_station_specific_usb_index(qapp, monkeypatch, local_projects):
    _, operator = local_projects
    (operator / ".env").write_text("CAMERA_SOURCE_5=2\n")

    images, feedback, capture = _configure_area(
        qapp, monkeypatch, CameraOption(5, "USB", "0"), 2
    )

    assert len(images) == 1, feedback
    assert capture.released
