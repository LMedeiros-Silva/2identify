from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal
from uuid import UUID

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

from app.api.operation_contracts import (
    parse_camera,
    parse_catalog,
    parse_managed_camera,
    parse_managed_cameras,
    parse_operation,
    parse_operations,
    parse_risk_area,
    parse_risk_areas,
)
from app.api.ppe_contracts import parse_active_operations
from app.core.config import Settings
from app.domain import (
    AdminAlert,
    AdminAlertPage,
    AdminAuthentication,
    AdminCredentials,
    Administrator,
    AlertActor,
    AlertCamera,
    AlertEmployee,
    AlertOccurrence,
    AlertOperationalContext,
    AlertSector,
    CameraDraft,
    CameraOption,
    DashboardAlertCategories,
    DashboardAlertStatus,
    DashboardAlertTrendPoint,
    DashboardSummary,
    EmployeeDraft,
    EmployeePage,
    EmployeeRecord,
    FaceTemplateDraft,
    FaceTemplateStatus,
    ManagedCamera,
    OperationCatalog,
    OperationConfiguration,
    OperationDraft,
    RiskArea,
    RiskAreaDraft,
)
from app.domain.ppe_management import ActiveOperationSnapshot
from app.services.errors import (
    AlertNotFoundError,
    AlertStateConflictError,
    ApiUnavailableError,
    ConfigurationConflictError,
    ConfigurationNotFoundError,
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


class _DashboardAlertStatusDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new: int = Field(ge=0)
    confirmed: int = Field(ge=0)
    closed: int = Field(ge=0)
    other: int = Field(ge=0)


class _DashboardAlertCategoriesDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ppe: int = Field(ge=0)
    ergonomics: int = Field(ge=0)
    risk_area: int = Field(ge=0)
    monitoring: int = Field(ge=0)
    other: int = Field(ge=0)


class _DashboardAlertTrendPointDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    alerts: int = Field(ge=0)


class _DashboardSummaryDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_employees: int = Field(ge=0)
    ppe_assignments: int = Field(ge=0)
    delivered_ppe: int = Field(ge=0)
    ppe_delivery_percentage: float = Field(ge=0, le=100)
    alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    alert_status: _DashboardAlertStatusDto
    alert_categories: _DashboardAlertCategoriesDto
    alert_trend: tuple[_DashboardAlertTrendPointDto, ...] = Field(
        min_length=7,
        max_length=7,
    )
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
            alert_status=DashboardAlertStatus(
                new=self.alert_status.new,
                confirmed=self.alert_status.confirmed,
                closed=self.alert_status.closed,
                other=self.alert_status.other,
            ),
            alert_categories=DashboardAlertCategories(
                ppe=self.alert_categories.ppe,
                ergonomics=self.alert_categories.ergonomics,
                risk_area=self.alert_categories.risk_area,
                monitoring=self.alert_categories.monitoring,
                other=self.alert_categories.other,
            ),
            alert_trend=tuple(
                DashboardAlertTrendPoint(day=item.day, alerts=item.alerts)
                for item in self.alert_trend
            ),
        )


class _AlertActorDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str = Field(min_length=1, max_length=150)

    def to_domain(self) -> AlertActor:
        return AlertActor(id=self.id, name=self.name)


class _AlertSectorDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str = Field(min_length=1, max_length=100)

    def to_domain(self) -> AlertSector:
        return AlertSector(id=self.id, name=self.name)


class _AlertEmployeeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    registration: str
    role: str | None
    shift: str | None
    sector: _AlertSectorDto | None

    def to_domain(self) -> AlertEmployee:
        return AlertEmployee(
            id=self.id,
            name=self.name,
            registration=self.registration,
            role=self.role,
            shift=self.shift,
            sector=self.sector.to_domain() if self.sector else None,
        )


class _AlertCameraDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    description: str | None
    sector: _AlertSectorDto | None

    def to_domain(self) -> AlertCamera:
        return AlertCamera(
            id=self.id,
            name=self.name,
            description=self.description,
            sector=self.sector.to_domain() if self.sector else None,
        )


