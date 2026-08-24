"""Spatial decisions for normalized risk-area geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain import (
    NormalizedPoint,
    RiskAreaGeometry,
    SafetyAlertSeverity,
    SafetyViolation,
    SafetyViolationType,
)
from app.vision.pose import PoseDetectionBatch

_BOUNDARY_EPSILON = 1e-9


class RiskAreaPointRelation(StrEnum):
    """Relation between one normalized point and a configured risk polygon."""

    OUTSIDE = "outside"
    BOUNDARY = "boundary"
    INSIDE = "inside"


class RiskAreaSpatialEngine:
    """Classify normalized points without depending on Qt, OpenCV or a detector."""

    @staticmethod
    def classify_point(
        geometry: RiskAreaGeometry,
        point: NormalizedPoint,
    ) -> RiskAreaPointRelation:
        """Return a deterministic point-in-polygon relation including boundaries."""

        if not isinstance(geometry, RiskAreaGeometry):
            raise ValueError("geometry deve ser uma RiskAreaGeometry")
        if not isinstance(point, NormalizedPoint):
            raise ValueError("point deve ser um NormalizedPoint")

        vertices = geometry.vertices
        inside = False
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if _point_on_segment(point, start, end):
                return RiskAreaPointRelation.BOUNDARY
            crosses_horizontal_ray = (start.y > point.y) != (end.y > point.y)
            if not crosses_horizontal_ray:
                continue
            intersection_x = start.x + (point.y - start.y) * (
                end.x - start.x
            ) / (end.y - start.y)
            if intersection_x > point.x:
                inside = not inside
        return (
            RiskAreaPointRelation.INSIDE
            if inside
            else RiskAreaPointRelation.OUTSIDE
        )

    @classmethod
    def contains_point(
        cls,
        geometry: RiskAreaGeometry,
        point: NormalizedPoint,
        *,
        include_boundary: bool = True,
    ) -> bool:
        """Return membership using an explicit boundary policy."""

        relation = cls.classify_point(geometry, point)
        return relation is RiskAreaPointRelation.INSIDE or (
            include_boundary and relation is RiskAreaPointRelation.BOUNDARY
        )


@dataclass(frozen=True, slots=True)
class RiskAreaAssessment:
    """One frame-level person-presence decision for a configured risk area."""

    violations: tuple[SafetyViolation, ...]
    detected_people: int
    evaluated_people: int
    people_inside: int
    inference_milliseconds: float

    @property
    def is_clear(self) -> bool:
        return self.evaluated_people > 0 and self.people_inside == 0


class RiskAreaPoseEngine:
    """Match reliable human-pose keypoints against normalized risk geometry."""

    def __init__(self, *, keypoint_confidence_threshold: float) -> None:
        if not 0.0 < keypoint_confidence_threshold <= 1.0:
            raise ValueError("keypoint_confidence_threshold deve estar entre 0 e 1")
        self._keypoint_threshold = keypoint_confidence_threshold

    def evaluate(
        self,
        batch: PoseDetectionBatch,
        geometry: RiskAreaGeometry,
        *,
        risk_area_id: int,
        risk_area_name: str,
    ) -> RiskAreaAssessment:
        """Return one stable violation when any visible body point enters the area."""

        if not isinstance(batch, PoseDetectionBatch):
            raise ValueError("batch deve ser PoseDetectionBatch")
        if not isinstance(geometry, RiskAreaGeometry):
            raise ValueError("geometry deve ser uma RiskAreaGeometry")
        if risk_area_id <= 0:
            raise ValueError("risk_area_id deve ser positivo")
        normalized_name = risk_area_name.strip()
        if not normalized_name:
            raise ValueError("risk_area_name não pode ser vazio")

        evaluated_people = 0
        people_inside = 0
        for pose in batch.poses:
            visible_points = tuple(
                NormalizedPoint(
                    keypoint.x / batch.frame_width,
                    keypoint.y / batch.frame_height,
                )
                for keypoint in pose.keypoints
                if keypoint.confidence >= self._keypoint_threshold
                and 0.0 <= keypoint.x <= batch.frame_width
                and 0.0 <= keypoint.y <= batch.frame_height
            )
            if not visible_points:
                continue
            evaluated_people += 1
            if any(
                RiskAreaSpatialEngine.contains_point(geometry, point)
                for point in visible_points
            ):
                people_inside += 1

        violations: tuple[SafetyViolation, ...] = ()
        if people_inside:
            violations = (
                SafetyViolation(
                    violation_type=SafetyViolationType.PERSON_IN_RISK_AREA,
                    subject_key=f"risk_area:{risk_area_id}",
                    summary=(
                        "Pessoa detectada na área de risco: "
                        f"{normalized_name}"
                    ),
                    severity=SafetyAlertSeverity.CRITICAL,
                ),
            )
        return RiskAreaAssessment(
            violations=violations,
            detected_people=len(batch.poses),
            evaluated_people=evaluated_people,
            people_inside=people_inside,
            inference_milliseconds=batch.inference_milliseconds,
        )


def _point_on_segment(
    point: NormalizedPoint,
    start: NormalizedPoint,
    end: NormalizedPoint,
) -> bool:
    cross_product = (end.x - start.x) * (point.y - start.y) - (
        end.y - start.y
    ) * (point.x - start.x)
    if abs(cross_product) > _BOUNDARY_EPSILON:
        return False
    return (
        min(start.x, end.x) - _BOUNDARY_EPSILON
        <= point.x
        <= max(start.x, end.x) + _BOUNDARY_EPSILON
        and min(start.y, end.y) - _BOUNDARY_EPSILON
        <= point.y
        <= max(start.y, end.y) + _BOUNDARY_EPSILON
    )
