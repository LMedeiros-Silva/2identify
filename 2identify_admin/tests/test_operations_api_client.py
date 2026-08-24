from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.api import AdminApiClient
from app.core.config import Settings
from app.domain import (
    CameraDraft,
    NormalizedPoint,
    OperationDraft,
    PolygonGeometry,
    RiskAreaDraft,
)


def _settings() -> Settings:
    return Settings(
        api_base_url="http://api.test",
        app_env="testing",
        _env_file=None,
    )


def _area_payload() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": 10,
        "camera_id": 5,
        "camera_name": "Linha A",
        "name": "Área principal",
        "geometry": {
            "type": "polygon",
            "points": [[0.1, 0.1], [0.8, 0.1], [0.5, 0.8]],
        },
        "active": True,
        "created_at": now,
        "updated_at": now,
    }


def test_client_sends_normalized_area_only_through_authenticated_api() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(201, json=_area_payload())

    geometry = PolygonGeometry(
        (
            NormalizedPoint(0.1, 0.1),
            NormalizedPoint(0.8, 0.1),
            NormalizedPoint(0.5, 0.8),
        )
    )
    with AdminApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        area = client.save_risk_area("secret-token", RiskAreaDraft(5, "Área principal", geometry))

    assert area.geometry == geometry
    assert received[0].headers["authorization"] == "Bearer secret-token"
    assert received[0].url.path == "/admin/risk-areas"
    assert received[0].read().decode().count("0.1") >= 2


def test_client_registers_camera_only_through_authenticated_api() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(
            201,
            json={
                "id": 7,
                "name": "Webcam USB",
                "description": "Teste",
                "stream_source": "0",
            },
        )

    draft = CameraDraft("Webcam USB", "Teste", "0", 1)
    with AdminApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        camera = client.create_camera("secret-token", draft)

    assert camera.id == 7
    assert camera.stream_source == "0"
    assert received[0].headers["authorization"] == "Bearer secret-token"
    assert received[0].url.path == "/admin/cameras"
    assert '"sector_id":1' in received[0].read().decode()


def test_client_updates_operation_with_epi_and_risk_area_ids() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        now = datetime.now(UTC).isoformat()
        return httpx.Response(
            200,
            json={
                "id": 20,
                "name": "Soldagem",
                "description": None,
                "required_ppe": [{"id": 1, "name": "Capacete", "code": "CAP", "description": None}],
                "risk_area": _area_payload(),
                "active": True,
                "created_at": now,
                "updated_at": now,
            },
        )

    with AdminApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        operation = client.save_operation(
            "secret-token", OperationDraft("Soldagem", None, (1,), 10), 20
        )

    assert operation.id == 20
    assert received[0].method == "PUT"
    assert received[0].url.path == "/admin/operations/20"
    assert '"epi_ids":[1]' in received[0].read().decode()
