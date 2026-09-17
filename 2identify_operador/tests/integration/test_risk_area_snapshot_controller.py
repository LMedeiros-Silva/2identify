import numpy as np
from PySide6.QtWidgets import QLabel

from app.controllers.risk_area_snapshot_controller import RiskAreaSnapshotController
from app.core.config import AppSettings
from app.domain import NormalizedPoint, Operation, RiskAreaGeometry, RiskAreaReference
from app.ui.components import CameraFrameView
from app.ui.operations import OperationsPage
from app.workers.safety_camera_worker import SafetyCameraWorker


class CameraStub:
    def __init__(self, *, opens: bool = True) -> None:
        self.opens = opens
        self.closed = False
        self.frame = np.zeros((120, 160, 3), dtype=np.uint8)

    def open(self) -> bool:
        return self.opens

    def read(self):
        return True, self.frame.copy()

    def close(self) -> None:
        self.closed = True


def _configured_page(qtbot) -> tuple[OperationsPage, RiskAreaReference]:
    risk_area = RiskAreaReference(
        31,
        "Linha de Produção A",
        RiskAreaGeometry(
            (
                NormalizedPoint(0.1, 0.6),
                NormalizedPoint(0.4, 0.3),
                NormalizedPoint(0.9, 0.7),
            )
        ),
        geometry_calibrated=True,
        camera_id=3,
        camera_name="Webcam USB",
    )
    operation = Operation(8, "Inspeção industrial", risk_area=risk_area)
    page = OperationsPage()
    qtbot.addWidget(page)
    page.set_operations((operation,))
    page.show_operation_details(operation)
    page.show_risk_area(risk_area)
    return page, risk_area


def _controller(
    page: OperationsPage,
    camera: CameraStub,
) -> RiskAreaSnapshotController:
    return RiskAreaSnapshotController(
        settings=AppSettings(_env_file=None),
        page=page,
        worker_factory=lambda: SafetyCameraWorker(
            camera_factory=lambda: camera,
            preview_fps=30,
            maximum_failed_reads=3,
        ),
    )


def test_risk_area_snapshot_controller_freezes_frame_below_polygon(qtbot) -> None:
    page, risk_area = _configured_page(qtbot)
    camera = CameraStub()
    controller = _controller(page, camera)

    controller.capture(risk_area)

    preview = page.findChild(CameraFrameView, "operationRiskAreaPreview")
    qtbot.waitUntil(
        lambda: preview.has_frame and camera.closed and not controller.is_running,
        timeout=2_000,
    )
    assert preview.risk_zone_labels == ("Linha de Produção A",)
    assert "Webcam USB" in page.findChild(QLabel, "operationRiskAreaNotice").text()


def test_risk_area_snapshot_controller_keeps_polygon_when_camera_is_unavailable(
    qtbot,
) -> None:
    page, risk_area = _configured_page(qtbot)
    camera = CameraStub(opens=False)
    controller = _controller(page, camera)

    controller.capture(risk_area)

    notice = page.findChild(QLabel, "operationRiskAreaNotice")
    qtbot.waitUntil(
        lambda: (
            "Não foi possível acessar" in notice.text()
            and camera.closed
            and not controller.is_running
        ),
        timeout=2_000,
    )
    preview = page.findChild(CameraFrameView, "operationRiskAreaPreview")
    assert not preview.has_frame
    assert preview.risk_zone_count == 1


def test_risk_snapshot_uses_its_camera_specific_local_source(monkeypatch, qtbot) -> None:
    page, risk_area = _configured_page(qtbot)
    monkeypatch.setattr(
        "app.controllers.risk_area_snapshot_controller.local_camera_source",
        lambda camera_id: "1" if camera_id == 3 else None,
    )
    controller = RiskAreaSnapshotController(AppSettings(_env_file=None, camera_source="0"), page)
    worker = controller._new_worker(risk_area)
    assert worker._camera_factory.keywords["source"] == 1
    worker.deleteLater()


def test_risk_snapshot_refuses_global_source_when_camera_mapping_missing(
    monkeypatch, qtbot
) -> None:
    page, risk_area = _configured_page(qtbot)
    monkeypatch.setattr(
        "app.controllers.risk_area_snapshot_controller.local_camera_source",
        lambda _camera_id: None,
    )
    controller = RiskAreaSnapshotController(AppSettings(_env_file=None, camera_source="0"), page)
    controller.capture(risk_area)
    assert not controller.is_running
    assert "não configurada" in page.findChild(QLabel, "operationRiskAreaNotice").text()
