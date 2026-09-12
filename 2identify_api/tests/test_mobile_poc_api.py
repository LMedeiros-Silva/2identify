"""CORS and isolated cloud API launcher tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mobile_poc.config import validate_mobile_database_targets
from scripts.run_mobile_poc_api import build_mobile_api_environment, startup_message
from tests.test_admin_api import LifecycleDatabase, make_settings


def test_cors_is_absent_locally_and_limited_to_configured_mobile_origin() -> None:
    local_app = create_app(settings=make_settings(), database=LifecycleDatabase())
    mobile_app = create_app(
        settings=make_settings(mobile_cors_origins="http://localhost:5173"),
        database=LifecycleDatabase(),
    )
    preflight_headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }

    with TestClient(local_app) as client:
        local_response = client.options("/admin/alerts", headers=preflight_headers)
    with TestClient(mobile_app) as client:
        allowed = client.options("/admin/alerts", headers=preflight_headers)
        blocked = client.options(
            "/admin/alerts",
            headers={**preflight_headers, "Origin": "http://untrusted.example"},
        )

    assert "access-control-allow-origin" not in local_response.headers
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in blocked.headers


def test_launcher_changes_only_the_child_environment(tmp_path: Path) -> None:
    mobile_env = tmp_path / ".env.mobile"
    mobile_env.write_text(
        "MOBILE_CORS_ORIGINS=http://localhost:5173,http://192.168.1.20:5173\n",
        encoding="utf-8",
    )
    config = validate_mobile_database_targets(
        "postgresql://local:one@127.0.0.1:5432/identify",
        "postgresql://cloud:two@db.projectref.supabase.co:5432/postgres",
    )
    parent = {
        "DATABASE_URL": config.local_sqlalchemy_url,
        "CLOUD_DATABASE_URL": config.cloud_sqlalchemy_url,
        "UNCHANGED": "yes",
    }

    child = build_mobile_api_environment(config, mobile_env, parent)

    assert parent["DATABASE_URL"] == config.local_sqlalchemy_url
    assert child["DATABASE_URL"] == config.cloud_sqlalchemy_url
    assert "CLOUD_DATABASE_URL" not in child
    assert child["MOBILE_CORS_ORIGINS"] == (
        "http://localhost:5173,http://192.168.1.20:5173"
    )
    assert child["UNCHANGED"] == "yes"


def test_launcher_message_contains_only_masked_cloud_target() -> None:
    config = validate_mobile_database_targets(
        "postgresql://local:one@127.0.0.1:5432/identify",
        "postgresql://cloud:two@db.projectref.supabase.co:5432/postgres",
    )

    message = startup_message(config, host="0.0.0.0", port=8000)

    assert message == (
        "API mobile iniciando em 0.0.0.0:8000 com destino "
        "db.pr***.supabase.co:5432/postgres"
    )
    assert "cloud:two" not in message
