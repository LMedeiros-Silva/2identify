"""Synchronous HTTP adapter for the 2Identify API.

Blocking calls from this client must run outside the Qt UI thread.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.auth import CredentialAuthenticationResult, LoginCredentials
from app.services.auth_service import (
    AuthenticationUnavailableError,
    CredentialsRejectedError,
)

logger = logging.getLogger(__name__)


class _OperatorPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    profile_photo_reference: str | None = None


class _CredentialLoginPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    token_type: str = "bearer"
    operator: _OperatorPayload


class OperatorApiClient:
    """HTTP provider for Operator authentication and future API use cases."""

    def __init__(
        self,
        base_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=read_timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "2Identify-Operator"},
        )

    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        try:
            response = self._client.post(
                "auth/login",
                json={"username": credentials.username, "password": credentials.password},
            )
        except httpx.RequestError as error:
            logger.warning(
                "credential_authentication_api_unavailable",
                extra={"error_type": type(error).__name__},
            )
            raise AuthenticationUnavailableError(
                "Serviço de autenticação indisponível. Tente novamente em instantes."
            ) from error

        if response.status_code in {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}:
            logger.warning(
                "credential_authentication_rejected",
                extra={"status_code": response.status_code},
            )
            raise CredentialsRejectedError("Usuário ou senha inválidos.")

        try:
            response.raise_for_status()
            payload = _CredentialLoginPayload.model_validate(response.json())
            return CredentialAuthenticationResult(
                operator_id=payload.operator.id,
                name=payload.operator.name,
                access_token=payload.access_token,
                token_type=payload.token_type,
                profile_photo_reference=payload.operator.profile_photo_reference,
            )
        except (httpx.HTTPStatusError, ValidationError, ValueError) as error:
            logger.error(
                "credential_authentication_invalid_api_response",
                extra={"status_code": response.status_code, "error_type": type(error).__name__},
            )
            raise AuthenticationUnavailableError(
                "O serviço de autenticação retornou uma resposta inválida."
            ) from error

    def close(self) -> None:
        self._client.close()
