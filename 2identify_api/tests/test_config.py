"""Configuration safety tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_secret_is_masked_in_settings_representation() -> None:
    raw_url = "postgresql+psycopg2://identify_user:very-secret@localhost:5432/identify_db"
    settings = Settings(database_url=raw_url, _env_file=None)

    assert raw_url not in repr(settings)
    assert "very-secret" not in repr(settings)


def test_operator_is_the_only_profile_allowed_by_default() -> None:
    settings = Settings(
        database_url="postgresql+psycopg2://user:password@localhost/identify_db",
        _env_file=None,
    )

    assert settings.auth_allowed_profiles == frozenset({"operador"})
    assert settings.auth_token_audience == "2identify-operator"
    assert settings.auth_admin_token_audience == "2identify-admin"


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///local.db",
        "postgresql+asyncpg://user:password@localhost/identify_db",
        "postgresql+psycopg2:///identify_db",
    ],
)
def test_database_url_must_use_expected_postgresql_driver(database_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=database_url, _env_file=None)


def test_realtime_heartbeat_cannot_create_query_storm_outside_testing() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg2://user:password@localhost/identify_db",
            app_env="development",
            realtime_heartbeat_interval_seconds=0.05,
            _env_file=None,
        )


def test_per_admin_realtime_limit_cannot_exceed_global_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg2://user:password@localhost/identify_db",
            realtime_max_connections=2,
            realtime_max_connections_per_admin=3,
            _env_file=None,
        )
