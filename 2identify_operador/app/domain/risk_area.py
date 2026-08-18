"""Camera-independent geometry contracts for configured industrial risk areas."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

_GEOMETRY_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    """A point in normalized camera coordinates, independent from resolution."""

    x: float
    y: float

    def __post_init__(self) -> None:
        x = float(self.x)
        y = float(self.y)
        if not isfinite(x) or not isfinite(y):
            raise ValueError("coordenadas normalizadas devem ser finitas")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("coordenadas normalizadas devem estar entre zero e um")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)


@dataclass(frozen=True, slots=True)
class RiskAreaGeometry:
    """A validated simple polygon in normalized camera coordinates."""

    vertices: tuple[NormalizedPoint, ...]

    def __post_init__(self) -> None:
        vertices = tuple(self.vertices)
        if len(vertices) >= 2 and vertices[0] == vertices[-1]:
            vertices = vertices[:-1]
        if len(vertices) < 3:
            raise ValueError("a geometria da área de risco exige ao menos três vértices")
        if any(not isinstance(item, NormalizedPoint) for item in vertices):
            raise ValueError("vertices deve conter somente NormalizedPoint")
        if len(set(vertices)) != len(vertices):
            raise ValueError("a geometria da área de risco não pode repetir vértices")
        if abs(_signed_double_area(vertices)) <= _GEOMETRY_EPSILON:
            raise ValueError("a geometria da área de risco não pode ter área zero")
        if _has_self_intersection(vertices):
            raise ValueError("a geometria da área de risco não pode se cruzar")
        object.__setattr__(self, "vertices", vertices)


def _signed_double_area(vertices: tuple[NormalizedPoint, ...]) -> float:
    return sum(
        current.x * following.y - following.x * current.y
        for current, following in _polygon_edges(vertices)
    )


def _has_self_intersection(vertices: tuple[NormalizedPoint, ...]) -> bool:
    edges = tuple(_polygon_edges(vertices))
    edge_count = len(edges)
    for first_index, first in enumerate(edges):
        for second_index in range(first_index + 1, edge_count):
            if (
                second_index == first_index + 1
                or first_index == 0
                and second_index == edge_count - 1
            ):
                continue
            if _segments_intersect(*first, *edges[second_index]):
                return True
    return False


def _polygon_edges(
    vertices: tuple[NormalizedPoint, ...],
) -> tuple[tuple[NormalizedPoint, NormalizedPoint], ...]:
    return tuple(
        (vertices[index], vertices[(index + 1) % len(vertices)])
        for index in range(len(vertices))
    )


def _segments_intersect(
    first_start: NormalizedPoint,
    first_end: NormalizedPoint,
    second_start: NormalizedPoint,
    second_end: NormalizedPoint,
) -> bool:
    first_orientation = _orientation(first_start, first_end, second_start)
    second_orientation = _orientation(first_start, first_end, second_end)
    third_orientation = _orientation(second_start, second_end, first_start)
    fourth_orientation = _orientation(second_start, second_end, first_end)
    return (
        first_orientation * second_orientation < -_GEOMETRY_EPSILON
        and third_orientation * fourth_orientation < -_GEOMETRY_EPSILON
    ) or any(
        abs(orientation) <= _GEOMETRY_EPSILON
        and _point_within_segment(point, start, end)
        for orientation, point, start, end in (
            (first_orientation, second_start, first_start, first_end),
            (second_orientation, second_end, first_start, first_end),
            (third_orientation, first_start, second_start, second_end),
            (fourth_orientation, first_end, second_start, second_end),
        )
    )


def _orientation(
    start: NormalizedPoint,
    end: NormalizedPoint,
    point: NormalizedPoint,
) -> float:
    return (end.x - start.x) * (point.y - start.y) - (
        end.y - start.y
    ) * (point.x - start.x)


def _point_within_segment(
    point: NormalizedPoint,
    start: NormalizedPoint,
    end: NormalizedPoint,
) -> bool:
    return (
        min(start.x, end.x) - _GEOMETRY_EPSILON
        <= point.x
        <= max(start.x, end.x) + _GEOMETRY_EPSILON
        and min(start.y, end.y) - _GEOMETRY_EPSILON
        <= point.y
        <= max(start.y, end.y) + _GEOMETRY_EPSILON
    )
