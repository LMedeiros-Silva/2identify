from __future__ import annotations

import json

import httpx
import pytest

from app.api import AdminApiClient
from app.core.config import Settings
from app.domain import AdminCredentials
from app.services.admin_auth_service import AdminAuthService
from app.services.errors import (
    ApiUnavailableError,
    InvalidApiResponseError,
    InvalidCredentialsError,
    SessionExpiredError,
)

TOKEN = "header.payload.signature"


def make_settings() -> Settings:
    return Settings(_env_file=None, API_URL="https://api.example.test")  # type: ignore[call-arg]


def administrator_payload() -> dict[str, object]:
    return {
        "id": 7,
        "name": "Administradora Teste",
        "username": "admin.teste",
        "profile": "administrador",
    }


def test_login_and_me_follow_contract_without_exposing_secrets() -> None:
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        if request.url.path == "/auth/admin/login":
            assert json.loads(request.content) == {
                "username": "admin.teste",
                "password": "senha-super-secreta",
            }
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                json={
                    "access_token": TOKEN,
                    "token_type": "bearer",
                    "expires_in": 900,
                    "administrator": administrator_payload(),
                },
            )
        assert request.url.path == "/admin/me"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json=administrator_payload())

    credentials = AdminCredentials(" admin.teste ", "senha-super-secreta")
    with AdminApiClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        authentication = AdminAuthService(client).authenticate(credentials)

    assert observed_paths == ["/auth/admin/login", "/admin/me"]
    assert authentication.administrator.username == "admin.teste"
    assert TOKEN not in repr(authentication)
    assert "senha-super-secreta" not in repr(credentials)


def test_dashboard_summary_contract_and_authorization_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/dashboard/summary"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            json={
                "active_employees": 3,
                "ppe_assignments": 12,
                "delivered_ppe": 9,
                "ppe_delivery_percentage": 75.0,
                "alerts": 4,
                "critical_alerts": 1,
                "generated_at": "2026-08-20T12:30:00Z",
            },
        )

    with AdminApiClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        summary = client.get_dashboard_summary(TOKEN)

    assert summary.active_employees == 3
    assert summary.delivered_ppe == 9
    assert summary.generated_at.tzinfo is not None


@pytest.mark.parametrize("status_code", [401, 403])
def test_protected_endpoint_rejects_expired_or_forbidden_session(
    status_code: int,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code, json={"detail": "sensitive"})
    )
    with AdminApiClient(make_settings(), transport=transport) as client:
        with pytest.raises(SessionExpiredError, match="sessão expirou"):
            client.get_dashboard_summary(TOKEN)


def test_invalid_login_is_not_reported_as_offline() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(401, json={"detail": "invalid"})
    )
    with AdminApiClient(make_settings(), transport=transport) as client:
        with pytest.raises(InvalidCredentialsError):
            client.login(AdminCredentials("admin", "senha-incorreta"))


def test_transport_failure_is_recoverable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with AdminApiClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ApiUnavailableError, match="conectar"):
            client.get_dashboard_summary(TOKEN)


def test_inconsistent_dashboard_payload_is_rejected() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "active_employees": 1,
                "ppe_assignments": 1,
                "delivered_ppe": 2,
                "ppe_delivery_percentage": 100,
                "alerts": 0,
                "critical_alerts": 0,
                "generated_at": "2026-08-20T12:30:00Z",
            },
        )
    )
    with AdminApiClient(make_settings(), transport=transport) as client:
        with pytest.raises(InvalidApiResponseError):
            client.get_dashboard_summary(TOKEN)
