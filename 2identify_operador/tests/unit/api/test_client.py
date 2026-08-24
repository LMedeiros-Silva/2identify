import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.api.client import OperatorApiClient
from app.domain import (
    LoginCredentials,
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolation,
    SafetyViolationType,
)
from app.services.alert_delivery_service import (
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
from app.services.safety_state_service import (
    HardwareSafetyState,
    SafetyConditionState,
    SafetyStateLevel,
    SafetyStateReason,
    SafetyStateSnapshot,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> OperatorApiClient:
    return OperatorApiClient(
        base_url="https://api.example.test/v1",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=2.0,
        transport=httpx.MockTransport(handler),
    )


def _ergonomic_alert() -> SafetyAlert:
    detected_at = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)
    return SafetyAlert(
        alert_id=UUID("11111111-1111-4111-8111-111111111111"),
        work_session_id=UUID("22222222-2222-4222-8222-222222222222"),
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=8,
        violation=SafetyViolation(
            SafetyViolationType.ERGONOMIC_RISK,
            "ergonomics:trunk_inclination",
            "Risco ergonômico: tronco inclinado 52° em relação à vertical",
            SafetyAlertSeverity.CRITICAL,
        ),
        first_observed_at=detected_at,
        raised_at=detected_at,
        resolved_at=None,
        status=SafetyAlertStatus.ACTIVE,
    )


def _risk_area_alert() -> SafetyAlert:
    detected_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    return SafetyAlert(
        alert_id=UUID("33333333-3333-4333-8333-333333333333"),
        work_session_id=UUID("44444444-4444-4444-8444-444444444444"),
        operator_id=15,
        operation_id=41,
        camera_id=3,
        risk_area_id=8,
        violation=SafetyViolation(
            SafetyViolationType.PERSON_IN_RISK_AREA,
            "risk_area:8",
            "Pessoa detectada na área de risco: Linha A",
            SafetyAlertSeverity.CRITICAL,
        ),
        first_observed_at=detected_at,
        raised_at=detected_at,
        resolved_at=None,
        status=SafetyAlertStatus.ACTIVE,
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


def test_list_operations_maps_api_catalog_with_ppe_and_calibrated_risk_area() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.test/v1/operator/operations"
        assert request.headers["Authorization"] == "Bearer token-operador"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 41,
                    "name": "Soldagem industrial",
                    "description": "Solda controlada",
                    "required_ppe": [
                        {
                            "id": 1,
                            "name": "Capacete",
                            "code": "EPI-001",
                            "description": "Capacete de segurança.",
                        },
                        {
                            "id": 5,
                            "name": "Óculos de proteção",
                            "code": "EPI-005",
                            "description": None,
                        },
                    ],
                    "risk_area": {
                        "id": 8,
                        "camera_id": 3,
                        "camera_name": "Webcam USB",
                        "name": "Célula de solda",
                        "geometry": {
                            "type": "polygon",
                            "points": [[0.1, 0.2], [0.8, 0.2], [0.7, 0.9]],
                        },
                        "active": True,
                        "created_at": "2026-08-24T12:00:00Z",
                        "updated_at": "2026-08-24T12:00:00Z",
                    },
                    "active": True,
                    "created_at": "2026-08-24T12:00:00Z",
                    "updated_at": "2026-08-24T12:00:00Z",
                }
            ],
        )

    client = _client(handler)

    operations = client.list_operations("token-operador")

    assert len(operations) == 1
    operation = operations[0]
    assert operation.operation_id == 41
    assert [item.detection_class for item in operation.required_ppe] == [
        "capacete",
        "oculos",
    ]
    assert operation.risk_area is not None
    assert operation.risk_area.camera_id == 3
    assert operation.risk_area.camera_name == "Webcam USB"
    assert operation.risk_area.geometry_calibrated
    assert operation.risk_area.geometry is not None
    assert [(point.x, point.y) for point in operation.risk_area.geometry.vertices] == [
        (0.1, 0.2),
        (0.8, 0.2),
        (0.7, 0.9),
    ]
    client.close()


def test_list_operations_with_catalog_token_uses_read_only_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://api.example.test/v1/operator/operations/catalog"
        )
        assert request.headers["Authorization"] == "Bearer catalog-token"
        return httpx.Response(200, json=[])

    client = _client(handler)

    assert client.list_operations_with_catalog_token("catalog-token") == ()
    client.close()


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_list_operations_maps_api_failures(status_code: int) -> None:
    client = _client(lambda _request: httpx.Response(status_code))

    with pytest.raises(OperationsUnavailableError):
        client.list_operations("token-operador")

    client.close()


