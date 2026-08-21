"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import DatabaseGateway, DatabaseManager, DatabaseUnavailableError
from app.core.logging_config import configure_logging
from app.realtime import (
    AdminRealtimeAuthorizer,
    DatabaseAdminRealtimeAuthorizer,
    InMemoryRealtimeEventBroker,
    RealtimeEventBroker,
    UnavailableAdminRealtimeAuthorizer,
)

logger = logging.getLogger(__name__)
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


async def request_validation_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    """Return useful validation details without reflecting submitted secrets."""

    if not isinstance(error, RequestValidationError):
        raise error
    safe_errors = [
        {key: item[key] for key in ("type", "loc", "msg") if key in item}
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": safe_errors},
        headers=_NO_STORE_HEADERS,
    )


def create_app(
    settings: Settings | None = None,
    database: DatabaseGateway | None = None,
    realtime_event_broker: RealtimeEventBroker | None = None,
    admin_realtime_authorizer: AdminRealtimeAuthorizer | None = None,
) -> FastAPI:
    """Build one application instance with explicit infrastructure dependencies."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    logger.info(
        "configuration_loaded",
        extra={
            "app_env": resolved_settings.app_env.value,
            "database_schema": resolved_settings.database_schema,
        },
    )
    resolved_database = database or DatabaseManager(resolved_settings)
    resolved_realtime_event_broker = realtime_event_broker or InMemoryRealtimeEventBroker(
        queue_capacity=resolved_settings.realtime_client_queue_capacity,
        max_connections=resolved_settings.realtime_max_connections,
        max_connections_per_owner=resolved_settings.realtime_max_connections_per_admin,
        sink_close_timeout_seconds=resolved_settings.realtime_sink_close_timeout_seconds,
    )
    if admin_realtime_authorizer is not None:
        resolved_admin_realtime_authorizer = admin_realtime_authorizer
    elif isinstance(resolved_database, DatabaseManager):
        resolved_admin_realtime_authorizer = DatabaseAdminRealtimeAuthorizer(
            resolved_database.session_factory,
            resolved_settings,
        )
    else:
        resolved_admin_realtime_authorizer = UnavailableAdminRealtimeAuthorizer()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "api_started",
            extra={"app_env": resolved_settings.app_env.value, "version": __version__},
        )
        try:
            resolved_database.check_connection()
        except DatabaseUnavailableError as error:
            logger.warning(
                "database_startup_check_failed",
                extra={"error_type": type(error.__cause__ or error).__name__},
            )
        else:
            logger.info("database_startup_check_succeeded")

        try:
            yield
        finally:
            await resolved_realtime_event_broker.close(
                code=1012,
                reason="API em encerramento",
            )
            resolved_database.dispose()
            logger.info("api_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = resolved_database
    application.state.realtime_event_broker = resolved_realtime_event_broker
    application.state.admin_realtime_authorizer = resolved_admin_realtime_authorizer
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.include_router(router)
    return application


app = create_app()
