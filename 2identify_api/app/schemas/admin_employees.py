"""Authenticated employee registration and biometric enrollment contracts."""

from __future__ import annotations

from datetime import datetime
from math import isfinite, sqrt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    registration: str = Field(min_length=1, max_length=50)
    role: str | None = Field(default=None, max_length=100)
    shift: str | None = Field(default=None, max_length=50)
    sector_id: int = Field(gt=0)
    active: bool = True

    @field_validator("name", "registration")
    @classmethod
    def nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campo obrigatório")
        return value


class EmployeeDetail(EmployeeDraft):
    id: int = Field(gt=0)
    sector_name: str
    created_at: datetime
    updated_at: datetime


class EmployeeList(BaseModel):
    items: tuple[EmployeeDetail, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class FaceTemplateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=80)
    embedding: tuple[float, ...] = Field(min_length=128, max_length=128)

    @field_validator("embedding")
    @classmethod
    def normalized(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if not all(isfinite(value) for value in values):
            raise ValueError("embedding inválido")
        norm = sqrt(sum(value * value for value in values))
        if not 0.99 <= norm <= 1.01:
            raise ValueError("embedding deve estar normalizado")
        return values


class FaceTemplateStatus(BaseModel):
    employee_id: int = Field(gt=0)
    model_id: str
    enrolled_at: datetime


__all__ = [
    "EmployeeDraft", "EmployeeDetail", "EmployeeList",
    "FaceTemplateDraft", "FaceTemplateStatus",
]
