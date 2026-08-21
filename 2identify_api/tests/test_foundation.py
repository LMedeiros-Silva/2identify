"""Contract tests for the Stage 33 foundation endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import DatabaseUnavailableError
from app.main import app, create_app


class FakeDatabase:
    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.disposed = False

    def check_connection(self) -> None:
        if self.unavailable:
            internal_error = RuntimeError(
                "password=never-expose host=private-database.internal"
            )
            raise DatabaseUnavailableError("PostgreSQL indisponível") from internal_error

    def dispose(self) -> None:
        self.disposed = True


def make_settings() -> Settings:
    return Settings(
        database_url=(
            "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
        ),
        app_env="testing",
        auth_token_secret="test-only-secret-with-at-least-32-bytes",
        _env_file=None,
    )


def test_application_import_creates_fastapi_instance() -> None:
    assert isinstance(app, FastAPI)


def test_root_contract() -> None:
    database = FakeDatabase()
    application = create_app(settings=make_settings(), database=database)

    with TestClient(application) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"name": "2Identify API", "status": "running"}
    assert database.disposed is True


def test_health_reports_real_gateway_success() -> None:
    application = create_app(settings=make_settings(), database=FakeDatabase())

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_failure_is_sanitized() -> None:
    application = create_app(
        settings=make_settings(),
        database=FakeDatabase(unavailable=True),
    )

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "disconnected"}
    assert "never-expose" not in response.text
    assert "private-database" not in response.text


def test_openapi_documentation_is_available() -> None:
    application = create_app(settings=make_settings(), database=FakeDatabase())

    with TestClient(application) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
    assert "/auth/login" in response.json()["paths"]
