"""Root and real database health endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.database import DatabaseGateway, DatabaseUnavailableError
from app.schemas import HealthResponse, RootResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=RootResponse, tags=["foundation"])
def root(request: Request) -> RootResponse:
    """Confirm that the FastAPI process is serving requests."""

    return RootResponse(name=request.app.state.settings.app_name, status="running")


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
    tags=["foundation"],
)
def health(request: Request) -> HealthResponse | JSONResponse:
    """Check FastAPI and perform a real `SELECT 1` against PostgreSQL."""

    database: DatabaseGateway = request.app.state.database
    try:
        database.check_connection()
    except DatabaseUnavailableError as error:
        logger.warning(
            "database_health_check_failed",
            extra={"error_type": type(error.__cause__ or error).__name__},
        )
        payload = HealthResponse(status="degraded", database="disconnected")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(mode="json"),
        )

    logger.info("database_health_check_succeeded")
    return HealthResponse(status="ok", database="connected")
