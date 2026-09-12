"""Isolated and secret-safe database configuration for the mobile PoC."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ as process_environment
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core.config import PROJECT_ROOT


class MobilePocConfigurationError(RuntimeError):
    """Raised when cloud configuration cannot be proven safe."""


@dataclass(frozen=True, repr=False)
class MobilePocDatabaseConfig:
    """Validated URLs whose default representation never contains credentials."""

    _local_database_url: SecretStr
    _cloud_database_url: SecretStr
    masked_cloud_target: str

    @property
    def local_sqlalchemy_url(self) -> str:
        return self._local_database_url.get_secret_value()

    @property
    def cloud_sqlalchemy_url(self) -> str:
        return self._cloud_database_url.get_secret_value()

    def __repr__(self) -> str:
        return (
            "MobilePocDatabaseConfig("
            f"local_database_url=SecretStr('**********'), "
            f"cloud_database_url=SecretStr('**********'), "
            f"masked_cloud_target={self.masked_cloud_target!r})"
        )


def _parse_postgresql_url(raw_value: str, *, variable_name: str) -> URL:
    value = raw_value.strip()
    if not value:
        raise MobilePocConfigurationError(f"{variable_name} não foi configurada")
    try:
        url = make_url(value)
    except ArgumentError as error:
        raise MobilePocConfigurationError(
            f"{variable_name} não contém uma URL PostgreSQL válida"
        ) from error

    if url.get_backend_name() != "postgresql" or url.get_driver_name() != "psycopg2":
        raise MobilePocConfigurationError(
            f"{variable_name} deve usar PostgreSQL com driver psycopg2"
        )
    if not url.username or not url.host or not url.database:
        raise MobilePocConfigurationError(
            f"{variable_name} deve informar usuário, host e banco"
        )
    return url.set(drivername="postgresql+psycopg2")


def _unmasked_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def _database_identity(url: URL) -> tuple[str, int, str]:
    assert url.host is not None
    assert url.database is not None
    return (url.host.casefold(), url.port or 5432, url.database.casefold())


def _masked_supabase_target(url: URL) -> str:
    assert url.host is not None
    assert url.database is not None
    labels = url.host.split(".")
    if len(labels) >= 4 and labels[-2:] == ["supabase", "co"]:
        project_label = labels[-3]
        project_prefix = project_label[:2]
        masked_host = ".".join([*labels[:-3], f"{project_prefix}***", "supabase", "co"])
    else:
        masked_host = "***"
    return f"{masked_host}:{url.port or 5432}/{url.database}"


def validate_mobile_database_targets(
    local_database_url: str,
    cloud_database_url: str,
) -> MobilePocDatabaseConfig:
    """Validate that the cloud target is an explicit, different Supabase database."""

    local_url = _parse_postgresql_url(local_database_url, variable_name="DATABASE_URL")
    cloud_url = _parse_postgresql_url(cloud_database_url, variable_name="CLOUD_DATABASE_URL")
    cloud_host = (cloud_url.host or "").casefold()
    if not cloud_host.endswith(".supabase.co"):
        raise MobilePocConfigurationError(
            "CLOUD_DATABASE_URL não aponta para um host Supabase reconhecido"
        )
    if _database_identity(local_url) == _database_identity(cloud_url):
        raise MobilePocConfigurationError("origem local e destino cloud são o mesmo banco")

    return MobilePocDatabaseConfig(
        _local_database_url=SecretStr(_unmasked_url(local_url)),
        _cloud_database_url=SecretStr(_unmasked_url(cloud_url)),
        masked_cloud_target=_masked_supabase_target(cloud_url),
    )


def load_mobile_poc_database_config(
    *,
    local_env_path: Path = PROJECT_ROOT / ".env",
    mobile_env_path: Path = PROJECT_ROOT / ".env.mobile",
    environ: Mapping[str, str] | None = None,
) -> MobilePocDatabaseConfig:
    """Load local and cloud URLs from their separate, non-overlapping sources."""

    environment = process_environment if environ is None else environ
    local_values = dotenv_values(local_env_path) if local_env_path.is_file() else {}
    mobile_values = dotenv_values(mobile_env_path) if mobile_env_path.is_file() else {}
    local_raw = environment.get("DATABASE_URL") or local_values.get("DATABASE_URL")
    cloud_raw = environment.get("CLOUD_DATABASE_URL") or mobile_values.get(
        "CLOUD_DATABASE_URL"
    )
    if not isinstance(local_raw, str) or not local_raw.strip():
        raise MobilePocConfigurationError("DATABASE_URL local não foi configurada")
    if not isinstance(cloud_raw, str) or not cloud_raw.strip():
        raise MobilePocConfigurationError("CLOUD_DATABASE_URL não foi configurada")
    return validate_mobile_database_targets(local_raw, cloud_raw)


__all__ = [
    "MobilePocConfigurationError",
    "MobilePocDatabaseConfig",
    "load_mobile_poc_database_config",
    "validate_mobile_database_targets",
]
