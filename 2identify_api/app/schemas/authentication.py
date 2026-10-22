"""Credential-authentication HTTP contracts."""

from __future__ import annotations

from math import isfinite, sqrt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class CredentialLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=1_024)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("username não pode ser vazio")
        return normalized


FaceProbe = Annotated[tuple[float, ...], Field(min_length=128, max_length=128)]


class FaceLoginRequest(BaseModel):
    """Embeddings of successive live frames; the API decides who they belong to."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=80)
    probes: tuple[FaceProbe, ...] = Field(min_length=2, max_length=10, repr=False)

    @field_validator("probes")
    @classmethod
    def normalized(cls, probes: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
        for probe in probes:
            if not all(isfinite(value) for value in probe):
                raise ValueError("embedding inválido")
            if not 0.99 <= sqrt(sum(value * value for value in probe)) <= 1.01:
                raise ValueError("embedding deve estar normalizado")
        return probes


class OperatorPayload(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=150)
    profile: str = Field(min_length=1, max_length=50)
    profile_photo_reference: str | None = None


class CredentialLoginResponse(BaseModel):
    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    operator: OperatorPayload


class AdministratorPayload(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=1, max_length=100)
    profile: Literal["administrador"]


class AdminCredentialLoginResponse(BaseModel):
    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    administrator: AdministratorPayload
