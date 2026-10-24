"""Configuration for the public panel process (reads the API ``.env``)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

API_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEB_DIRECTORY = API_ROOT.parent / "2identify_web"


class PublicPanelSettings(BaseSettings):
    """Only what the public panel needs: no auth secrets or device tokens."""

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    database_url: SecretStr
    database_schema: str = "public"
    database_connect_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 3
    # Public address printed in the QR code; empty means "the address the page was opened on".
    public_panel_url: str = ""
    public_panel_poll_seconds: Annotated[float, Field(ge=0.2, le=30.0)] = 1.0
    public_panel_window: Annotated[int, Field(ge=10, le=500)] = 100
    public_panel_max_clients: Annotated[int, Field(ge=1, le=5_000)] = 500
    public_panel_web_dir: Path = DEFAULT_WEB_DIRECTORY

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> SecretStr:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        try:
            url = make_url(raw)
        except ArgumentError as error:
            raise ValueError("DATABASE_URL deve ser uma URL SQLAlchemy válida") from error
        if url.get_backend_name() not in {"postgresql", "sqlite"}:
            raise ValueError("DATABASE_URL deve apontar para PostgreSQL")
        return SecretStr(raw)

    @field_validator("database_schema")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
            raise ValueError("DATABASE_SCHEMA deve ser um identificador SQL simples")
        return value

    @field_validator("public_panel_url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and re.fullmatch(r"https?://[^\s/]+(/[^\s]*)?", value) is None:
            raise ValueError("PUBLIC_PANEL_URL deve ser uma URL http(s) completa")
        return value
