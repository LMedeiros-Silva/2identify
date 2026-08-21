from __future__ import annotations

import logging
from typing import Any, Literal

import httpx
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    SecretStr,
    ValidationError,
    field_validator,
)

from app.core.config import Settings
from app.domain import (
    AdminAuthentication,
    AdminCredentials,
    Administrator,
    DashboardSummary,
)
from app.services.errors import (
    ApiUnavailableError,
    InvalidApiResponseError,
    InvalidCredentialsError,
    SessionExpiredError,
)

logger = logging.getLogger(__name__)


class _AdministratorDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=1, max_length=100)
    profile: Literal["administrador"]

    def to_domain(self) -> Administrator:
        return Administrator(
            id=self.id,
            name=self.name,
            username=self.username,
            profile=self.profile,
        )


class _AdminLoginDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: SecretStr
    token_type: str
    expires_in: PositiveInt
    administrator: _AdministratorDto

    @field_validator("token_type")
    @classmethod
    def validate_token_type(cls, value: str) -> str:
        if value.lower() != "bearer":
            raise ValueError("unsupported token type")
        return "bearer"

    def to_domain(self) -> AdminAuthentication:
        return AdminAuthentication(
            administrator=self.administrator.to_domain(),
            access_token=self.access_token.get_secret_value(),
            token_type=self.token_type,
            expires_in=self.expires_in,
        )


class _AdminMeEnvelopeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    administrator: _AdministratorDto


class _DashboardSummaryDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_employees: int = Field(ge=0)
    ppe_assignments: int = Field(ge=0)
    delivered_ppe: int = Field(ge=0)
    ppe_delivery_percentage: float = Field(ge=0, le=100)
    alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    generated_at: AwareDatetime

    def to_domain(self) -> DashboardSummary:
        return DashboardSummary(
            active_employees=self.active_employees,
            ppe_assignments=self.ppe_assignments,
            delivered_ppe=self.delivered_ppe,
            ppe_delivery_percentage=self.ppe_delivery_percentage,
            alerts=self.alerts,
            critical_alerts=self.critical_alerts,
            generated_at=self.generated_at,
        )


class AdminApiClient:
    """Cliente HTTP síncrono executado exclusivamente nos workers Qt."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        timeout = httpx.Timeout(
            connect=settings.api_connect_timeout_seconds,
            read=settings.api_read_timeout_seconds,
            write=settings.api_write_timeout_seconds,
            pool=settings.api_pool_timeout_seconds,
        )
        self._client = httpx.Client(
            base_url=settings.api_base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "2Identify-Admin/0.4.0",
            },
        )
        self._closed = False

    def login(self, credentials: AdminCredentials) -> AdminAuthentication:
        response = self._request(
            "POST",
            "/auth/admin/login",
            json={
                "username": credentials.username,
                "password": credentials.password,
            },
        )

        if response.status_code in (401, 403):
            raise InvalidCredentialsError("Usuário ou senha inválidos.")
        self._ensure_success(response, operation="admin_login")

        try:
            return _AdminLoginDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            logger.warning(
                "Resposta incompatível da API",
                extra={"operation": "admin_login", "status_code": response.status_code},
            )
            raise InvalidApiResponseError(
                "A API retornou uma resposta de autenticação inválida."
            ) from error

    def get_current_administrator(self, access_token: str) -> Administrator:
        response = self._authorized_request(
            "GET", "/admin/me", access_token=access_token
        )
        self._ensure_protected_success(response, operation="admin_me")

        try:
            payload: Any = response.json()
            try:
                dto = _AdministratorDto.model_validate(payload)
            except ValidationError:
                dto = _AdminMeEnvelopeDto.model_validate(payload).administrator
            return dto.to_domain()
        except (ValueError, ValidationError) as error:
            logger.warning(
                "Resposta incompatível da API",
                extra={"operation": "admin_me", "status_code": response.status_code},
            )
            raise InvalidApiResponseError(
                "A API retornou uma identidade administrativa inválida."
            ) from error

    def get_dashboard_summary(self, access_token: str) -> DashboardSummary:
        response = self._authorized_request(
            "GET", "/admin/dashboard/summary", access_token=access_token
        )
        self._ensure_protected_success(response, operation="dashboard_summary")

        try:
            return _DashboardSummaryDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            logger.warning(
                "Resposta incompatível da API",
                extra={
                    "operation": "dashboard_summary",
                    "status_code": response.status_code,
                },
            )
            raise InvalidApiResponseError(
                "A API retornou indicadores inválidos para o dashboard."
            ) from error

    def close(self) -> None:
        if not self._closed:
            self._client.close()
            self._closed = True

    def _authorized_request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
    ) -> httpx.Response:
        if not access_token:
            raise SessionExpiredError("Sua sessão expirou. Entre novamente.")
        return self._request(
            method,
            path,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._closed:
            raise ApiUnavailableError("O cliente da API já foi encerrado.")

        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            logger.warning("Timeout na API", extra={"operation": path})
            raise ApiUnavailableError(
                "A API demorou para responder. Tente novamente."
            ) from error
        except httpx.TransportError as error:
            logger.warning("API indisponível", extra={"operation": path})
            raise ApiUnavailableError(
                "Não foi possível conectar à API. Verifique a conexão e tente novamente."
            ) from error

    @staticmethod
    def _ensure_protected_success(
        response: httpx.Response,
        *,
        operation: str,
    ) -> None:
        if response.status_code in (401, 403):
            raise SessionExpiredError("Sua sessão expirou. Entre novamente.")
        AdminApiClient._ensure_success(response, operation=operation)

    @staticmethod
    def _ensure_success(response: httpx.Response, *, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        logger.warning(
            "Erro HTTP da API",
            extra={"operation": operation, "status_code": response.status_code},
        )
        raise ApiUnavailableError(
            "A API não conseguiu concluir a solicitação. Tente novamente."
        )

    def __enter__(self) -> AdminApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
