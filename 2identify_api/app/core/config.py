"""Typed application settings loaded exclusively from the API environment."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppEnvironment(StrEnum):
    """Supported API runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Single validated source of runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    database_url: SecretStr
    app_name: str = "2Identify API"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_schema: str = "public"
    database_connect_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 3
    auth_token_secret: SecretStr
    auth_token_ttl_minutes: Annotated[int, Field(ge=5, le=1_440)] = 30
    auth_token_issuer: str = "2identify-api"
    auth_token_audience: str = "2identify-operator"
    auth_admin_token_audience: str = "2identify-admin"
    auth_allowed_profiles: Annotated[frozenset[str], NoDecode] = frozenset({"operador"})
    realtime_heartbeat_interval_seconds: Annotated[
        float,
        Field(ge=0.05, le=300.0),
    ] = 20.0
    realtime_client_queue_capacity: Annotated[int, Field(ge=1, le=1_024)] = 64
    realtime_max_connections: Annotated[int, Field(ge=1, le=10_000)] = 128
    realtime_max_connections_per_admin: Annotated[int, Field(ge=1, le=100)] = 4
    realtime_sink_close_timeout_seconds: Annotated[
        float,
        Field(ge=0.01, le=30.0),
    ] = 2.0

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> SecretStr:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        try:
            url = make_url(raw_value)
        except ArgumentError as error:
            raise ValueError("DATABASE_URL deve ser uma URL SQLAlchemy válida") from error

        if url.get_backend_name() != "postgresql":
            raise ValueError("DATABASE_URL deve apontar para PostgreSQL")
        if url.get_driver_name() != "psycopg2":
            raise ValueError("DATABASE_URL deve utilizar o driver psycopg2")
        if not url.username or not url.host or not url.database:
            raise ValueError("DATABASE_URL deve informar usuário, host e banco")
        return SecretStr(raw_value)

    @field_validator(
        "app_name",
        "database_schema",
        "auth_token_issuer",
        "auth_token_audience",
        "auth_admin_token_audience",
    )
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("a configuração não pode ser vazia")
        return normalized

    @field_validator("database_schema")
    @classmethod
    def validate_database_schema_identifier(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
            raise ValueError("DATABASE_SCHEMA deve ser um identificador SQL simples")
        return value

    @field_validator("auth_token_secret")
    @classmethod
    def validate_auth_token_secret(cls, value: SecretStr) -> SecretStr:
        raw_value = value.get_secret_value()
        if len(raw_value.encode("utf-8")) < 32:
            raise ValueError("AUTH_TOKEN_SECRET deve possuir pelo menos 32 bytes")
        if raw_value.casefold().startswith(("change_me", "generate_")):
            raise ValueError("AUTH_TOKEN_SECRET ainda contém um placeholder")
        return value

    @field_validator("auth_allowed_profiles", mode="before")
    @classmethod
    def parse_auth_allowed_profiles(cls, value: object) -> frozenset[str]:
        raw_profiles = value.split(",") if isinstance(value, str) else value
        if not isinstance(raw_profiles, list | tuple | set | frozenset):
            raise ValueError("AUTH_ALLOWED_PROFILES deve ser uma lista separada por vírgulas")
        profiles = frozenset(str(profile).strip().casefold() for profile in raw_profiles)
        if not profiles or "" in profiles:
            raise ValueError("AUTH_ALLOWED_PROFILES deve informar ao menos um perfil")
        return profiles

    @model_validator(mode="after")
    def validate_realtime_resource_policy(self) -> Settings:
        if (
            self.app_env is not AppEnvironment.TESTING
            and self.realtime_heartbeat_interval_seconds < 5.0
        ):
            raise ValueError(
                "REALTIME_HEARTBEAT_INTERVAL_SECONDS deve ser ao menos 5 fora de testing"
            )
        if self.realtime_max_connections_per_admin > self.realtime_max_connections:
            raise ValueError(
                "REALTIME_MAX_CONNECTIONS_PER_ADMIN não pode exceder "
                "REALTIME_MAX_CONNECTIONS"
            )
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return the secret URL only to the database infrastructure layer."""

        return self.database_url.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache immutable settings for the current process."""

    return Settings()
