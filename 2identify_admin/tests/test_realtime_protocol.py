from __future__ import annotations

import json
from datetime import UTC
from uuid import UUID

import pytest

from app.domain import ConnectionReadyEvent, HeartbeatEvent, RealtimeAlert
from app.realtime import (
    MAX_REALTIME_MESSAGE_BYTES,
    InvalidRealtimeEventError,
    InvalidWebSocketUrlError,
    derive_admin_websocket_url,
    parse_realtime_event,
)


def envelope(event_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": "12345678-1234-4234-8234-123456789abc",
        "event_type": event_type,
        "occurred_at": "2026-08-20T12:00:00Z",
        "payload": payload,
    }


def alert_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "alert_id": 7,
        "occurrence_id": 11,
        "level": "critical",
        "status": "nao_lido",
        "summary": "Ausência de capacete detectada na câmera 2.",
        "detected_at": "2026-08-20T11:59:58Z",
        "camera_id": 2,
    }
    payload.update(overrides)
    return payload


def test_derives_websocket_url_and_requires_tls_outside_loopback() -> None:
    assert (
        derive_admin_websocket_url("http://127.0.0.1:8000")
        == "ws://127.0.0.1:8000/ws/admin/alerts"
    )
    assert (
        derive_admin_websocket_url("http://localhost:8000/base/")
        == "ws://localhost:8000/base/ws/admin/alerts"
    )
    assert (
        derive_admin_websocket_url("https://api.example.test/v1")
        == "wss://api.example.test/v1/ws/admin/alerts"
    )

    with pytest.raises(InvalidWebSocketUrlError):
        derive_admin_websocket_url("http://api.example.test")
    with pytest.raises(InvalidWebSocketUrlError):
        derive_admin_websocket_url("https://token@api.example.test")
    with pytest.raises(InvalidWebSocketUrlError):
        derive_admin_websocket_url("https://api.example.test?token=secret")


def test_parses_all_strict_v1_event_types() -> None:
    ready = parse_realtime_event(
        json.dumps(
            envelope(
                "connection.ready",
                {"status": "awaiting_alert_ingestion"},
            )
        )
    )
    heartbeat = parse_realtime_event(
        json.dumps(envelope("connection.heartbeat", {}))
    )
    alert = parse_realtime_event(
        json.dumps(envelope("alert.created", alert_payload()))
    )

    assert isinstance(ready, ConnectionReadyEvent)
    assert isinstance(heartbeat, HeartbeatEvent)
    assert isinstance(alert, RealtimeAlert)
    assert alert.event_id == UUID("12345678-1234-4234-8234-123456789abc")
    assert alert.detected_at.tzinfo == UTC
    assert alert.camera_id == 2


@pytest.mark.parametrize(
    "document",
    [
        envelope("connection.ready", {"status": "ready"}),
        envelope("connection.heartbeat", {"unexpected": True}),
        envelope("alert.created", alert_payload(alert_id=0)),
        envelope("alert.created", alert_payload(level="info")),
        envelope("alert.created", alert_payload(status="pendente")),
        envelope("alert.created", alert_payload(camera_id=-1)),
        envelope(
            "alert.created",
            alert_payload(detected_at="2026-08-20T09:00:00-03:00"),
        ),
        {**envelope("connection.heartbeat", {}), "schema_version": 2},
        {**envelope("connection.heartbeat", {}), "extra": "forbidden"},
    ],
)
def test_rejects_invalid_or_extra_contract_fields(document: dict[str, object]) -> None:
    with pytest.raises(InvalidRealtimeEventError):
        parse_realtime_event(json.dumps(document))


@pytest.mark.parametrize(
    "summary",
    [
        "arquivo C:\\Users\\operador\\foto.jpg",
        "configuração /etc/2identify/camera.conf",
        "evidência /opt/2identify/frame.jpg",
        "data:image/jpeg;base64," + ("A" * 100),
        "DATA:text/plain,conteudo",
        "imagem " + ("A" * 100) + ";BASE64," + ("B" * 100),
        "Contato admin@example.com",
        "CPF: 123.456.789-00",
        "Celular: (11) 99999-9999",
        "Phone: +55.11.99999.9999",
        "Contato +55.11.99999.9999",
        "Nome do funcionário: Pessoa Teste",
        "Alerta\ncom quebra de linha",
    ],
)
def test_rejects_local_paths_base64_and_pii(summary: str) -> None:
    with pytest.raises(InvalidRealtimeEventError):
        parse_realtime_event(
            json.dumps(envelope("alert.created", alert_payload(summary=summary)))
        )


def test_rejects_duplicate_keys_and_oversized_messages() -> None:
    duplicate = (
        '{"schema_version":1,"schema_version":1,'
        '"event_id":"12345678-1234-4234-8234-123456789abc",'
        '"event_type":"connection.heartbeat",'
        '"occurred_at":"2026-08-20T12:00:00Z","payload":{}}'
    )
    with pytest.raises(InvalidRealtimeEventError):
        parse_realtime_event(duplicate)
    with pytest.raises(InvalidRealtimeEventError):
        parse_realtime_event("x" * (MAX_REALTIME_MESSAGE_BYTES + 1))


def test_detected_at_allows_at_most_five_minutes_of_clock_skew() -> None:
    parse_realtime_event(
        json.dumps(
            envelope(
                "alert.created",
                alert_payload(detected_at="2026-08-20T12:05:00Z"),
            )
        )
    )

    with pytest.raises(InvalidRealtimeEventError):
        parse_realtime_event(
            json.dumps(
                envelope(
                    "alert.created",
                    alert_payload(detected_at="2026-08-20T12:05:01Z"),
                )
            )
        )
