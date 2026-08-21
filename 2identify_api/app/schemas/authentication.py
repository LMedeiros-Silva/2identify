"""Credential-authentication HTTP contracts."""

from __future__ import annotations

from typing import Literal

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