class _AlertOccurrenceDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    type: str
    description: str | None
    confidence: float | None
    image_reference: str | None
    video_reference: str | None
    detected_at: AwareDatetime
    employee: _AlertEmployeeDto | None
    camera: _AlertCameraDto | None

    def to_domain(self) -> AlertOccurrence:
        return AlertOccurrence(
            id=self.id,
            type=self.type,
            description=self.description,
            confidence=self.confidence,
            image_reference=self.image_reference,
            video_reference=self.video_reference,
            detected_at=self.detected_at,
            employee=self.employee.to_domain() if self.employee else None,
            camera=self.camera.to_domain() if self.camera else None,
        )


class _AlertOperationalContextDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    work_session_id: UUID
    operation_id: PositiveInt
    risk_area_id: PositiveInt | None
    violation_type: str
    subject_key: str
    operator: _AlertActorDto | None
    received_at: AwareDatetime

    def to_domain(self) -> AlertOperationalContext:
        return AlertOperationalContext(
            event_id=self.event_id,
            work_session_id=self.work_session_id,
            operation_id=self.operation_id,
            risk_area_id=self.risk_area_id,
            violation_type=self.violation_type,
            subject_key=self.subject_key,
            operator=self.operator.to_domain() if self.operator else None,
            received_at=self.received_at,
        )


class _AdminAlertDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    category: Literal["ppe", "ergonomics", "monitoring", "risk_area", "safety"]
    level: Literal["warning", "critical"]
    status: Literal["nao_lido", "lido", "encerrado"]
    summary: str
    observation: str | None
    created_at: AwareDatetime
    received_at: AwareDatetime | None
    confirmed_at: AwareDatetime | None
    confirmed_by: _AlertActorDto | None
    closed_at: AwareDatetime | None
    closed_by: _AlertActorDto | None
    occurrence: _AlertOccurrenceDto
    operational_context: _AlertOperationalContextDto | None

    def to_domain(self) -> AdminAlert:
        return AdminAlert(
            id=self.id,
            category=self.category,
            level=self.level,
            status=self.status,
            summary=self.summary,
            observation=self.observation,
            created_at=self.created_at,
            received_at=self.received_at,
            confirmed_at=self.confirmed_at,
            confirmed_by=(self.confirmed_by.to_domain() if self.confirmed_by else None),
            closed_at=self.closed_at,
            closed_by=self.closed_by.to_domain() if self.closed_by else None,
            occurrence=self.occurrence.to_domain(),
            operational_context=(
                self.operational_context.to_domain() if self.operational_context else None
            ),
        )


