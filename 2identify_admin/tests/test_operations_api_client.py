from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from app.api import AdminApiClient
from app.core.config import Settings
from app.domain import (
    CameraDraft,
    ManagedCamera,
    NormalizedPoint,
    OperationCatalog,
    OperationDraft,
    PolygonGeometry,
    RiskAreaDraft,
)
from app.services.admin_operations_service import AdminOperationsService


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


def test_client_lists_and_updates_inactive_camera_through_api() -> None:
    received: list[httpx.Request] = []
    camera = {
        "id": 7,
        "name": "Webcam USB",
        "description": "Teste",
        "stream_source": "0",
        "sector_id": 1,
        "active": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[camera])
        return httpx.Response(200, json={**camera, "sector_id": 2, "active": True})

    with AdminApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        listed = client.get_cameras("secret-token")
        saved = client.save_camera(
            "secret-token", CameraDraft("Webcam USB", "Teste", "0", 2), 7
        )

    assert len(listed) == 1 and listed[0].active is False
    assert saved.sector_id == 2 and saved.active is True
    assert [(request.method, request.url.path) for request in received] == [
        ("GET", "/admin/cameras"),
        ("PUT", "/admin/cameras/7"),
    ]
    assert all(request.headers["authorization"] == "Bearer secret-token" for request in received)


def test_operations_service_loads_managed_cameras_and_routes_update() -> None:
    camera = ManagedCamera(7, "USB", "0", None, 1, False)
    provider = SimpleNamespace(
        get_operation_catalog=lambda token: OperationCatalog((), ()),
        get_risk_areas=lambda token: (),
        get_operations=lambda token: (),
        get_cameras=lambda token: (camera,),
        save_camera=lambda token, draft, camera_id: ManagedCamera(
            camera_id, draft.name, draft.stream_source, draft.description,
            draft.sector_id, draft.active,
        ),
    )
    service = AdminOperationsService(provider)
    assert service.load("token")[3] == (camera,)
    saved = service.save_camera("token", CameraDraft("USB", None, "0", 1, True), 7)
    assert saved.id == 7 and saved.active is True


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
