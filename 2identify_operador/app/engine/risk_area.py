"""Spatial decisions for normalized risk-area geometry."""

from __future__ import annotations

from enum import StrEnum

from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry

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
