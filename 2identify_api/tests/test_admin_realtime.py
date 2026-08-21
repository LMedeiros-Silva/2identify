"""Authenticated administrative WebSocket and internal broker tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.database import get_db
from app.core.security import AccessTokenService
from app.main import create_app
from app.models import Base, Usuario
from app.realtime import (
    BrokerCapacityError,
    DatabaseAdminRealtimeAuthorizer,
    InMemoryRealtimeEventBroker,
)
from app.schemas.realtime import (
    AlertCreatedPayload,
    RealtimeEventEnvelope,
    StreamHeartbeatPayload,
    StreamReadyPayload,
)
from app.services import AdministratorPrincipal

TEST_SECRET = "realtime-test-secret-with-at-least-32-bytes"
ADMIN_PRINCIPAL = AdministratorPrincipal(
    account_id=77,
    name="Administrador Teste",
    username="admin.teste",
    profile="administrador",
)


class LifecycleDatabase:
    def check_connection(self) -> None:
        return None

    def dispose(self) -> None:
        return None


class StaticAuthorizer:
    def authorize(self, _token: str) -> AdministratorPrincipal:
        return ADMIN_PRINCIPAL


class UnavailableAuthorizer:
    def authorize(self, _token: str) -> AdministratorPrincipal:
        raise SQLAlchemyError("database unavailable")


class BecomesUnavailableAuthorizer:
    def __init__(self) -> None:
        self.calls = 0

    def authorize(self, _token: str) -> AdministratorPrincipal:
        self.calls += 1
        if self.calls > 1:
            raise SQLAlchemyError("database unavailable")
        return ADMIN_PRINCIPAL


def make_settings() -> Settings:
    return Settings(
        database_url=(
            "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
        ),
        app_env="testing",
        auth_token_secret=TEST_SECRET,
        auth_token_audience="2identify-operator",
        auth_admin_token_audience="2identify-admin",
        auth_allowed_profiles="operador",
        realtime_heartbeat_interval_seconds=0.05,
        _env_file=None,
    )


@pytest.fixture
def realtime_api() -> Iterator[
    tuple[
        FastAPI,
        sessionmaker[Session],
        Settings,
        InMemoryRealtimeEventBroker,
    ]
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings()
    broker = InMemoryRealtimeEventBroker()
    application = create_app(
        settings=settings,
        database=LifecycleDatabase(),
        realtime_event_broker=broker,
        admin_realtime_authorizer=DatabaseAdminRealtimeAuthorizer(
            sessions,
            settings,
        ),
    )

    def override_get_db() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    yield application, sessions, settings, broker
    application.dependency_overrides.clear()
    engine.dispose()


def add_account(
    sessions: sessionmaker[Session],
    *,
    username: str,
    profile: str,
    active: bool = True,
) -> int:
    now = datetime.now(UTC)
    account = Usuario(
        nome="Administrador Teste" if profile == "administrador" else "Operador Teste",
        username=username,
        senha_hash=bcrypt.hashpw(b"senha-segura", bcrypt.gensalt()).decode(),
        perfil=profile,
        ativo=active,
        criado_em=now,
        atualizado_em=now,
    )
    with sessions() as session:
        session.add(account)
        session.commit()
        return account.id


def issue_token(
    settings: Settings,
    *,
    account_id: int,
    profile: str,
    admin_audience: bool,
) -> str:
    audience = (
        settings.auth_admin_token_audience
        if admin_audience
        else settings.auth_token_audience
    )
    return AccessTokenService(settings, audience=audience).issue(
        subject=account_id,
        name="Administrador Teste" if profile == "administrador" else "Operador Teste",
        profile=profile,
    )


def assert_websocket_rejected(
    client: TestClient,
    *,
    path: str = "/ws/admin/alerts",
    token: str | None = None,
    explicit_headers: object | None = None,
    expected_status: int = 401,
) -> None:
    headers: object = (
        {"Authorization": f"Bearer {token}"} if token is not None else {}
    )
    if explicit_headers is not None:
        headers = explicit_headers
    with (
        pytest.raises(WebSocketDenialResponse) as rejected,
        client.websocket_connect(path, headers=headers),
    ):
        pytest.fail("WebSocket não autorizado foi aceito")
    assert rejected.value.status_code == expected_status


def test_websocket_requires_authorization_header_and_ignores_query_token(
    realtime_api,
    caplog,
) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )

    with TestClient(application) as client:
        assert_websocket_rejected(client)
        assert_websocket_rejected(
            client,
            path=f"/ws/admin/alerts?token={token}",
            expected_status=400,
        )
        assert_websocket_rejected(
            client,
            path=f"/ws/admin/alerts?token={token}",
            token=token,
            expected_status=400,
        )
        assert_websocket_rejected(
            client,
            path="/ws/admin/alerts?unexpected=1",
            token=token,
            expected_status=400,
        )
    assert token not in caplog.text


@pytest.mark.parametrize(
    "authorization",
    ["Basic opaque", "Bearer", "Bearer first second", "Bearer  duplicated-space"],
)
def test_malformed_authorization_header_is_rejected(
    realtime_api,
    authorization: str,
) -> None:
    application, _sessions, _settings, _broker = realtime_api

    with TestClient(application) as client:
        assert_websocket_rejected(
            client,
            explicit_headers={"Authorization": authorization},
        )


def test_multiple_authorization_headers_are_rejected(realtime_api) -> None:
    application, _sessions, _settings, _broker = realtime_api
    headers = httpx.Headers(
        [
            ("Authorization", "Bearer first"),
            ("Authorization", "Bearer second"),
        ]
    )

    with TestClient(application) as client:
        assert_websocket_rejected(client, explicit_headers=headers)


def test_operator_token_cannot_open_admin_websocket(realtime_api) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="operador", profile="operador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="operador",
        admin_audience=False,
    )

    with TestClient(application) as client:
        assert_websocket_rejected(client, token=token)


def test_tampered_and_expired_admin_tokens_are_rejected(realtime_api) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    valid = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )
    token_parts = valid.split(".")
    replacement = "A" if token_parts[2][0] != "A" else "B"
    token_parts[2] = f"{replacement}{token_parts[2][1:]}"
    tampered = ".".join(token_parts)

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(account_id),
            "name": "Administrador Teste",
            "profile": "administrador",
            "iat": now - timedelta(minutes=2),
            "nbf": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
            "iss": settings.auth_token_issuer,
            "aud": settings.auth_admin_token_audience,
            "jti": "expired-realtime-test-token",
        },
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )

    with TestClient(application) as client:
        assert_websocket_rejected(client, token=tampered)
        assert_websocket_rejected(client, token=expired)


def test_websocket_rechecks_active_administrator_account(realtime_api) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )
    with sessions.begin() as session:
        session.execute(
            update(Usuario).where(Usuario.id == account_id).values(ativo=False)
        )

    with TestClient(application) as client:
        assert_websocket_rejected(client, token=token)


def test_database_unavailable_denies_handshake_without_leaking_token(caplog) -> None:
    token = "opaque-handshake-secret"
    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=InMemoryRealtimeEventBroker(),
        admin_realtime_authorizer=UnavailableAuthorizer(),
    )

    with TestClient(application) as client:
        assert_websocket_rejected(client, token=token, expected_status=503)

    assert token not in caplog.text


def test_database_unavailable_during_heartbeat_closes_accepted_stream() -> None:
    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=InMemoryRealtimeEventBroker(),
        admin_realtime_authorizer=BecomesUnavailableAuthorizer(),
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": "Bearer opaque-admin-token"},
        ) as websocket,
    ):
        assert websocket.receive_json()["event_type"] == "connection.ready"
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 1011


def test_closed_broker_closes_accepted_stream_with_1012() -> None:
    broker = InMemoryRealtimeEventBroker()
    asyncio.run(broker.close(code=1012, reason="preclosed for test"))
    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=broker,
        admin_realtime_authorizer=StaticAuthorizer(),
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": "Bearer opaque-admin-token"},
        ) as websocket,
        pytest.raises(WebSocketDisconnect) as disconnected,
    ):
        websocket.receive_json()

    assert disconnected.value.code == 1012


def test_application_lifespan_closes_realtime_broker_with_1012() -> None:
    class RecordingBroker(InMemoryRealtimeEventBroker):
        def __init__(self) -> None:
            super().__init__()
            self.shutdown_code: int | None = None

        async def close(self, *, code: int, reason: str) -> None:
            self.shutdown_code = code
            await super().close(code=code, reason=reason)

    broker = RecordingBroker()
    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=broker,
        admin_realtime_authorizer=StaticAuthorizer(),
    )

    with TestClient(application):
        assert broker.shutdown_code is None

    assert broker.shutdown_code == 1012


def test_connection_capacity_closes_overloaded_stream_with_1013() -> None:
    broker = InMemoryRealtimeEventBroker(
        max_connections=1,
        max_connections_per_owner=1,
    )
    application = create_app(
        settings=make_settings(),
        database=LifecycleDatabase(),
        realtime_event_broker=broker,
        admin_realtime_authorizer=StaticAuthorizer(),
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": "Bearer first-admin-token"},
        ) as first,
    ):
        assert first.receive_json()["event_type"] == "connection.ready"
        with (
            client.websocket_connect(
                "/ws/admin/alerts",
                headers={"Authorization": "Bearer second-admin-token"},
            ) as overloaded,
            pytest.raises(WebSocketDisconnect) as disconnected,
        ):
            overloaded.receive_json()

        assert disconnected.value.code == 1013
        assert broker.subscriber_count == 1


def test_authenticated_connection_emits_ready_and_heartbeat_and_is_removed(
    realtime_api,
) -> None:
    application, sessions, settings, broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )

    with TestClient(application) as client:
        with client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket:
            ready = RealtimeEventEnvelope.model_validate_json(
                json.dumps(websocket.receive_json())
            )
            assert ready.schema_version == 1
            assert ready.event_type == "connection.ready"
            assert ready.occurred_at.tzinfo is not None
            assert isinstance(ready.event_id, UUID)
            assert ready.payload == StreamReadyPayload(
                status="awaiting_alert_ingestion"
            )
            assert broker.subscriber_count == 1

            heartbeat = RealtimeEventEnvelope.model_validate_json(
                json.dumps(websocket.receive_json())
            )
            assert heartbeat.schema_version == 1
            assert heartbeat.event_type == "connection.heartbeat"
            assert heartbeat.event_id != ready.event_id
            assert heartbeat.payload == StreamHeartbeatPayload()

        assert broker.subscriber_count == 0


def test_client_frames_are_rejected_as_protocol_violation(realtime_api) -> None:
    application, sessions, settings, broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket,
    ):
        assert websocket.receive_json()["event_type"] == "connection.ready"
        websocket.send_text("client-command-is-not-supported")
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 1008
    assert broker.subscriber_count == 0


def test_client_binary_frame_is_rejected_as_unsupported_data(realtime_api) -> None:
    application, sessions, settings, broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket,
    ):
        assert websocket.receive_json()["event_type"] == "connection.ready"
        websocket.send_bytes(b"client-binary-frame")
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 1003
    assert broker.subscriber_count == 0


def test_periodic_revalidation_disconnects_account_disabled_after_handshake(
    realtime_api,
) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    token = issue_token(
        settings,
        account_id=account_id,
        profile="administrador",
        admin_audience=True,
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket,
    ):
        ready = websocket.receive_json()
        assert ready["event_type"] == "connection.ready"
        with sessions.begin() as session:
            session.execute(
                update(Usuario).where(Usuario.id == account_id).values(ativo=False)
            )
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 4401


def test_periodic_revalidation_disconnects_token_that_expires_during_stream(
    realtime_api,
) -> None:
    application, sessions, settings, _broker = realtime_api
    account_id = add_account(sessions, username="admin", profile="administrador")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(account_id),
            "name": "Administrador Teste",
            "profile": "administrador",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=1),
            "iss": settings.auth_token_issuer,
            "aud": settings.auth_admin_token_audience,
            "jti": "short-lived-realtime-test-token",
        },
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )

    with (
        TestClient(application) as client,
        client.websocket_connect(
            "/ws/admin/alerts",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket,
    ):
        assert websocket.receive_json()["event_type"] == "connection.ready"
        with pytest.raises(WebSocketDisconnect) as disconnected:
            while True:
                websocket.receive_json()

    assert disconnected.value.code == 4401


def test_internal_broker_fans_out_and_removes_failed_sink() -> None:
    class RecordingSink:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail
            self.events: list[RealtimeEventEnvelope] = []
            self.closed = False
            self.closed_code: int | None = None

        async def send(self, event: RealtimeEventEnvelope) -> None:
            if self.fail:
                raise RuntimeError("destination unavailable")
            self.events.append(event)

        async def close(self, *, code: int, reason: str) -> None:
            self.closed = True
            self.closed_code = code

    async def scenario() -> None:
        broker = InMemoryRealtimeEventBroker()
        healthy = RecordingSink()
        failed = RecordingSink(fail=True)
        await broker.subscribe(healthy)
        await broker.subscribe(failed)
        event = RealtimeEventEnvelope(
            event_type="alert.created",
            payload=AlertCreatedPayload(
                alert_id=7,
                occurrence_id=11,
                level="critical",
                status="nao_lido",
                summary="Capacete ausente",
                detected_at=datetime.now(UTC),
                camera_id=None,
            ),
        )

        report = await broker.publish(event)
        for _ in range(10):
            if broker.subscriber_count == 1 and healthy.events:
                break
            await asyncio.sleep(0)

        assert report.attempted == 2
        assert report.enqueued == 2
        assert report.disconnected == 0
        assert healthy.events == [event]
        assert broker.subscriber_count == 1
        await broker.close(code=1012, reason="test shutdown")
        assert healthy.closed is True
        assert healthy.closed_code == 1012
        assert broker.subscriber_count == 0

    asyncio.run(scenario())


def test_broker_disconnects_slow_subscriber_with_1013_on_queue_overflow() -> None:
    class SlowSink:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.closed_code: int | None = None

        async def send(self, _event: RealtimeEventEnvelope) -> None:
            self.started.set()
            await self.release.wait()

        async def close(self, *, code: int, reason: str) -> None:
            self.closed_code = code

    async def scenario() -> None:
        broker = InMemoryRealtimeEventBroker(queue_capacity=1)
        sink = SlowSink()
        subscription_id = await broker.subscribe(sink)
        event = RealtimeEventEnvelope(
            event_type="connection.heartbeat",
            payload=StreamHeartbeatPayload(),
        )

        assert await broker.send_to(subscription_id, event) is True
        await sink.started.wait()
        assert await broker.send_to(subscription_id, event) is True
        assert await broker.send_to(subscription_id, event) is False

        assert sink.closed_code == 1013
        assert broker.subscriber_count == 0

    asyncio.run(scenario())


def test_broker_enforces_global_and_per_admin_connection_limits() -> None:
    class Sink:
        async def send(self, _event: RealtimeEventEnvelope) -> None:
            return None

        async def close(self, *, code: int, reason: str) -> None:
            return None

    async def scenario() -> None:
        broker = InMemoryRealtimeEventBroker(
            max_connections=2,
            max_connections_per_owner=1,
        )
        first_id = await broker.subscribe(Sink(), owner_id=1)
        with pytest.raises(BrokerCapacityError):
            await broker.subscribe(Sink(), owner_id=1)

        await broker.subscribe(Sink(), owner_id=2)
        with pytest.raises(BrokerCapacityError):
            await broker.subscribe(Sink(), owner_id=3)
        assert broker.subscriber_count == 2

        await broker.unsubscribe(first_id)
        await broker.subscribe(Sink(), owner_id=1)
        assert broker.subscriber_count == 2
        await broker.close(code=1012, reason="test shutdown")

    asyncio.run(scenario())


def test_publish_does_not_wait_forever_for_cancel_resistant_slow_sink() -> None:
    class CancelResistantSink:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.finished = asyncio.Event()

        async def send(self, _event: RealtimeEventEnvelope) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await self.release.wait()
                raise
            finally:
                self.finished.set()

        async def close(self, *, code: int, reason: str) -> None:
            return None

    class RecordingSink:
        def __init__(self) -> None:
            self.events: list[RealtimeEventEnvelope] = []

        async def send(self, event: RealtimeEventEnvelope) -> None:
            self.events.append(event)

        async def close(self, *, code: int, reason: str) -> None:
            return None

    async def scenario() -> None:
        broker = InMemoryRealtimeEventBroker(
            queue_capacity=1,
            max_connections=2,
            max_connections_per_owner=1,
            sink_close_timeout_seconds=0.02,
        )
        slow = CancelResistantSink()
        healthy = RecordingSink()
        slow_id = await broker.subscribe(slow, owner_id=1)
        await broker.subscribe(healthy, owner_id=2)
        event = RealtimeEventEnvelope(
            event_type="connection.heartbeat",
            payload=StreamHeartbeatPayload(),
        )

        assert await broker.send_to(slow_id, event) is True
        await slow.started.wait()
        assert await broker.send_to(slow_id, event) is True
        report = await asyncio.wait_for(broker.publish(event), timeout=0.25)

        assert report.attempted == 2
        assert report.enqueued == 1
        assert report.disconnected == 1
        assert broker.subscriber_count == 1
        slow.release.set()
        await asyncio.wait_for(slow.finished.wait(), timeout=0.25)
        await broker.close(code=1012, reason="test shutdown")

    asyncio.run(scenario())


def test_broker_shutdown_times_out_hanging_sink_close() -> None:
    class HangingCloseSink:
        def __init__(self) -> None:
            self.close_started = asyncio.Event()

        async def send(self, _event: RealtimeEventEnvelope) -> None:
            return None

        async def close(self, *, code: int, reason: str) -> None:
            self.close_started.set()
            await asyncio.Event().wait()

    async def scenario() -> None:
        broker = InMemoryRealtimeEventBroker(sink_close_timeout_seconds=0.02)
        sink = HangingCloseSink()
        await broker.subscribe(sink, owner_id=1)

        await asyncio.wait_for(
            broker.close(code=1012, reason="test shutdown"),
            timeout=0.25,
        )

        assert sink.close_started.is_set()
        assert broker.subscriber_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "unsafe_summary",
    [
        "Contato: pessoa@example.com",
        "CPF: 123.456.789-00",
        "Telefone: (11) 99999-9999",
        "Matrícula: FUNC-001",
        "Nome do funcionário: Pessoa Teste",
        "Nome da operadora: Pessoa Teste",
        r"Evidência C:\Users\operador\frame.jpg",
        "data:image/jpeg;base64,AAAA",
        "Alerta\ncom quebra de linha",
        "A" * 100,
    ],
)
def test_alert_created_payload_rejects_unsafe_summary(unsafe_summary: str) -> None:
    if unsafe_summary == "A" * 100:
        unsafe_summary = "A" * 100 + ";base64," + "B" * 100
    with pytest.raises(ValidationError):
        AlertCreatedPayload(
            alert_id=1,
            occurrence_id=2,
            level="warning",
            status="nao_lido",
            summary=unsafe_summary,
            detected_at=datetime.now(UTC),
        )


def test_realtime_payloads_do_not_coerce_publisher_values() -> None:
    with pytest.raises(ValidationError):
        AlertCreatedPayload(
            alert_id="1",  # type: ignore[arg-type]
            occurrence_id=2,
            level="warning",
            status="nao_lido",
            summary="Capacete ausente",
            detected_at=datetime.now(UTC),
        )


def test_alert_event_rejects_detection_over_five_minutes_in_the_future() -> None:
    occurred_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        RealtimeEventEnvelope(
            event_type="alert.created",
            occurred_at=occurred_at,
            payload=AlertCreatedPayload(
                alert_id=1,
                occurrence_id=2,
                level="warning",
                status="nao_lido",
                summary="Capacete ausente",
                detected_at=datetime(2026, 8, 20, 13, 0, tzinfo=UTC),
            ),
        )
