"""SQLAlchemy 2.x engine and request-scoped session management."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot answer a non-mutating probe."""


@runtime_checkable
class DatabaseGateway(Protocol):
    """Small infrastructure contract used by the application lifecycle and health route."""

    def check_connection(self) -> None:
        """Verify that PostgreSQL is reachable."""

    def dispose(self) -> None:
        """Release owned database resources."""


class DatabaseManager:
    """Own the engine and session factory for one API process."""

    def __init__(self, settings: Settings) -> None:
        self.engine: Engine = create_engine(
            settings.sqlalchemy_database_url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "connect_timeout": settings.database_connect_timeout_seconds,
                "application_name": settings.app_name,
                "options": f"-csearch_path={settings.database_schema}",
            },
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    def check_connection(self) -> None:
        """Execute a real read-only PostgreSQL round trip."""

        try:
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1")).scalar_one()
                if result != 1:
                    raise DatabaseUnavailableError("resposta inesperada do PostgreSQL")
        except DatabaseUnavailableError:
            raise
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("PostgreSQL indisponível") from error

    def dispose(self) -> None:
        """Release all pooled connections during application shutdown."""

        self.engine.dispose()


def get_database_manager(request: Request) -> DatabaseManager:
    """Resolve the application-owned database manager."""

    database = getattr(request.app.state, "database", None)
    if not isinstance(database, DatabaseManager):
        raise RuntimeError("gerenciador de banco não configurado")
    return database


def get_db(request: Request) -> Iterator[Session]:
    """Provide one SQLAlchemy session and always close it after the request."""

    database = get_database_manager(request)
    session = database.session_factory()
    try:
        yield session
    finally:
        session.close()
