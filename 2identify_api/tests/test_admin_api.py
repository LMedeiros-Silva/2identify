"""Administrative authentication and dashboard tests on an isolated database."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    Boolean,
    Column,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    update,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import (
    get_admin_authentication_service,
    get_admin_authorization_service,
    get_admin_dashboard_service,
)
from app.core.config import Settings
from app.core.database import get_db
from app.core.security import AccessTokenService, InvalidAccessTokenError
from app.main import create_app
from app.models import Base, Usuario
from app.services import AuthenticatedAccount

TEST_SECRET = "admin-test-secret-with-at-least-32-bytes"


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
        "auth_token_audience": "2identify-operator",
        "auth_admin_token_audience": "2identify-admin",
        "auth_allowed_profiles": "operador",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def isolated_admin_api() -> Iterator[
    tuple[
        FastAPI,
        sessionmaker[Session],
        Settings,
        Engine,
        dict[str, Table],
    ]
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    dashboard_metadata = MetaData()
    dashboard_tables = {
        "funcionarios": Table(
            "funcionarios",
            dashboard_metadata,
            Column("id", Integer, primary_key=True),
            Column("ativo", Boolean, nullable=False),
        ),
        "funcionario_epis": Table(
            "funcionario_epis",
            dashboard_metadata,
            Column("id", Integer, primary_key=True),
            Column("entregue", Boolean, nullable=False),
        ),
        "alertas": Table(
            "alertas",
            dashboard_metadata,
            Column("id", Integer, primary_key=True),
            Column("nivel", String(30), nullable=False),
        ),
    }
    dashboard_metadata.create_all(engine)
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
    yield application, sessions, settings, engine, dashboard_tables
    application.dependency_overrides.clear()
    engine.dispose()


def add_account(
    sessions: sessionmaker[Session],
    *,
    username: str,
    profile: str,
    password: str = "senha-segura",
    active: bool = True,
) -> int:
    now = datetime.now(UTC)
    account = Usuario(
        nome="Administrador Teste" if profile == "administrador" else "Operador Teste",
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


def admin_login(client: TestClient) -> str:
    response = client.post(
        "/auth/admin/login",
        json={"username": "admin", "password": "senha-segura"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_admin_login_contract_and_audience_are_isolated(isolated_admin_api) -> None:
    application, sessions, settings, _engine, _tables = isolated_admin_api
    account_id = add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        response = client.post(
            "/auth/admin/login",
            json={"username": "  admin  ", "password": "senha-segura"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 1_800
    assert payload["administrator"] == {
        "id": account_id,
        "name": "Administrador Teste",
        "username": "admin",
        "profile": "administrador",
    }
    assert response.headers["cache-control"] == "no-store"
    admin_tokens = AccessTokenService(
        settings,
        audience=settings.auth_admin_token_audience,
    )
    assert admin_tokens.verify(payload["access_token"]).profile == "administrador"
    with pytest.raises(InvalidAccessTokenError):
        AccessTokenService(settings).verify(payload["access_token"])


def test_operator_login_remains_operator_only_and_cannot_access_admin(
    isolated_admin_api,
) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    add_account(sessions, username="operador", profile="operador")
    add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        operator_login = client.post(
            "/auth/login",
            json={"username": "operador", "password": "senha-segura"},
        )
        admin_on_operator_route = client.post(
            "/auth/login",
            json={"username": "admin", "password": "senha-segura"},
        )
        admin_response = client.get(
            "/admin/me",
            headers={"Authorization": f"Bearer {operator_login.json()['access_token']}"},
        )

    assert operator_login.status_code == 200
    assert admin_on_operator_route.status_code == 401
    assert admin_response.status_code == 401
    assert admin_response.headers["cache-control"] == "no-store"


def test_operator_profile_is_rejected_by_admin_login(isolated_admin_api) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    add_account(sessions, username="operador", profile="operador")

    with TestClient(application) as client:
        response = client.post(
            "/auth/admin/login",
            json={"username": "operador", "password": "senha-segura"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuário ou senha inválidos."}
    assert response.headers["cache-control"] == "no-store"


def test_admin_me_returns_direct_revalidated_identity(isolated_admin_api) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    account_id = add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        token = admin_login(client)
        response = client.get(
            "/admin/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": account_id,
        "name": "Administrador Teste",
        "username": "admin",
        "profile": "administrador",
    }
    assert response.headers["cache-control"] == "no-store"


def test_admin_resources_reject_missing_tampered_expired_and_wrong_issuer_tokens(
    isolated_admin_api,
) -> None:
    application, sessions, settings, _engine, _tables = isolated_admin_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    now = datetime.now(UTC)
    base_payload = {
        "sub": str(account_id),
        "name": "Administrador Teste",
        "profile": "administrador",
        "iat": now - timedelta(minutes=2),
        "nbf": now - timedelta(minutes=2),
        "exp": now + timedelta(minutes=2),
        "iss": settings.auth_token_issuer,
        "aud": settings.auth_admin_token_audience,
        "jti": "route-security-test-token",
    }
    expired_payload = {**base_payload, "exp": now - timedelta(minutes=1)}
    wrong_issuer_payload = {**base_payload, "iss": "untrusted-issuer"}
    expired = jwt.encode(
        expired_payload,
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )
    wrong_issuer = jwt.encode(
        wrong_issuer_payload,
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )

    with TestClient(application) as client:
        valid = admin_login(client)
        token_parts = valid.split(".")
        altered_first_character = "A" if token_parts[2][0] != "A" else "B"
        token_parts[2] = f"{altered_first_character}{token_parts[2][1:]}"
        tampered = ".".join(token_parts)
        responses = [client.get("/admin/me")]
        responses.extend(
            client.get(
                "/admin/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            for token in (tampered, expired, wrong_issuer)
        )

    for response in responses:
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("column", "value"),
    [("ativo", False), ("perfil", "operador")],
)
def test_protected_routes_recheck_active_admin_profile(
    isolated_admin_api,
    column: str,
    value: object,
) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    account_id = add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        token = admin_login(client)
        with sessions.begin() as session:
            session.execute(
                update(Usuario).where(Usuario.id == account_id).values({column: value})
            )
        response = client.get(
            "/admin/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Token de acesso inválido."}
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_returns_zero_safe_metrics(isolated_admin_api) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    add_account(sessions, username="admin", profile="administrador")

    with TestClient(application) as client:
        token = admin_login(client)
        response = client.get(
            "/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in payload if key != "generated_at"} == {
        "active_employees": 0,
        "ppe_assignments": 0,
        "delivered_ppe": 0,
        "ppe_delivery_percentage": 0.0,
        "alerts": 0,
        "critical_alerts": 0,
    }
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo is not None
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_returns_read_only_operational_metrics(isolated_admin_api) -> None:
    application, sessions, _settings, engine, tables = isolated_admin_api
    add_account(sessions, username="admin", profile="administrador")
    with engine.begin() as connection:
        connection.execute(
            tables["funcionarios"].insert(),
            [{"ativo": True}, {"ativo": True}, {"ativo": False}],
        )
        connection.execute(
            tables["funcionario_epis"].insert(),
            [{"entregue": True}, {"entregue": True}, {"entregue": False}],
        )
        connection.execute(
            tables["alertas"].insert(),
            [{"nivel": "critico"}, {"nivel": " CRITICO "}, {"nivel": "aviso"}],
        )

    with TestClient(application) as client:
        token = admin_login(client)
        response = client.get(
            "/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_employees"] == 2
    assert payload["ppe_assignments"] == 3
    assert payload["delivered_ppe"] == 2
    assert payload["ppe_delivery_percentage"] == 66.7
    assert payload["alerts"] == 3
    assert payload["critical_alerts"] == 2


def test_admin_login_database_failure_is_sanitized(isolated_admin_api) -> None:
    application, _sessions, _settings, _engine, _tables = isolated_admin_api

    class UnavailableAuthenticationService:
        def authenticate(self, _username: str, _password: object) -> None:
            raise OperationalError(
                "SELECT senha_hash FROM usuarios",
                {"password": "never-expose"},
                RuntimeError("private-database.internal"),
            )

    application.dependency_overrides[get_admin_authentication_service] = (
        UnavailableAuthenticationService
    )
    with TestClient(application) as client:
        response = client.post(
            "/auth/admin/login",
            json={"username": "admin", "password": "never-expose"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço de autenticação indisponível."}
    assert response.headers["cache-control"] == "no-store"
    assert "never-expose" not in response.text
    assert "private-database" not in response.text


def test_dashboard_database_failure_is_sanitized(isolated_admin_api) -> None:
    application, sessions, _settings, _engine, _tables = isolated_admin_api
    add_account(sessions, username="admin", profile="administrador")

    class UnavailableDashboardService:
        def get_summary(self) -> None:
            raise OperationalError(
                "SELECT count(*) FROM alertas",
                {"password": "never-expose"},
                RuntimeError("private-database.internal"),
            )

    application.dependency_overrides[get_admin_dashboard_service] = UnavailableDashboardService
    with TestClient(application) as client:
        token = admin_login(client)
        response = client.get(
            "/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço administrativo indisponível."}
    assert response.headers["cache-control"] == "no-store"
    assert "never-expose" not in response.text
    assert "private-database" not in response.text


def test_admin_account_recheck_database_failure_is_sanitized(isolated_admin_api) -> None:
    application, _sessions, _settings, _engine, _tables = isolated_admin_api

    class UnavailableAuthorizationService:
        def authorize(self, _token: str) -> None:
            raise OperationalError(
                "SELECT * FROM usuarios WHERE id = ?",
                {"password": "never-expose"},
                RuntimeError("private-database.internal"),
            )

    application.dependency_overrides[get_admin_authorization_service] = (
        UnavailableAuthorizationService
    )
    with TestClient(application) as client:
        response = client.get(
            "/admin/me",
            headers={"Authorization": "Bearer syntactically-valid-placeholder"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço administrativo indisponível."}
    assert response.headers["cache-control"] == "no-store"
    assert "never-expose" not in response.text
    assert "private-database" not in response.text


def test_admin_validation_error_never_reflects_password(isolated_admin_api) -> None:
    application, _sessions, _settings, _engine, _tables = isolated_admin_api
    submitted_password = "SENSITIVE-ADMIN-MARKER-" + ("x" * 1_100)

    with TestClient(application) as client:
        response = client.post(
            "/auth/admin/login",
            json={"username": "admin", "password": submitted_password},
        )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert submitted_password not in response.text
    assert all("input" not in item for item in response.json()["detail"])


def test_authenticated_account_repr_hides_bearer_token() -> None:
    account = AuthenticatedAccount(
        account_id=1,
        name="Administrador Teste",
        username="admin",
        profile="administrador",
        access_token="SENSITIVE-BEARER-TOKEN",
        expires_in_seconds=1_800,
    )

    assert "SENSITIVE-BEARER-TOKEN" not in repr(account)
