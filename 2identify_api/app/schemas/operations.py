"""Validated contracts for operation and normalized risk-area configuration."""

from __future__ import annotations

from datetime import datetime
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

_EPSILON = 1e-9
NormalizedPoint = tuple[float, float]


class PolygonGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="polygon", pattern="^polygon$")
    points: tuple[NormalizedPoint, ...] = Field(min_length=3, max_length=100)

    @field_validator("points")
    @classmethod
    def validate_polygon(cls, points: tuple[NormalizedPoint, ...]) -> tuple[NormalizedPoint, ...]:
        normalized = tuple((float(x), float(y)) for x, y in points)
        if normalized[0] == normalized[-1]:
            normalized = normalized[:-1]
        if len(normalized) < 3:
            raise ValueError("o polígono exige no mínimo três pontos")
        if any(
            not isfinite(value) or not 0.0 <= value <= 1.0
            for point in normalized
            for value in point
        ):
            raise ValueError("as coordenadas devem ser finitas e estar entre 0.0 e 1.0")
        if len(set(normalized)) != len(normalized):
            raise ValueError("o polígono não pode repetir pontos")
        if abs(_signed_double_area(normalized)) <= _EPSILON:
            raise ValueError("o polígono não pode ter área zero")
        if _has_self_intersection(normalized):
            raise ValueError("o polígono não pode possuir linhas cruzadas")
        return normalized


class EpiReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    code: str | None = None
    description: str | None = None


class CameraCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    description: str | None = None
    stream_source: str


class SectorCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str


class OperationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cameras: tuple[CameraCatalogItem, ...]
    epis: tuple[EpiReference, ...]
    sectors: tuple[SectorCatalogItem, ...]


class CameraWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    stream_source: str = Field(min_length=1, max_length=500)
    sector_id: PositiveInt
    active: bool = True

    @field_validator("name", "stream_source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("o valor não pode ser vazio")
        return value

    @field_validator("description")
    @classmethod
    def normalize_camera_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class RiskAreaWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: PositiveInt
    name: str = Field(min_length=1, max_length=120)
    geometry: PolygonGeometry
    active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("o nome da área não pode ser vazio")
        return value


class RiskAreaDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    camera_id: PositiveInt
    camera_name: str
    name: str
    geometry: PolygonGeometry
    active: bool
    created_at: datetime
    updated_at: datetime


class OperationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    epi_ids: tuple[PositiveInt, ...] = Field(min_length=1, max_length=100)
    risk_area_id: PositiveInt
    active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_operation_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("o nome da operação não pode ser vazio")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("epi_ids")
    @classmethod
    def unique_epis(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("a lista de EPIs não pode conter itens duplicados")
        return value


class OperationDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    description: str | None
    required_ppe: tuple[EpiReference, ...]
    risk_area: RiskAreaDetail
    active: bool
    created_at: datetime
    updated_at: datetime


def _signed_double_area(points: tuple[NormalizedPoint, ...]) -> float:
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _has_self_intersection(points: tuple[NormalizedPoint, ...]) -> bool:
    edges = tuple(
        (points[index], points[(index + 1) % len(points)]) for index in range(len(points))
    )
    for first_index, first in enumerate(edges):
        for second_index in range(first_index + 1, len(edges)):
            if second_index == first_index + 1 or (
                first_index == 0 and second_index == len(edges) - 1
            ):
                continue
            if _segments_intersect(*first, *edges[second_index]):
                return True
    return False


def _segments_intersect(
    a: NormalizedPoint,
    b: NormalizedPoint,
    c: NormalizedPoint,
    d: NormalizedPoint,
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
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _within(point: NormalizedPoint, start: NormalizedPoint, end: NormalizedPoint) -> bool:
    return (
        min(start[0], end[0]) - _EPSILON <= point[0] <= max(start[0], end[0]) + _EPSILON
        and min(start[1], end[1]) - _EPSILON <= point[1] <= max(start[1], end[1]) + _EPSILON
    )


__all__ = [
    "CameraCatalogItem",
    "CameraWrite",
    "EpiReference",
    "OperationCatalog",
    "OperationDetail",
    "OperationWrite",
    "PolygonGeometry",
    "RiskAreaDetail",
    "RiskAreaWrite",
    "SectorCatalogItem",
]
