"""Synchronous HTTP adapter for the 2Identify API.

Blocking calls from this client must run outside the Qt UI thread.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.domain import (
    NormalizedPoint,
    Operation,
    PpeRequirement,
    RiskAreaGeometry,
    RiskAreaReference,
    SafetyAlert,
)
from app.domain.auth import CredentialAuthenticationResult, LoginCredentials
from app.services.alert_delivery_service import (
    AlertDeliveryReceipt,
    AlertDeliveryRejectedError,
    AlertDeliveryUnavailableError,
)
from app.services.auth_service import (
    AuthenticationUnavailableError,
    CredentialsRejectedError,
)
from app.services.operation_service import (
    InvalidOperationDataError,
    OperationsUnavailableError,
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


class _AlertReceiptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    alert_id: int = Field(gt=0)
    occurrence_id: int = Field(gt=0)
    duplicate: bool


class _OperationPpePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    code: str | None = None
    description: str | None = None


class _RiskAreaGeometryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern="^polygon$")
    points: tuple[tuple[float, float], ...] = Field(min_length=3)


class _RiskAreaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    camera_id: int = Field(gt=0)
    camera_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    geometry: _RiskAreaGeometryPayload
    active: bool
    created_at: datetime
    updated_at: datetime


class _OperationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    description: str | None = None
    required_ppe: tuple[_OperationPpePayload, ...]
    risk_area: _RiskAreaPayload
    active: bool
    created_at: datetime
    updated_at: datetime


_OPERATION_LIST_ADAPTER = TypeAdapter(tuple[_OperationPayload, ...])
_PPE_DETECTION_CLASS_BY_CODE = {
    "CAP": "capacete",
    "LUV": "luva",
    "EPI-001": "capacete",
    "EPI-002": "luva",
    "EPI-003": "bota",
    "EPI-004": "mangote",
    "EPI-005": "oculos",
    "EPI-006": "protetor_headset",
}
_PPE_DETECTION_CLASS_BY_NAME = {
    "bota": "bota",
    "botas": "bota",
    "capacete": "capacete",
    "colete": "colete_refletivo",
    "colete refletivo": "colete_refletivo",
    "luva": "luva",
    "luvas": "luva",
    "mangote": "mangote",
    "mangotes": "mangote",
    "mascara": "mascara",
    "oculos": "oculos",
    "oculos de protecao": "oculos",
    "protetor auricular": "protetor_headset",
}


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

    def list_operations(self, access_token: str) -> tuple[Operation, ...]:
        """Return the active Admin-configured operation catalog from the API."""

        token = access_token.strip()
        if not token:
            raise OperationsUnavailableError(
                "A consulta de operações exige uma sessão autenticada pela API."
            )
        try:
            response = self._client.get(
                "operator/operations",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as error:
            logger.warning(
                "operation_list_api_unavailable",
                extra={"error_type": type(error).__name__},
            )
            raise OperationsUnavailableError(
                "API indisponível. Verifique se a 2identify_api está em execução."
            ) from error

        if response.status_code in {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}:
            raise OperationsUnavailableError(
                "Sua sessão da API expirou. Saia e entre novamente com usuário e senha."
            )
        try:
            response.raise_for_status()
            payload = _OPERATION_LIST_ADAPTER.validate_python(response.json())
            return tuple(_operation_from_payload(item) for item in payload)
        except httpx.HTTPStatusError as error:
            logger.warning(
                "operation_list_api_rejected",
                extra={"status_code": response.status_code},
            )
            raise OperationsUnavailableError(
                "A API não conseguiu consultar as operações cadastradas."
            ) from error
        except (ValidationError, ValueError) as error:
            logger.error(
                "operation_list_invalid_api_response",
                extra={"status_code": response.status_code, "error_type": type(error).__name__},
            )
            raise InvalidOperationDataError(
                "A API retornou uma configuração de operação inválida."
            ) from error

    def send_alert(
        self,
        alert: SafetyAlert,
        access_token: str,
    ) -> AlertDeliveryReceipt:
        token = access_token.strip()
        if not token:
            raise AlertDeliveryRejectedError(
                "O alerta exige uma sessão autenticada pela API."
            )
        payload = {
            "event_id": str(alert.alert_id),
            "work_session_id": str(alert.work_session_id),
            "operation_id": alert.operation_id,
            "camera_id": alert.camera_id,
            "risk_area_id": alert.risk_area_id,
            "violation_type": alert.violation.violation_type.value,
            "subject_key": alert.violation.subject_key,
            "summary": alert.violation.summary,
            "severity": alert.violation.severity.value,
            "first_observed_at": alert.first_observed_at.isoformat(),
            "raised_at": alert.raised_at.isoformat(),
        }
        try:
            response = self._client.post(
                "operator/alerts",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as error:
            raise AlertDeliveryUnavailableError(
                "API indisponível; o alerta continua registrado localmente."
            ) from error
        if response.status_code in {
            httpx.codes.UNAUTHORIZED,
            httpx.codes.FORBIDDEN,
            httpx.codes.CONFLICT,
            httpx.codes.UNPROCESSABLE_ENTITY,
        }:
            raise AlertDeliveryRejectedError(
                "A API rejeitou o alerta ou a sessão do operador."
            )
        try:
            response.raise_for_status()
            receipt = _AlertReceiptPayload.model_validate(response.json())
        except (httpx.HTTPStatusError, ValidationError, ValueError) as error:
            raise AlertDeliveryUnavailableError(
                "A API não confirmou o registro do alerta."
            ) from error
        if receipt.event_id != alert.alert_id:
            raise AlertDeliveryUnavailableError(
                "A API confirmou um identificador de alerta inesperado."
            )
        return AlertDeliveryReceipt(
            event_id=receipt.event_id,
            alert_id=receipt.alert_id,
            occurrence_id=receipt.occurrence_id,
            duplicate=receipt.duplicate,
        )

    def close(self) -> None:
        self._client.close()


def _operation_from_payload(payload: _OperationPayload) -> Operation:
    geometry = RiskAreaGeometry(
        tuple(NormalizedPoint(x, y) for x, y in payload.risk_area.geometry.points)
    )
    risk_area = RiskAreaReference(
        risk_area_id=payload.risk_area.id,
        name=payload.risk_area.name,
        geometry=geometry,
        geometry_calibrated=True,
        camera_id=payload.risk_area.camera_id,
        camera_name=payload.risk_area.camera_name,
    )
    required_ppe = tuple(
        PpeRequirement(
            ppe_id=item.id,
            name=item.name,
            detection_class=_ppe_detection_class(item),
        )
        for item in payload.required_ppe
    )
    return Operation(
        operation_id=payload.id,
        name=payload.name,
        description=payload.description,
        required_ppe=required_ppe,
        risk_area=risk_area,
        active=payload.active,
    )


def _ppe_detection_class(payload: _OperationPpePayload) -> str | None:
    code = payload.code.strip().upper() if payload.code is not None else None
    if code and code in _PPE_DETECTION_CLASS_BY_CODE:
        return _PPE_DETECTION_CLASS_BY_CODE[code]
    normalized_name = " ".join(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", payload.name)
            if not unicodedata.combining(character)
        )
        .casefold()
        .split()
    )
    return _PPE_DETECTION_CLASS_BY_NAME.get(normalized_name)
