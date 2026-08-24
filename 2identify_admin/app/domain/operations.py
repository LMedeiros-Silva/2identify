"""Desktop domain contracts for operation and risk-area administration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        x, y = float(self.x), float(self.y)
        if not isfinite(x) or not isfinite(y) or not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("coordenadas normalizadas devem estar entre 0.0 e 1.0")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)


@dataclass(frozen=True, slots=True)
class PolygonGeometry:
    points: tuple[NormalizedPoint, ...]

    def __post_init__(self) -> None:
        points = tuple(self.points)
        if len(points) >= 2 and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 3:
            raise ValueError("a área de risco exige no mínimo três pontos")
        if len(set(points)) != len(points):
            raise ValueError("a área de risco não pode repetir pontos")
        if abs(_area(points)) <= _EPSILON:
            raise ValueError("a área de risco não pode ter área zero")
        if _self_intersects(points):
            raise ValueError("a área de risco não pode possuir linhas cruzadas")
        object.__setattr__(self, "points", points)

    def to_payload(self) -> dict[str, object]:
        return {"type": "polygon", "points": [[point.x, point.y] for point in self.points]}


@dataclass(frozen=True, slots=True)
class PpeOption:
    id: int
    name: str
    code: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CameraOption:
    id: int
    name: str
    stream_source: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class SectorOption:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class CameraDraft:
    name: str
    description: str | None
    stream_source: str
    sector_id: int
    active: bool = True

    def __post_init__(self) -> None:
        name = self.name.strip()
        source = self.stream_source.strip()
        description = self.description.strip() or None if self.description is not None else None
        if not name:
            raise ValueError("informe o nome da câmera")
        if not source:
            raise ValueError("informe a fonte da câmera")
        if self.sector_id <= 0:
            raise ValueError("selecione o setor da câmera")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "stream_source", source)
        object.__setattr__(self, "description", description)


@dataclass(frozen=True, slots=True)
class OperationCatalog:
    cameras: tuple[CameraOption, ...]
    epis: tuple[PpeOption, ...]
    sectors: tuple[SectorOption, ...] = ()


@dataclass(frozen=True, slots=True)
class RiskArea:
    id: int
    camera_id: int
    camera_name: str
    name: str
    geometry: PolygonGeometry
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RiskAreaDraft:
    camera_id: int
    name: str
    geometry: PolygonGeometry
    active: bool = True


@dataclass(frozen=True, slots=True)
class OperationConfiguration:
    id: int
    name: str
    description: str | None
    required_ppe: tuple[PpeOption, ...]
    risk_area: RiskArea
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationDraft:
    name: str
    description: str | None
    epi_ids: tuple[int, ...]
    risk_area_id: int
    active: bool = True


def _area(points: tuple[NormalizedPoint, ...]) -> float:
    return sum(
        point.x * points[(index + 1) % len(points)].y
        - points[(index + 1) % len(points)].x * point.y
        for index, point in enumerate(points)
    )


def _self_intersects(points: tuple[NormalizedPoint, ...]) -> bool:
    edges = tuple(
        (points[index], points[(index + 1) % len(points)]) for index in range(len(points))
    )
    for first_index, first in enumerate(edges):
        for second_index in range(first_index + 1, len(edges)):
            if second_index == first_index + 1 or (
                first_index == 0 and second_index == len(edges) - 1
            ):
                continue
            if _intersects(*first, *edges[second_index]):
                return True
    return False


def _intersects(
    a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint, d: NormalizedPoint
) -> bool:
    values = (
        _orientation(a, b, c),
        _orientation(a, b, d),
        _orientation(c, d, a),
        _orientation(c, d, b),
    )
    return (values[0] * values[1] < -_EPSILON and values[2] * values[3] < -_EPSILON) or any(
        abs(value) <= _EPSILON and _within(point, start, end)
        for value, point, start, end in (
            (values[0], c, a, b),
            (values[1], d, a, b),
            (values[2], a, c, d),
            (values[3], b, c, d),
        )
    )


def _orientation(a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _within(point: NormalizedPoint, start: NormalizedPoint, end: NormalizedPoint) -> bool:
    return (
        min(start.x, end.x) - _EPSILON <= point.x <= max(start.x, end.x) + _EPSILON
        and min(start.y, end.y) - _EPSILON <= point.y <= max(start.y, end.y) + _EPSILON
    )


__all__ = [
    "CameraOption",
    "CameraDraft",
    "NormalizedPoint",
    "OperationCatalog",
    "OperationConfiguration",
    "OperationDraft",
    "PolygonGeometry",
    "PpeOption",
    "RiskArea",
    "RiskAreaDraft",
    "SectorOption",
]
