from app.domain import NormalizedPoint, RiskAreaGeometry, SafetyViolationType
from app.engine import (
    RiskAreaPointRelation,
    RiskAreaPoseEngine,
    RiskAreaSpatialEngine,
)
from app.vision.pose import (
    COCO_KEYPOINT_COUNT,
    PersonPose,
    PoseDetectionBatch,
    PoseKeypoint,
)


def _geometry() -> RiskAreaGeometry:
    return RiskAreaGeometry(
        (
            NormalizedPoint(0.2, 0.2),
            NormalizedPoint(0.8, 0.2),
            NormalizedPoint(0.8, 0.8),
            NormalizedPoint(0.2, 0.8),
        )
    )


def test_spatial_engine_classifies_inside_boundary_and_outside() -> None:
    engine = RiskAreaSpatialEngine()
    geometry = _geometry()

    assert engine.classify_point(geometry, NormalizedPoint(0.5, 0.5)) is (
        RiskAreaPointRelation.INSIDE
    )
    assert engine.classify_point(geometry, NormalizedPoint(0.2, 0.5)) is (
        RiskAreaPointRelation.BOUNDARY
    )
    assert engine.classify_point(geometry, NormalizedPoint(0.1, 0.5)) is (
        RiskAreaPointRelation.OUTSIDE
    )


def test_spatial_engine_has_explicit_boundary_policy() -> None:
    engine = RiskAreaSpatialEngine()
    geometry = _geometry()
    boundary = NormalizedPoint(0.2, 0.5)

    assert engine.contains_point(geometry, boundary)
    assert not engine.contains_point(
        geometry,
        boundary,
        include_boundary=False,
    )


def _pose_batch(*keypoints: PoseKeypoint) -> PoseDetectionBatch:
    pose_keypoints = list(keypoints)
    pose_keypoints.extend(
        PoseKeypoint(0.0, 0.0, 0.0)
        for _ in range(COCO_KEYPOINT_COUNT - len(pose_keypoints))
    )
    return PoseDetectionBatch(
        poses=(PersonPose(0.95, tuple(pose_keypoints)),),
        frame_width=200,
        frame_height=100,
        inference_milliseconds=4.5,
    )


def test_pose_engine_emits_risk_violation_when_body_point_enters_polygon() -> None:
    assessment = RiskAreaPoseEngine(
        keypoint_confidence_threshold=0.5,
    ).evaluate(
        _pose_batch(PoseKeypoint(100.0, 50.0, 0.95)),
        _geometry(),
        risk_area_id=7,
        risk_area_name="Linha A",
    )

    assert assessment.detected_people == 1
    assert assessment.evaluated_people == 1
    assert assessment.people_inside == 1
    assert len(assessment.violations) == 1
    assert assessment.violations[0].violation_type is (
        SafetyViolationType.PERSON_IN_RISK_AREA
    )
    assert assessment.violations[0].subject_key == "risk_area:7"


def test_pose_engine_keeps_area_clear_when_visible_body_is_outside() -> None:
    assessment = RiskAreaPoseEngine(
        keypoint_confidence_threshold=0.5,
    ).evaluate(
        _pose_batch(PoseKeypoint(10.0, 10.0, 0.95)),
        _geometry(),
        risk_area_id=7,
        risk_area_name="Linha A",
    )

    assert assessment.is_clear
    assert assessment.people_inside == 0
    assert assessment.violations == ()


def test_pose_engine_ignores_low_confidence_and_out_of_frame_points() -> None:
    assessment = RiskAreaPoseEngine(
        keypoint_confidence_threshold=0.5,
    ).evaluate(
        _pose_batch(
            PoseKeypoint(100.0, 50.0, 0.49),
            PoseKeypoint(250.0, 50.0, 0.95),
        ),
        _geometry(),
        risk_area_id=7,
        risk_area_name="Linha A",
    )

    assert assessment.detected_people == 1
    assert assessment.evaluated_people == 0
    assert assessment.people_inside == 0
    assert assessment.violations == ()