def test_list_operations_rejects_invalid_geometry() -> None:
    client = _client(
        lambda _request: httpx.Response(
            200,
            json=[
                {
                    "id": 41,
                    "name": "Operação inválida",
                    "description": None,
                    "required_ppe": [],
                    "risk_area": {
                        "id": 8,
                        "camera_id": 3,
                        "camera_name": "Webcam USB",
                        "name": "Área inválida",
                        "geometry": {
                            "type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
                        },
                        "active": True,
                        "created_at": "2026-08-24T12:00:00Z",
                        "updated_at": "2026-08-24T12:00:00Z",
                    },
                    "active": True,
                    "created_at": "2026-08-24T12:00:00Z",
                    "updated_at": "2026-08-24T12:00:00Z",
                }
            ],
        )
    )

    with pytest.raises(InvalidOperationDataError):
        client.list_operations("token-operador")

    client.close()


def test_send_alert_uses_bearer_and_maps_idempotent_receipt() -> None:
    alert = _ergonomic_alert()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.test/v1/operator/alerts"
        assert request.headers["Authorization"] == "Bearer token-operador"
        payload = json.loads(request.content)
        assert payload["event_id"] == str(alert.alert_id)
        assert payload["violation_type"] == "ergonomic_risk"
        assert payload["severity"] == "critical"
        return httpx.Response(
            201,
            json={
                "event_id": str(alert.alert_id),
                "alert_id": 19,
                "occurrence_id": 22,
                "duplicate": False,
            },
        )

    client = _client(handler)

    receipt = client.send_alert(alert, "token-operador")

    assert receipt.event_id == alert.alert_id
    assert receipt.alert_id == 19
    assert receipt.occurrence_id == 22
    client.close()


def test_send_risk_area_alert_includes_camera_and_area_context() -> None:
    alert = _risk_area_alert()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["violation_type"] == "person_in_risk_area"
        assert payload["subject_key"] == "risk_area:8"
        assert payload["camera_id"] == 3
        assert payload["risk_area_id"] == 8
        return httpx.Response(
            201,
            json={
                "event_id": str(alert.alert_id),
                "alert_id": 25,
                "occurrence_id": 31,
                "duplicate": False,
            },
        )

    client = _client(handler)

    receipt = client.send_alert(alert, "token-operador")

    assert receipt.alert_id == 25
    assert receipt.occurrence_id == 31
    client.close()


@pytest.mark.parametrize("status_code", [401, 403, 409, 422])
def test_send_alert_maps_permanent_rejections(status_code: int) -> None:
    client = _client(lambda _request: httpx.Response(status_code))

    with pytest.raises(AlertDeliveryRejectedError):
        client.send_alert(_ergonomic_alert(), "token-operador")

    client.close()


def test_send_alert_maps_network_failure_as_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("host confidencial", request=request)

    client = _client(handler)

    with pytest.raises(AlertDeliveryUnavailableError, match="indisponível"):
        client.send_alert(_ergonomic_alert(), "token-operador")

    client.close()


def test_send_safety_state_uses_authenticated_complete_snapshot() -> None:
    observed_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    snapshot = SafetyStateSnapshot(
        work_session_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        operation_id=41,
        camera_id=3,
        observed_at=observed_at,
        conditions=(
            SafetyConditionState(
                condition_id="risk_area:8",
                reason=SafetyStateReason.PERSON_IN_RISK_AREA,
                level=SafetyStateLevel.CRITICAL,
                first_observed_at=observed_at,
            ),
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.test/v1/operator/safety-state"
        assert request.method == "PUT"
        assert request.headers["Authorization"] == "Bearer token-operador"
        payload = json.loads(request.content)
        assert payload["work_session_id"] == str(snapshot.work_session_id)
        assert payload["conditions"] == [
            {
                "condition_id": "risk_area:8",
                "reason": "PERSON_IN_RISK_AREA",
                "level": "critical",
                "first_observed_at": observed_at.isoformat(),
            }
        ]
        return httpx.Response(
            200,
            json={
                "type": "safety_state",
                "schema_version": 1,
                "state": "RED",
                "reason": "PERSON_IN_RISK_AREA",
                "active_conditions": 1,
                "updated_at": observed_at.isoformat(),
            },
        )

    client = _client(handler)
    receipt = client.send_safety_state(snapshot, "token-operador")

    assert receipt.state is HardwareSafetyState.RED
    assert receipt.reason is SafetyStateReason.PERSON_IN_RISK_AREA
    assert receipt.active_conditions == 1
    client.close()
