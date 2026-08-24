"""Global safety aggregation and ESP32 WebSocket integration."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import WebSocketDenialResponse

from app.api.dependencies import get_db
from app.core.security import AccessTokenService
from app.main import create_app
from app.models import Base, Usuario
from app.realtime import InMemoryRealtimeEventBroker, RealtimeMessage
from app.schemas.safety_state import OperatorSafetyStateSnapshot, SafetyStateMessage
from app.services import SafetyStateAggregator
from tests.test_authentication import LifecycleDatabase, make_settings

_DEVICE_TOKEN = "esp32-test-device-token-with-32-bytes"
_SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OBSERVED_AT = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


class RecordingBroker(InMemoryRealtimeEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[RealtimeMessage] = []

    async def publish(self, event: RealtimeMessage):  # type: ignore[no-untyped-def]
        self.published.append(event)
        return await super().publish(event)


def _snapshot(
    *conditions: tuple[str, str, str],
    session_id: UUID = _SESSION_ID,
) -> OperatorSafetyStateSnapshot:
    return OperatorSafetyStateSnapshot.model_validate(
        {
            "work_session_id": str(session_id),
            "operation_id": 12,
            "camera_id": 3,
            "observed_at": _OBSERVED_AT.isoformat(),
            "conditions": [
                {
                    "condition_id": condition_id,
                    "reason": reason,
                    "level": level,
                    "first_observed_at": (
                        _OBSERVED_AT - timedelta(seconds=5)
                    ).isoformat(),
                }
                for condition_id, reason, level in conditions
            ],
        }
    )


def test_aggregator_applies_global_priority_and_suppresses_duplicates() -> None:
    broker = RecordingBroker()
    clock_values = iter(
        _OBSERVED_AT + timedelta(seconds=offset) for offset in range(20)
    )
    aggregator = SafetyStateAggregator(broker, clock=lambda: next(clock_values))

    async def scenario() -> None:
        assert await aggregator.current() is None
        medium = await aggregator.update(
            operator_id=1,
            snapshot=_snapshot(("ppe:1", "PPE_MISSING", "medium")),
        )
        duplicate = await aggregator.update(
            operator_id=1,
            snapshot=_snapshot(("ppe:1", "PPE_MISSING", "medium")),
        )
        critical = await aggregator.update(
            operator_id=2,
            snapshot=_snapshot(
                ("ergonomics:trunk", "ERGONOMIC_RISK", "critical"),
                session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            ),
        )
        back_to_medium = await aggregator.update(
            operator_id=2,
            snapshot=_snapshot(
                session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
            ),
        )
        safe = await aggregator.update(
            operator_id=1,
            snapshot=_snapshot(),
        )

        assert medium.message.state == "YELLOW"
        assert duplicate.published is False
        assert critical.message.state == "RED"
        assert back_to_medium.message.state == "YELLOW"
        assert safe.message.state == "GREEN"
        assert [item.state for item in broker.published] == [
            "YELLOW",
            "RED",
            "YELLOW",
            "GREEN",
        ]

    asyncio.run(scenario())


@pytest.fixture
def safety_api() -> Iterator[tuple[TestClient, str]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings(safety_device_token=_DEVICE_TOKEN)
    application = create_app(
        settings=settings,
        database=LifecycleDatabase(),
        safety_state_broker=InMemoryRealtimeEventBroker(),
    )

    def override_get_db() -> Iterator[Session]:
        with sessions() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    now = datetime.now(UTC)
    with sessions.begin() as session:
        account = Usuario(
            nome="Operador Sinalizador",
            username="operador.sinalizador",
            senha_hash=bcrypt.hashpw(b"senha", bcrypt.gensalt()).decode(),
            perfil="operador",
            ativo=True,
            criado_em=now,
            atualizado_em=now,
        )
        session.add(account)
    access_token = AccessTokenService(settings).issue(
        subject=account.id,
        name=account.nome,
        profile="operador",
    )
    with TestClient(application) as client:
        yield client, access_token
    application.dependency_overrides.clear()
    engine.dispose()


def test_device_receives_current_state_changes_and_reconnect_snapshot(safety_api) -> None:
    client, access_token = safety_api
    device_headers = {"Authorization": f"Bearer {_DEVICE_TOKEN}"}
    operator_headers = {"Authorization": f"Bearer {access_token}"}

    initialized = client.put(
        "/operator/safety-state",
        json=_snapshot().model_dump(mode="json"),
        headers=operator_headers,
    )
    assert initialized.status_code == 200
    assert initialized.json()["state"] == "GREEN"

    with client.websocket_connect(
        "/ws/devices/safety",
        headers=device_headers,
    ) as websocket:
        assert websocket.receive_json()["state"] == "GREEN"
        response = client.put(
            "/operator/safety-state",
            json=_snapshot(
                ("risk-area:4", "PERSON_IN_RISK_AREA", "critical")
            ).model_dump(mode="json"),
            headers=operator_headers,
        )
        assert response.status_code == 200
        assert websocket.receive_json()["state"] == "RED"

    with client.websocket_connect(
        "/ws/devices/safety",
        headers=device_headers,
    ) as reconnected:
        current = SafetyStateMessage.model_validate(
            reconnected.receive_json(),
            strict=False,
        )
        assert current.state == "RED"
        assert current.reason == "PERSON_IN_RISK_AREA"


def test_device_websocket_rejects_missing_token(safety_api) -> None:
    client, _access_token = safety_api
    with (
        pytest.raises(WebSocketDenialResponse) as denied,
        client.websocket_connect("/ws/devices/safety"),
    ):
        pass
    assert denied.value.status_code == 401
