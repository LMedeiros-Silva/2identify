"""Employee registration and central Face ID contracts for the Admin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite, sqrt


@dataclass(frozen=True, slots=True)
class EmployeeDraft:
    name: str
    registration: str
    sector_id: int
    role: str | None = None
    shift: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.registration.strip() or self.sector_id <= 0:
            raise ValueError("Nome, matrícula e setor são obrigatórios.")


@dataclass(frozen=True, slots=True)
class EmployeeRecord:
    id: int
    name: str
    registration: str
    sector_id: int
    sector_name: str
    role: str | None
    shift: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EmployeePage:
    items: tuple[EmployeeRecord, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class FaceTemplateDraft:
    model_id: str
    embedding: tuple[float, ...] = field(repr=False)

    def __post_init__(self) -> None:
        norm = sqrt(sum(value * value for value in self.embedding))
        if (
            self.model_id != "opencv_sface_2021dec"
            or len(self.embedding) != 128
            or not all(isfinite(value) for value in self.embedding)
            or not 0.99 <= norm <= 1.01
        ):
            raise ValueError("Template facial incompatível com SFace.")


@dataclass(frozen=True, slots=True)
class FaceTemplateStatus:
    employee_id: int
    model_id: str
    enrolled_at: datetime


__all__ = [
    "EmployeeDraft", "EmployeeRecord", "EmployeePage",
    "FaceTemplateDraft", "FaceTemplateStatus",
]
