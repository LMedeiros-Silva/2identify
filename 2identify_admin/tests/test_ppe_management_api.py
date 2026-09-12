from __future__ import annotations

from datetime import UTC

import httpx

from app.api import AdminApiClient
from app.core.config import Settings
from app.domain.ppe_management import ActiveOperationOverallStatus, PpeLiveState


def test_client_loads_authoritative_active_operation_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/active-operations"
        assert request.headers["Authorization"] == "Bearer token-admin"
        return httpx.Response(
            200,
            json=[
                {
                    "work_session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "session_status": "active",
                    "operator_id": 15,
                    "operator_name": "Breno Barbosa",
                    "operation_id": 7,
                    "operation_name": "Linha de montagem",
                    "started_at": "2026-08-25T12:00:00Z",
                    "observed_at": "2026-08-25T12:00:05Z",
                    "camera_id": 3,
                    "camera_name": "Câmera Linha A",
                    "ppe": [
                        {"ppe_id": 1, "name": "Capacete", "state": "confirmed"},
                        {"ppe_id": 2, "name": "Luvas", "state": "absent"},
                    ],
                    "overall_status": "non_compliant",
                }
            ],
        )

    settings = Settings(_env_file=None, API_URL="https://api.example.test")  # type: ignore[call-arg]
    with AdminApiClient(settings, transport=httpx.MockTransport(handler)) as client:
        result = client.get_active_operations("token-admin")

    assert len(result) == 1
    assert result[0].operator_name == "Breno Barbosa"
    assert result[0].started_at.tzinfo == UTC
    assert result[0].ppe[0].state is PpeLiveState.CONFIRMED
    assert result[0].overall_status is ActiveOperationOverallStatus.NON_COMPLIANT
