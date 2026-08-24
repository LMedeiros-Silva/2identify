import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from app.ui.components import (
    CameraFrameOverlay,
    CameraFrameView,
    CameraOverlayBox,
    CameraPoseKeypoint,
    CameraPoseOverlay,
    CameraPoseSkeleton,
    CameraRiskZone,
)


def _overlay() -> CameraFrameOverlay:
    return CameraFrameOverlay(
        boxes=(
            CameraOverlayBox(
                label="capacete_seguranca",
                confidence=0.91,
                x1=40,
                y1=30,
                x2=160,
                y2=180,
            ),
        ),
        source_width=320,
        source_height=240,
    )


def _pose_overlay() -> CameraPoseOverlay:
    return CameraPoseOverlay(
        skeletons=(
            CameraPoseSkeleton(
                confidence=0.94,
                keypoints=tuple(
                    CameraPoseKeypoint(
                        x=50.0 + index * 10.0,
                        y=25.0 + (index % 5) * 35.0,
                        confidence=0.95,
                    )
                    for index in range(17)
                ),
            ),
        ),
        source_width=320,
        source_height=240,
        minimum_keypoint_confidence=0.50,
    )


def test_camera_frame_view_paints_detection_overlay(qtbot) -> None:
    view = CameraFrameView("testCameraFrame")
    qtbot.addWidget(view)
    view.resize(320, 240)
    view.show()
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(QColor("#10243e"))
    view.set_frame(frame)

    view.set_overlay(_overlay(), maximum_age_ms=1_000)
    rendered = view.grab().toImage()

    assert view.has_frame
    assert view.has_overlay
    assert view.overlay_box_count == 1
    blue_pixels = 0
    for y in range(rendered.height()):
        for x in range(rendered.width()):
            color = rendered.pixelColor(x, y)
            if color.blue() > 210 and color.green() > 130 and color.red() < 110:
                blue_pixels += 1
    assert blue_pixels > 100


def test_camera_frame_view_expires_and_clears_stale_boxes(qtbot) -> None:
    view = CameraFrameView("testCameraFrame")
    qtbot.addWidget(view)
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(QColor("#10243e"))
    view.set_frame(frame)
    view.set_overlay(_overlay(), maximum_age_ms=30)

    qtbot.waitUntil(lambda: not view.has_overlay, timeout=500)

    view.set_overlay(_overlay(), maximum_age_ms=1_000)
    view.clear_frame()
    assert not view.has_frame
    assert not view.has_overlay


def test_camera_frame_view_keeps_persistent_normalized_risk_zone(qtbot) -> None:
    view = CameraFrameView("testCameraFrame")
    qtbot.addWidget(view)
    view.resize(320, 240)
    view.show()
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(QColor("#10243e"))
    view.set_frame(frame)
    zone = CameraRiskZone(
        "Linha A",
        ((0.1, 0.6), (0.4, 0.3), (0.9, 0.7), (0.8, 0.95)),
    )

    view.set_risk_zones((zone,))
    view.set_overlay(_overlay(), maximum_age_ms=30)
    qtbot.waitUntil(lambda: not view.has_overlay, timeout=500)
    rendered = view.grab().toImage()
    orange_pixels = 0
    for y in range(rendered.height()):
        for x in range(rendered.width()):
            color = rendered.pixelColor(x, y)
            if color.red() > 210 and color.green() > 100 and color.blue() < 120:
                orange_pixels += 1

    assert view.risk_zone_count == 1
    assert view.risk_zone_labels == ("Linha A",)
    assert orange_pixels > 50
    view.clear_frame()
    assert view.risk_zone_count == 1
    view.clear_risk_zones()
    assert view.risk_zone_count == 0


def test_camera_frame_view_paints_and_expires_pose_skeleton(qtbot) -> None:
    view = CameraFrameView("testCameraFrame")
    qtbot.addWidget(view)
    view.resize(320, 240)
    view.show()
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(QColor("#10243e"))
    view.set_frame(frame)

    view.set_pose_overlay(_pose_overlay(), maximum_age_ms=1_000)
    rendered = view.grab().toImage()
    cyan_pixels = 0
    for y in range(rendered.height()):
        for x in range(rendered.width()):
            color = rendered.pixelColor(x, y)
            if color.blue() > 190 and color.green() > 150 and color.red() < 100:
                cyan_pixels += 1

    assert view.pose_skeleton_count == 1
    assert cyan_pixels > 100

    view.clear_pose_overlay()
    assert view.pose_skeleton_count == 0


def test_camera_frame_view_copies_complete_presentation_to_mirror(qtbot) -> None:
    source = CameraFrameView("sourceCameraFrame")
    target = CameraFrameView("targetCameraFrame")
    qtbot.addWidget(source)
    qtbot.addWidget(target)
    frame = QImage(320, 240, QImage.Format.Format_RGB32)
    frame.fill(QColor("#10243e"))
    zone = CameraRiskZone(
        "Linha A",
        ((0.1, 0.6), (0.4, 0.3), (0.9, 0.7)),
    )
    source.set_frame(frame)
    source.set_risk_zones((zone,))
    source.set_overlay(_overlay(), maximum_age_ms=1_000)
    source.set_pose_overlay(_pose_overlay(), maximum_age_ms=1_000)

    source.copy_presentation_to(target)

    assert target.has_frame
    assert target.overlay_labels == ("capacete seguranca",)
    assert target.pose_skeleton_count == 1
    assert target.risk_zone_labels == ("Linha A",)


def test_camera_frame_view_can_letterbox_the_complete_camera_image(qtbot) -> None:
    view = CameraFrameView(
        "containedCameraFrame",
        aspect_ratio_mode=Qt.AspectRatioMode.KeepAspectRatio,
    )
    qtbot.addWidget(view)
    view.resize(400, 400)
    view.show()
    frame = QImage(400, 200, QImage.Format.Format_RGB32)
    frame.fill(QColor("#44aa66"))
    view.set_frame(frame)

    rendered = view.grab().toImage()
    letterbox = rendered.pixelColor(200, 20)
    image_center = rendered.pixelColor(200, 200)

    assert view.aspect_ratio_mode == Qt.AspectRatioMode.KeepAspectRatio
    assert letterbox.blue() > letterbox.green()
    assert image_center.green() > image_center.red()
    assert image_center.green() > image_center.blue()


@pytest.mark.parametrize(
    "box",
    [
        CameraOverlayBox("capacete", 0.9, 0, 0, 10, 10),
        CameraOverlayBox("luva", 0.8, 2, 3, 12, 14),
    ],
)
def test_camera_overlay_contract_preserves_valid_boxes(box) -> None:
    overlay = CameraFrameOverlay((box,), 100, 80)

    assert overlay.boxes == (box,)


def test_camera_overlay_contract_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        CameraOverlayBox("", 0.9, 0, 0, 10, 10)
    with pytest.raises(ValueError):
        CameraOverlayBox("capacete", 1.1, 0, 0, 10, 10)
    with pytest.raises(ValueError):
        CameraOverlayBox("capacete", 0.9, 10, 0, 5, 10)
    with pytest.raises(ValueError):
        CameraFrameOverlay((), 0, 80)
    with pytest.raises(ValueError):
        CameraPoseOverlay((), 320, 0, 0.5)
    with pytest.raises(ValueError):
        CameraPoseSkeleton(0.9, ())
