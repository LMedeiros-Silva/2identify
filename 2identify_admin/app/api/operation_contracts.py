"""Strict HTTP DTOs for operation configuration responses."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PositiveInt

from app.domain import (
    CameraOption,
    NormalizedPoint,
    OperationCatalog,
    OperationConfiguration,
    PolygonGeometry,
    PpeOption,
    RiskArea,
    SectorOption,
)


class _PpeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PositiveInt
    name: str
    code: str | None = None
    description: str | None = None

    def to_domain(self) -> PpeOption:
        return PpeOption(self.id, self.name, self.code, self.description)


class _CameraDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PositiveInt
    name: str
    description: str | None = None
    stream_source: str = Field(min_length=1)

    def to_domain(self) -> CameraOption:
        return CameraOption(self.id, self.name, self.stream_source, self.description)


class _SectorDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PositiveInt
    name: str = Field(min_length=1)

    def to_domain(self) -> SectorOption:
        return SectorOption(self.id, self.name)


class _CatalogDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cameras: tuple[_CameraDto, ...]
    epis: tuple[_PpeDto, ...]
    sectors: tuple[_SectorDto, ...] = ()

    def to_domain(self) -> OperationCatalog:
        return OperationCatalog(
            cameras=tuple(item.to_domain() for item in self.cameras),
            epis=tuple(item.to_domain() for item in self.epis),
            sectors=tuple(item.to_domain() for item in self.sectors),
        )


class _GeometryDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    points: tuple[tuple[float, float], ...]

    def to_domain(self) -> PolygonGeometry:
        if self.type != "polygon":
            raise ValueError("tipo de geometria inválido")
        return PolygonGeometry(tuple(NormalizedPoint(x, y) for x, y in self.points))


class _RiskAreaDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PositiveInt
    camera_id: PositiveInt
    camera_name: str
    name: str
    geometry: _GeometryDto
    active: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def to_domain(self) -> RiskArea:
        return RiskArea(
            self.id,
            self.camera_id,
            self.camera_name,
            self.name,
            self.geometry.to_domain(),
            self.active,
            self.created_at,
            self.updated_at,
        )


class _OperationDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PositiveInt
    name: str
    description: str | None
    required_ppe: tuple[_PpeDto, ...]
    risk_area: _RiskAreaDto
    active: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def to_domain(self) -> OperationConfiguration:
        return OperationConfiguration(
            self.id,
            self.name,
            self.description,
            tuple(item.to_domain() for item in self.required_ppe),
            self.risk_area.to_domain(),
            self.active,
            self.created_at,
            self.updated_at,
        )


def parse_catalog(payload: object) -> OperationCatalog:
    return _CatalogDto.model_validate(payload).to_domain()


def parse_camera(payload: object) -> CameraOption:
    return _CameraDto.model_validate(payload).to_domain()


def parse_risk_area(payload: object) -> RiskArea:
    return _RiskAreaDto.model_validate(payload).to_domain()


def parse_risk_areas(payload: object) -> tuple[RiskArea, ...]:
    return tuple(_RiskAreaDto.model_validate(item).to_domain() for item in _as_list(payload))


def parse_operation(payload: object) -> OperationConfiguration:
    return _OperationDto.model_validate(payload).to_domain()


def parse_operations(payload: object) -> tuple[OperationConfiguration, ...]:
    return tuple(_OperationDto.model_validate(item).to_domain() for item in _as_list(payload))


def _as_list(payload: object) -> list[object]:
    if not isinstance(payload, list):
        raise ValueError("lista esperada")
    return payload


__all__ = [
    "parse_catalog",
    "parse_camera",
    "parse_operation",
    "parse_operations",
    "parse_risk_area",
    "parse_risk_areas",
]