class _AdminAlertPageDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[_AdminAlertDto, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    def to_domain(self) -> AdminAlertPage:
        return AdminAlertPage(
            items=tuple(item.to_domain() for item in self.items),
            total=self.total,
            limit=self.limit,
            offset=self.offset,
        )


class _EmployeeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    name: str
    registration: str
    role: str | None
    shift: str | None
    sector_id: PositiveInt
    sector_name: str
    active: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def to_domain(self) -> EmployeeRecord:
        return EmployeeRecord(**self.model_dump())


class _EmployeePageDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[_EmployeeDto, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    def to_domain(self) -> EmployeePage:
        return EmployeePage(
            tuple(item.to_domain() for item in self.items),
            self.total, self.limit, self.offset,
        )


class _FaceTemplateStatusDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: PositiveInt
    model_id: str
    enrolled_at: AwareDatetime

    def to_domain(self) -> FaceTemplateStatus:
        return FaceTemplateStatus(**self.model_dump())


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
        response = self._authorized_request("GET", "/admin/me", access_token=access_token)
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

    def get_alerts(
        self, access_token: str, *, limit: int = 100, offset: int = 0
    ) -> AdminAlertPage:
        response = self._authorized_request(
            "GET",
            "/admin/alerts",
            access_token=access_token,
            params={"limit": limit, "offset": offset},
        )
        self._ensure_protected_success(response, operation="admin_alerts")
        try:
            return _AdminAlertPageDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError(
                "A API retornou uma lista de alertas inválida."
            ) from error

    def get_employees(
        self, access_token: str, *, limit: int = 100, offset: int = 0
    ) -> EmployeePage:
        response = self._authorized_request(
            "GET", "/admin/employees", access_token=access_token,
            params={"limit": limit, "offset": offset},
        )
        self._ensure_protected_success(response, operation="admin_employees")
        try:
            return _EmployeePageDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError(
                "A API retornou funcionários inválidos."
            ) from error

    def save_employee(
        self, access_token: str, draft: EmployeeDraft, employee_id: int | None = None
    ) -> EmployeeRecord:
        response = self._authorized_request(
            "POST" if employee_id is None else "PUT",
            "/admin/employees" if employee_id is None else f"/admin/employees/{employee_id}",
            access_token=access_token,
            json={
                "name": draft.name,
                "registration": draft.registration,
                "role": draft.role,
                "shift": draft.shift,
                "sector_id": draft.sector_id,
                "active": draft.active,
            },
        )
        self._ensure_configuration_success(response, operation="employee_save")
        try:
            return _EmployeeDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError("A API retornou um funcionário inválido.") from error

    def get_face_template_status(
        self, access_token: str, employee_id: int
    ) -> FaceTemplateStatus | None:
        response = self._authorized_request(
            "GET", f"/admin/employees/{employee_id}/face-template", access_token=access_token
        )
        if response.status_code == 404:
            return None
        self._ensure_protected_success(response, operation="employee_face_status")
        try:
            return _FaceTemplateStatusDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError("A API retornou um Face ID inválido.") from error

    def save_face_template(
        self, access_token: str, employee_id: int, draft: FaceTemplateDraft
    ) -> FaceTemplateStatus:
        response = self._authorized_request(
            "PUT", f"/admin/employees/{employee_id}/face-template",
            access_token=access_token,
            json={"model_id": draft.model_id, "embedding": list(draft.embedding)},
        )
        self._ensure_configuration_success(response, operation="employee_face_save")
        try:
            return _FaceTemplateStatusDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError("A API retornou um Face ID inválido.") from error

    def get_alert(self, access_token: str, alert_id: int) -> AdminAlert:
        response = self._authorized_request(
            "GET",
            f"/admin/alerts/{alert_id}",
            access_token=access_token,
        )
        return self._alert_from_response(response, operation="admin_alert_detail")

    def confirm_alert(self, access_token: str, alert_id: int) -> AdminAlert:
        response = self._authorized_request(
            "PATCH",
            f"/admin/alerts/{alert_id}/confirm",
            access_token=access_token,
            json={},
        )
        return self._alert_from_response(response, operation="admin_alert_confirm")

    def close_alert(self, access_token: str, alert_id: int) -> AdminAlert:
        response = self._authorized_request(
            "PATCH",
            f"/admin/alerts/{alert_id}/close",
            access_token=access_token,
            json={},
        )
        return self._alert_from_response(response, operation="admin_alert_close")

    def get_active_operations(self, access_token: str) -> tuple[ActiveOperationSnapshot, ...]:
        response = self._authorized_request(
            "GET", "/admin/active-operations", access_token=access_token
        )
        self._ensure_protected_success(response, operation="active_operations")
        try:
            return parse_active_operations(response.content)
        except ValueError as error:
            raise InvalidApiResponseError(
                "A API retornou dados inválidos para as operações ativas."
            ) from error

    def get_operation_catalog(self, access_token: str) -> OperationCatalog:
        response = self._authorized_request(
            "GET", "/admin/operations/catalog", access_token=access_token
        )
        self._ensure_protected_success(response, operation="operation_catalog")
        return self._parse_operation_response(response, parse_catalog, "catálogo de operações")

    def create_camera(self, access_token: str, draft: CameraDraft) -> CameraOption:
        response = self._authorized_request(
            "POST",
            "/admin/cameras",
            access_token=access_token,
            json={
                "name": draft.name,
                "description": draft.description,
                "stream_source": draft.stream_source,
                "sector_id": draft.sector_id,
                "active": draft.active,
            },
        )
        self._ensure_configuration_success(response, operation="camera_create")
        return self._parse_operation_response(response, parse_camera, "câmera")

    def get_cameras(self, access_token: str) -> tuple[ManagedCamera, ...]:
        response = self._authorized_request("GET", "/admin/cameras", access_token=access_token)
        self._ensure_protected_success(response, operation="camera_list")
        return self._parse_operation_response(response, parse_managed_cameras, "lista de câmeras")

    def save_camera(
        self, access_token: str, draft: CameraDraft, camera_id: int
    ) -> ManagedCamera:
        response = self._authorized_request(
            "PUT",
            f"/admin/cameras/{camera_id}",
            access_token=access_token,
            json={
                "name": draft.name,
                "description": draft.description,
                "stream_source": draft.stream_source,
                "sector_id": draft.sector_id,
                "active": draft.active,
            },
        )
        self._ensure_configuration_success(response, operation="camera_update")
        return self._parse_operation_response(response, parse_managed_camera, "câmera")

    def get_risk_areas(self, access_token: str) -> tuple[RiskArea, ...]:
        response = self._authorized_request("GET", "/admin/risk-areas", access_token=access_token)
        self._ensure_protected_success(response, operation="risk_area_list")
        return self._parse_operation_response(response, parse_risk_areas, "lista de áreas de risco")

    def save_risk_area(
        self,
        access_token: str,
        draft: RiskAreaDraft,
        risk_area_id: int | None = None,
    ) -> RiskArea:
        response = self._authorized_request(
            "POST" if risk_area_id is None else "PUT",
            ("/admin/risk-areas" if risk_area_id is None else f"/admin/risk-areas/{risk_area_id}"),
            access_token=access_token,
            json={
                "camera_id": draft.camera_id,
                "name": draft.name,
                "geometry": draft.geometry.to_payload(),
                "active": draft.active,
            },
        )
        self._ensure_configuration_success(response, operation="risk_area_save")
        return self._parse_operation_response(response, parse_risk_area, "área de risco")

    def get_operations(self, access_token: str) -> tuple[OperationConfiguration, ...]:
        response = self._authorized_request("GET", "/admin/operations", access_token=access_token)
        self._ensure_protected_success(response, operation="operation_list")
        return self._parse_operation_response(response, parse_operations, "lista de operações")

    def save_operation(
        self,
        access_token: str,
        draft: OperationDraft,
        operation_id: int | None = None,
    ) -> OperationConfiguration:
        response = self._authorized_request(
            "POST" if operation_id is None else "PUT",
            ("/admin/operations" if operation_id is None else f"/admin/operations/{operation_id}"),
            access_token=access_token,
            json={
                "name": draft.name,
                "description": draft.description,
                "epi_ids": list(draft.epi_ids),
                "risk_area_id": draft.risk_area_id,
                "active": draft.active,
            },
        )
        self._ensure_configuration_success(response, operation="operation_save")
        return self._parse_operation_response(response, parse_operation, "operação")

    @staticmethod
    def _parse_operation_response(response, parser, label):
        try:
            return parser(response.json())
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError(
                f"A API retornou dados inválidos para {label}."
            ) from error

    @staticmethod
    def _ensure_configuration_success(response: httpx.Response, *, operation: str) -> None:
        if response.status_code == 404:
            raise ConfigurationNotFoundError("A configuração não foi encontrada.")
        if response.status_code == 409:
            detail = "A configuração conflita com um cadastro existente."
            try:
                received = response.json().get("detail")
                if isinstance(received, str) and received.strip():
                    detail = received.strip()
            except ValueError:
                pass
            raise ConfigurationConflictError(detail)
        AdminApiClient._ensure_protected_success(response, operation=operation)

    def _alert_from_response(
        self,
        response: httpx.Response,
        *,
        operation: str,
    ) -> AdminAlert:
        if response.status_code == 404:
            raise AlertNotFoundError("O alerta não foi encontrado.")
        if response.status_code == 409:
            raise AlertStateConflictError(
                "O alerta foi alterado e não permite essa ação. Atualize a lista."
            )
        self._ensure_protected_success(response, operation=operation)
        try:
            return _AdminAlertDto.model_validate(response.json()).to_domain()
        except (ValueError, ValidationError) as error:
            raise InvalidApiResponseError(
                "A API retornou dados inválidos para o alerta."
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
        **kwargs: Any,
    ) -> httpx.Response:
        if not access_token:
            raise SessionExpiredError("Sua sessão expirou. Entre novamente.")
        return self._request(
            method,
            path,
            headers={"Authorization": f"Bearer {access_token}"},
            **kwargs,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._closed:
            raise ApiUnavailableError("O cliente da API já foi encerrado.")

        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            logger.warning("Timeout na API", extra={"operation": path})
            raise ApiUnavailableError("A API demorou para responder. Tente novamente.") from error
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
        raise ApiUnavailableError("A API não conseguiu concluir a solicitação. Tente novamente.")

    def __enter__(self) -> AdminApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
