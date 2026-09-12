"""Security tests for the isolated mobile PoC database configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.mobile_poc.config import (
    MobilePocConfigurationError,
    load_mobile_poc_database_config,
    validate_mobile_database_targets,
)

LOCAL_URL = "postgresql+psycopg2://local_user:local-secret@127.0.0.1:5432/identify"
CLOUD_URL = (
    "postgresql://postgres:cloud-secret-with-%23@db.projectref.supabase.co:5432/postgres"
)


def test_database_targets_are_normalized_and_secrets_stay_masked() -> None:
    config = validate_mobile_database_targets(LOCAL_URL, CLOUD_URL)

    assert config.local_sqlalchemy_url.startswith("postgresql+psycopg2://")
    assert config.cloud_sqlalchemy_url.startswith("postgresql+psycopg2://")
    assert config.masked_cloud_target == "db.pr***.supabase.co:5432/postgres"
    assert "local-secret" not in repr(config)
    assert "cloud-secret" not in repr(config)
    assert CLOUD_URL not in repr(config)


@pytest.mark.parametrize(
    ("local_url", "cloud_url"),
    [
        (LOCAL_URL, "postgresql://postgres:secret@cloud.example.com/postgres"),
        (
            "postgresql://user:one@db.same.supabase.co:5432/postgres",
            "postgresql://other:two@db.same.supabase.co:5432/postgres",
        ),
        ("sqlite:///local.db", CLOUD_URL),
    ],
)
def test_preflight_rejects_non_supabase_same_target_and_non_postgresql(
    local_url: str,
    cloud_url: str,
) -> None:
    with pytest.raises(MobilePocConfigurationError) as captured:
        validate_mobile_database_targets(local_url, cloud_url)

    message = str(captured.value)
    assert "secret" not in message.casefold()
    assert local_url not in message
    assert cloud_url not in message


def test_mobile_configuration_reads_local_and_cloud_urls_from_separate_files(
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    mobile_env = tmp_path / ".env.mobile"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\n", encoding="utf-8")
    mobile_env.write_text(f"CLOUD_DATABASE_URL={CLOUD_URL}\n", encoding="utf-8")

    config = load_mobile_poc_database_config(
        local_env_path=local_env,
        mobile_env_path=mobile_env,
        environ={},
    )

    assert "127.0.0.1" in config.local_sqlalchemy_url
    assert "supabase.co" in config.cloud_sqlalchemy_url


def test_mobile_file_cannot_override_the_local_database_url(tmp_path: Path) -> None:
    local_env = tmp_path / ".env"
    mobile_env = tmp_path / ".env.mobile"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\n", encoding="utf-8")
    mobile_env.write_text(
        f"DATABASE_URL={CLOUD_URL}\nCLOUD_DATABASE_URL={CLOUD_URL}\n",
        encoding="utf-8",
    )

    config = load_mobile_poc_database_config(
        local_env_path=local_env,
        mobile_env_path=mobile_env,
        environ={},
    )

    assert "127.0.0.1" in config.local_sqlalchemy_url


def test_missing_cloud_configuration_fails_without_revealing_local_url(
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\n", encoding="utf-8")

    with pytest.raises(MobilePocConfigurationError) as captured:
        load_mobile_poc_database_config(
            local_env_path=local_env,
            mobile_env_path=tmp_path / ".env.mobile",
            environ={},
        )

    assert LOCAL_URL not in str(captured.value)
