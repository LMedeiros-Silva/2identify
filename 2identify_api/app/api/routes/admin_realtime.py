"""Authenticated administrative WebSocket stream for future committed alerts."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_admin_realtime_authorizer,
    get_realtime_event_broker,
    get_runtime_settings,
)
from app.core.config import Settings
from app.realtime import (
    AdminRealtimeAuthorizer,
    BrokerCapacityError,
    BrokerClosedError,
    RealtimeEventBroker,
    WebSocketEventSink,
)
from app.schemas.realtime import stream_heartbeat_event, stream_ready_event
from app.services import AdminAuthorizationRejectedError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["administration-realtime"])

_UNAUTHORIZED_CLOSE_CODE = 4401
_SERVICE_UNAVAILABLE_CLOSE_CODE = 1011
_SERVICE_RESTART_CLOSE_CODE = 1012
_NORMAL_CLOSE_CODE = 1000
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
    value = values[0]
    scheme, separator, token = value.partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not token
        or token != token.strip()
        or any(character.isspace() for character in token)
    ):
        return None
    return token


async def _heartbeat_loop(
    broker: RealtimeEventBroker,
    subscription_id: UUID,
    authorizer: AdminRealtimeAuthorizer,
    token: str,
    interval_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_in_threadpool(authorizer.authorize, token)
        except AdminAuthorizationRejectedError:
            logger.warning("admin_realtime_periodic_authorization_rejected")
            await broker.disconnect(
                subscription_id,
                code=_UNAUTHORIZED_CLOSE_CODE,
                reason="Autorização administrativa expirada",
            )
            return
        except (SQLAlchemyError, RuntimeError) as error:
            logger.error(
                "admin_realtime_periodic_authorization_unavailable",
                extra={"error_type": type(error).__name__},
            )
            await broker.disconnect(
                subscription_id,
                code=_SERVICE_UNAVAILABLE_CLOSE_CODE,
                reason="Serviço administrativo indisponível",
            )
            return
        if not await broker.send_to(subscription_id, stream_heartbeat_event()):
            return


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


async def _run_connection(
    websocket: WebSocket,
    broker: RealtimeEventBroker,
    subscription_id: UUID,
    authorizer: AdminRealtimeAuthorizer,
    token: str,
    heartbeat_interval_seconds: float,
) -> None:
    heartbeat = asyncio.create_task(
        _heartbeat_loop(
            broker,
            subscription_id,
            authorizer,
            token,
            heartbeat_interval_seconds,
        ),
        name="admin-realtime-heartbeat",
    )
    receiver = asyncio.create_task(
        _receive_until_disconnect(websocket, broker, subscription_id),
        name="admin-realtime-receiver",
    )
    done, pending = await asyncio.wait(
        {heartbeat, receiver},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


@router.websocket("/ws/admin/alerts")
async def admin_alert_stream(
    websocket: WebSocket,
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    authorizer: Annotated[
        AdminRealtimeAuthorizer,
        Depends(get_admin_realtime_authorizer),
    ],
    broker: Annotated[RealtimeEventBroker, Depends(get_realtime_event_broker)],
) -> None:
    """Open a server-to-client stream only for a revalidated active administrator."""

    if websocket.url.query:
        logger.warning("admin_realtime_query_string_rejected")
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string não permitida.",
        )
        return

    token = _bearer_from_headers(websocket.headers.getlist("authorization"))
    if token is None:
        logger.warning("admin_realtime_authorization_rejected")
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação administrativa necessária.",
        )
        return

    try:
        principal = await run_in_threadpool(authorizer.authorize, token)
    except AdminAuthorizationRejectedError:
        logger.warning("admin_realtime_authorization_rejected")
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token administrativo inválido.",
        )
        return
    except (SQLAlchemyError, RuntimeError) as error:
        logger.error(
            "admin_realtime_database_unavailable",
            extra={"error_type": type(error).__name__},
        )
        await _deny_handshake(
            websocket,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço administrativo indisponível.",
        )
        return

    await websocket.accept()
    sink = WebSocketEventSink(
        websocket,
        close_timeout_seconds=settings.realtime_sink_close_timeout_seconds,
    )
    subscription_id = None
    try:
        subscription_id = await broker.subscribe(
            sink,
            owner_id=principal.account_id,
        )
        if not await broker.send_to(subscription_id, stream_ready_event()):
            return
        await _run_connection(
            websocket,
            broker,
            subscription_id,
            authorizer,
            token,
            settings.realtime_heartbeat_interval_seconds,
        )
    except BrokerClosedError:
        await sink.close(
            code=_SERVICE_RESTART_CLOSE_CODE,
            reason="API em encerramento",
        )
    except BrokerCapacityError:
        logger.warning("admin_realtime_capacity_reached")
        await sink.close(
            code=1013,
            reason="Capacidade de conexões atingida",
        )
    except Exception as error:
        logger.warning(
            "admin_realtime_connection_failed",
            extra={"error_type": type(error).__name__},
        )
        if subscription_id is not None:
            await broker.disconnect(
                subscription_id,
                code=_SERVICE_UNAVAILABLE_CLOSE_CODE,
                reason="Fluxo em tempo real indisponível",
            )
        else:
            await sink.close(
                code=_SERVICE_UNAVAILABLE_CLOSE_CODE,
                reason="Fluxo em tempo real indisponível",
            )
    finally:
        if subscription_id is not None:
            await broker.unsubscribe(subscription_id)
        else:
            await sink.close(code=_NORMAL_CLOSE_CODE, reason="Conexão encerrada")
