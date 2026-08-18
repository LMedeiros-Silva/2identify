import json
from collections.abc import Callable

import httpx
import pytest

from app.api.client import OperatorApiClient
from app.domain import LoginCredentials
from app.services.auth_service import (
    AuthenticationUnavailableError,
    CredentialsRejectedError,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> OperatorApiClient:
    return OperatorApiClient(
        base_url="https://api.example.test/v1",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    )


def test_authenticate_credentials_maps_valid_api_response_without_exposing_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.test/v1/auth/login"
        assert json.loads(request.content) == {
            "username": "operador.15",
            "password": "segredo",
        }
        return httpx.Response(
            200,
            json={
                "access_token": "token-confidencial",
                "token_type": "Bearer",
                "operator": {
                    "id": 15,
                    "name": "João Silva",
                    "profile_photo_reference": "operators/15/profile.jpg",
                },
            },
        )

    client = _client(handler)
    credentials = LoginCredentials(username="operador.15", password="segredo")

    result = client.authenticate_credentials(credentials)

    assert result.operator_id == 15
    assert result.name == "João Silva"
    assert result.access_token == "token-confidencial"
    assert result.token_type == "bearer"
    assert "token-confidencial" not in repr(result)
    client.close()


@pytest.mark.parametrize("status_code", [401, 403])
def test_authenticate_credentials_maps_authorization_rejection(status_code: int) -> None:
    client = _client(lambda _request: httpx.Response(status_code))

    with pytest.raises(CredentialsRejectedError, match="Usuário ou senha inválidos"):
        client.authenticate_credentials(LoginCredentials("operador", "incorreta"))

    client.close()


def test_authenticate_credentials_maps_network_failure_without_leaking_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("host interno confidencial", request=request)

    client = _client(handler)

    with pytest.raises(AuthenticationUnavailableError, match="indisponível") as raised:
        client.authenticate_credentials(LoginCredentials("operador", "segredo"))

    assert "host interno" not in str(raised.value)
    client.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"access_token": "token", "operator": {"id": 15}}),
        httpx.Response(200, content=b"not-json"),
    ],
)
def test_authenticate_credentials_fails_closed_for_invalid_api_response(
    response: httpx.Response,
) -> None:
    client = _client(lambda _request: response)

    with pytest.raises(AuthenticationUnavailableError):
        client.authenticate_credentials(LoginCredentials("operador", "segredo"))

    client.close()
