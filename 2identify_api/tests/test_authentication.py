"""End-to-end HTTP tests for credential authentication on an isolated database."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_authentication_service
from app.core.config import Settings
from app.core.database import get_db
from app.core.security import AccessTokenService
from app.main import create_app
from app.models import Base, Usuario

TEST_SECRET = "test-only-secret-with-at-least-32-bytes"


class LifecycleDatabase:
    def check_connection(self) -> None:
        return None

    def dispose(self) -> None:
        return None


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": (
            "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
        ),
        "app_env": "testing",
        "auth_token_secret": TEST_SECRET,
        "auth_allowed_profiles": "operador",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def isolated_api() -> Iterator[tuple[FastAPI, sessionmaker[Session], Settings, Engine]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings()
    application = create_app(settings=settings, database=LifecycleDatabase())

    def override_get_db() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    yield application, sessions, settings, engine
    application.dependency_overrides.clear()
    engine.dispose()


def add_account(
    sessions: sessionmaker[Session],
    *,
    username: str = "operador.15",
    password: str = "senha-segura",
    profile: str = "operador",
    active: bool = True,
) -> int:
    now = datetime.now(UTC)
    account = Usuario(
        nome="João Silva",
        username=username,
        senha_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        perfil=profile,
        ativo=active,
        criado_em=now,
        atualizado_em=now,
    )
    with sessions() as session:
        session.add(account)
        session.commit()
        return account.id


def test_login_contract_is_compatible_with_operator(isolated_api) -> None:
    application, sessions, settings, _engine = isolated_api
    account_id = add_account(sessions)

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": "  operador.15  ", "password": "senha-segura"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 1_800
    assert payload["operator"] == {
        "id": account_id,
        "name": "João Silva",
        "profile": "operador",
        "profile_photo_reference": None,
    }
    assert response.headers["cache-control"] == "no-store"
    claims = AccessTokenService(settings).verify(payload["access_token"])
    assert claims.subject == account_id
    assert claims.name == "João Silva"
    assert claims.profile == "operador"


def test_administrator_profile_is_rejected_without_explicit_opt_in(
    isolated_api,
) -> None:
    application, sessions, _settings, _engine = isolated_api
    add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "senha-segura"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuário ou senha inválidos."}


@pytest.mark.parametrize(
    ("account_options", "submitted_username", "submitted_password"),
    [
        ({}, "operador.15", "senha-incorreta"),
        ({"active": False}, "operador.15", "senha-segura"),
        ({"profile": "auditor"}, "operador.15", "senha-segura"),
        ({}, "conta.inexistente", "senha-segura"),
    ],
)
def test_login_rejections_are_indistinguishable(
    isolated_api,
    account_options: dict[str, object],
    submitted_username: str,
    submitted_password: str,
) -> None:
    application, sessions, _settings, _engine = isolated_api
    if submitted_username != "conta.inexistente":
        add_account(sessions, **account_options)

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": submitted_username, "password": submitted_password},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuário ou senha inválidos."}
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "", "password": "senha"},
        {"username": "operador", "password": "senha", "unexpected": True},
    ],
)
def test_login_rejects_invalid_payloads(isolated_api, body: dict[str, object]) -> None:
    application, _sessions, _settings, _engine = isolated_api

    with TestClient(application) as client:
        response = client.post("/auth/login", json=body)

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert all("input" not in item for item in response.json()["detail"])


def test_password_over_bcrypt_limit_is_generic_401_without_echo(
    isolated_api,
    caplog: pytest.LogCaptureFixture,
) -> None:
    application, sessions, _settings, _engine = isolated_api
    add_account(sessions)
    submitted_password = "SENSITIVE-BCRYPT-LIMIT-" + ("á" * 40)

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": "operador.15", "password": submitted_password},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuário ou senha inválidos."}
    assert submitted_password not in response.text
    assert submitted_password not in caplog.text


def test_validation_error_never_reflects_submitted_password(isolated_api) -> None:
    application, _sessions, _settings, _engine = isolated_api
    submitted_password = "SENSITIVE-VALIDATION-MARKER-" + ("x" * 1_100)

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": "operador", "password": submitted_password},
        )

    assert response.status_code == 422
    assert submitted_password not in response.text
    assert all("input" not in item for item in response.json()["detail"])
    assert response.headers["cache-control"] == "no-store"


def test_database_failure_returns_sanitized_503(isolated_api) -> None:
    application, _sessions, _settings, _engine = isolated_api

    class UnavailableAuthenticationService:
        def authenticate(self, _username: str, _password: object) -> None:
            raise OperationalError(
                "SELECT senha_hash FROM usuarios",
                {"password": "never-expose"},
                RuntimeError("private-database.internal"),
            )

    application.dependency_overrides[get_authentication_service] = (
        UnavailableAuthenticationService
    )

    with TestClient(application) as client:
        response = client.post(
            "/auth/login",
            json={"username": "operador", "password": "never-expose"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço de autenticação indisponível."}
    assert response.headers["cache-control"] == "no-store"
    assert "never-expose" not in response.text
    assert "private-database" not in response.text
