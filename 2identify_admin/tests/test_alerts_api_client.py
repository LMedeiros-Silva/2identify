from __future__ import annotations

import httpx

from app.api import AdminApiClient
from app.core.config import Settings

TOKEN = "header.payload.signature"


def settings() -> Settings:
    return Settings(_env_file=None, API_URL="https://api.example.test")  # type: ignore[call-arg]


def alert_payload(status: str = "nao_lido") -> dict[str, object]:
    return {
        "id": 20,
        "category": "ergonomics",
        "level": "critical",
        "status": status,
        "summary": "Tronco inclinado 52°",
        "observation": "Triagem automática",
        "created_at": "2026-08-23T14:30:00Z",
        "received_at": "2026-08-23T14:30:01Z",
        "confirmed_at": "2026-08-23T14:31:00Z" if status != "nao_lido" else None,
        "confirmed_by": (
            {"id": 1, "name": "Admin"} if status != "nao_lido" else None
        ),
        "closed_at": "2026-08-23T14:35:00Z" if status == "encerrado" else None,
        "closed_by": {"id": 1, "name": "Admin"} if status == "encerrado" else None,
        "occurrence": {
            "id": 10,
            "type": "ergonomic_risk",
            "description": "Postura inadequada",
            "confidence": 0.94,
            "image_reference": "evidencias/10.jpg",
            "video_reference": None,
            "detected_at": "2026-08-23T14:30:00Z",
            "employee": {
                "id": 4,
                "name": "Funcionário",
                "registration": "MAT-004",
                "role": "Montador",
                "shift": "Manhã",
                "sector": {"id": 3, "name": "Montagem"},
            },
            "camera": {
                "id": 5,
                "name": "Câmera 5",
                "description": "Linha",
                "sector": {"id": 3, "name": "Montagem"},
            },
        },
        "operational_context": {
            "event_id": "4d36a6ee-6e78-4e22-95b5-176276f2d21d",
            "work_session_id": "d9badffe-415b-4e29-b0af-129bf44437ef",
            "operation_id": 12,
            "risk_area_id": 7,
            "violation_type": "ergonomic_risk",
            "subject_key": "ergonomics:trunk_inclination",
            "operator": {"id": 2, "name": "Operador"},
            "received_at": "2026-08-23T14:30:01Z",
        },
    }


def test_alert_client_lists_confirms_and_closes_with_admin_bearer() -> None:
    paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append((request.method, request.url.path))
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"items": [alert_payload()], "total": 1, "limit": 100, "offset": 0},
            )
        assert request.content == b"{}"
        status = "lido" if request.url.path.endswith("/confirm") else "encerrado"
        return httpx.Response(200, json=alert_payload(status))

    with AdminApiClient(
        settings(),
        transport=httpx.MockTransport(handler),
    ) as client:
        page = client.get_alerts(TOKEN)
        confirmed = client.confirm_alert(TOKEN, 20)
        closed = client.close_alert(TOKEN, 20)

    assert page.items[0].occurrence.employee is not None
    assert page.items[0].occurrence.employee.registration == "MAT-004"
    assert confirmed.status == "lido"
    assert confirmed.confirmed_by is not None
    assert closed.status == "encerrado"
    assert paths == [
        ("GET", "/admin/alerts"),
        ("PATCH", "/admin/alerts/20/confirm"),
        ("PATCH", "/admin/alerts/20/close"),
    ]
