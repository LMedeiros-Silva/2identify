from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuração tipada do cliente desktop administrativo."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    api_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://127.0.0.1:8000"),
        validation_alias="API_URL",
    )
    api_connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=60,
        validation_alias="API_CONNECT_TIMEOUT_SECONDS",
    )
    api_read_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        le=120,
        validation_alias="API_READ_TIMEOUT_SECONDS",
    )
    api_write_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        le=120,
        validation_alias="API_WRITE_TIMEOUT_SECONDS",
    )
    api_pool_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=60,
        validation_alias="API_POOL_TIMEOUT_SECONDS",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_directory: Path = Field(
        default=PROJECT_ROOT / "logs",
        validation_alias="LOG_DIRECTORY",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL inválido")
        return normalized

    @property
    def api_base_url(self) -> str:
        return str(self.api_url).rstrip("/") + "/"

    @property
    def worker_shutdown_timeout_ms(self) -> int:
        maximum_request_seconds = sum(
            (
            self.api_connect_timeout_seconds,
            self.api_read_timeout_seconds,
            self.api_write_timeout_seconds,
            self.api_pool_timeout_seconds,
            )
        )
        return int((maximum_request_seconds + 2) * 1000)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_database_url() -> str:
    """Obtém a URL apenas quando uma ferramenta legada de banco é usada."""

    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não foi configurada para a ferramenta de banco solicitada."
        )
    return database_url
