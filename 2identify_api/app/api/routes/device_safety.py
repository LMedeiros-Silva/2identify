"""Token-authenticated WebSocket stream consumed by ESP32 signal devices."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_runtime_settings,
    get_safety_state_aggregator,
    get_safety_state_broker,
)
from app.core.config import Settings
from app.realtime import (
    BrokerCapacityError,
    BrokerClosedError,
    RealtimeEventBroker,
    WebSocketEventSink,
)
from app.services import SafetyStateAggregator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["device-safety"])

_SERVICE_RESTART_CLOSE_CODE = 1012
_SERVICE_UNAVAILABLE_CLOSE_CODE = 1011
_POLICY_VIOLATION_CLOSE_CODE = 1008
_UNSUPPORTED_DATA_CLOSE_CODE = 1003
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


async def _deny_handshake(
    websocket: WebSocket,
    *,
    status_code: int,
    detail: str,
) -> None:
    await websocket.send_denial_response(
        JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=_NO_STORE_HEADERS,
        )
    )


def _bearer_from_headers(values: list[str]) -> str | None:
    if len(values) != 1:
        return None
    scheme, separator, token = values[0].partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not token
        or token != token.strip()
        or any(character.isspace() for character in token)
    ):
        return None
    return token


async def _receive_until_disconnect(
    websocket: WebSocket,
    broker: RealtimeEventBroker,
    subscription_id: UUID,
) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        close_code = (
            _UNSUPPORTED_DATA_CLOSE_CODE
            if message.get("bytes") is not None
            else _POLICY_VIOLATION_CLOSE_CODE
        )
        await broker.disconnect(
            subscription_id,
            code=close_code,
            reason="Canal disponível somente para recebimento",
        )
        return


@router.websocket("/ws/devices/safety")
async def safety_device_stream(
    websocket: WebSocket,
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    aggregator: Annotated[SafetyStateAggregator, Depends(get_safety_state_aggregator)],
    broker: Annotated[RealtimeEventBroker, Depends(get_safety_state_broker)],
) -> None:
    """Send the current state immediately and then only effective changes."""

    if websocket.url.query:
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string não permitida.",
        )
        return
    configured = settings.safety_device_token
    token = _bearer_from_headers(websocket.headers.getlist("authorization"))
    if configured is None:
        logger.error("safety_device_authentication_not_configured")
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação do dispositivo não configurada.",
        )
        return
    if token is None or not secrets.compare_digest(
        token,
        configured.get_secret_value(),
    ):
        logger.warning("safety_device_authorization_rejected")
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token do dispositivo inválido.",
        )
        return

    await websocket.accept()
    sink = WebSocketEventSink(
        websocket,
        close_timeout_seconds=settings.realtime_sink_close_timeout_seconds,
    )
    subscription_id: UUID | None = None
    try:
        subscription_id = await broker.subscribe(sink)
        if not await aggregator.send_current(subscription_id):
            return
        await _receive_until_disconnect(websocket, broker, subscription_id)
    except BrokerClosedError:
        await sink.close(
            code=_SERVICE_RESTART_CLOSE_CODE,
            reason="API em encerramento",
        )
    except BrokerCapacityError:
        await sink.close(
            code=1013,
            reason="Capacidade de dispositivos atingida",
        )
    except Exception as error:
        logger.warning(
            "safety_device_connection_failed",
            extra={"error_type": type(error).__name__},
        )
        if subscription_id is not None:
            await broker.disconnect(
                subscription_id,
                code=_SERVICE_UNAVAILABLE_CLOSE_CODE,
                reason="Canal do sinalizador indisponível",
            )
        else:
            await sink.close(
                code=_SERVICE_UNAVAILABLE_CLOSE_CODE,
                reason="Canal do sinalizador indisponível",
            )
    finally:
        if subscription_id is not None:
            await broker.unsubscribe(subscription_id)
