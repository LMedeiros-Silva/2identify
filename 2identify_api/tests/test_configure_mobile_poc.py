from __future__ import annotations

from pathlib import Path

import pytest

from app.mobile_poc.config import MobilePocConfigurationError
from scripts.configure_mobile_poc import configure_mobile_environment

LOCAL_URL = "postgresql+psycopg2://local:local-pass@127.0.0.1:5432/localdb"
CLOUD_URL = (
    "postgresql+psycopg2://postgres:fake-secret@db.projectref.supabase.co:5432/postgres"
)


def test_configure_mobile_environment_writes_only_isolated_secret_file(
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    mobile_env = tmp_path / ".env.mobile"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\nKEEP_LOCAL=yes\n", encoding="utf-8")

    result = configure_mobile_environment(
        local_env_path=local_env,
        mobile_env_path=mobile_env,
        cloud_database_url=CLOUD_URL,
        cors_origins="http://localhost:5173,http://192.168.1.10:5173",
    )

    assert "fake-secret" not in repr(result)
    assert local_env.read_text(encoding="utf-8") == (
        f"DATABASE_URL={LOCAL_URL}\nKEEP_LOCAL=yes\n"
    )
    written = mobile_env.read_text(encoding="utf-8")
    assert "CLOUD_DATABASE_URL=" in written
    assert "MOBILE_CORS_ORIGINS=http://localhost:5173,http://192.168.1.10:5173" in written


def test_configure_mobile_environment_refuses_to_overwrite_local_env(
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\n", encoding="utf-8")

    with pytest.raises(MobilePocConfigurationError, match="isolado"):
        configure_mobile_environment(
            local_env_path=local_env,
            mobile_env_path=local_env,
            cloud_database_url=CLOUD_URL,
            cors_origins="http://localhost:5173",
        )


def test_configure_mobile_environment_refuses_existing_file_without_force(
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    mobile_env = tmp_path / ".env.mobile"
    local_env.write_text(f"DATABASE_URL={LOCAL_URL}\n", encoding="utf-8")
    mobile_env.write_text("preserve=true\n", encoding="utf-8")

    with pytest.raises(MobilePocConfigurationError, match="já existe"):
        configure_mobile_environment(
            local_env_path=local_env,
            mobile_env_path=mobile_env,
            cloud_database_url=CLOUD_URL,
            cors_origins="http://localhost:5173",
        )

    assert mobile_env.read_text(encoding="utf-8") == "preserve=true\n"
