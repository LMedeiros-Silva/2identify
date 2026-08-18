"""In-memory lifecycle service for industrial work sessions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from app.core.session import OperatorSession
from app.domain.operation import Operation
from app.domain.work_session import (
    OperationStartAuthorization,
    WorkSession,
    WorkSessionStatus,
)

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
SessionIdFactory = Callable[[], UUID]


class WorkSessionError(RuntimeError):
    """Base error for invalid work-session lifecycle operations."""


class WorkSessionAuthorizationError(WorkSessionError):
    """Raised when a safety authorization cannot start the requested work."""


class WorkSessionAlreadyActiveError(WorkSessionError):
    """Raised when another operation is already active in this process."""


class WorkSessionNotFoundError(WorkSessionError):
    """Raised when an active work session is required but absent."""


class WorkSessionService:
    """Validate, own and close the single local active work session."""

    def __init__(
        self,
        *,
        maximum_authorization_age_seconds: float,
        clock: Clock | None = None,
        session_id_factory: SessionIdFactory | None = None,
    ) -> None:
        if maximum_authorization_age_seconds <= 0:
            raise ValueError("maximum_authorization_age_seconds deve ser positivo")
        self._maximum_authorization_age_seconds = maximum_authorization_age_seconds
        self._clock = clock or _utc_now
        self._session_id_factory = session_id_factory or uuid4
        self._lock = RLock()
        self._current: WorkSession | None = None
        self._last_finished: WorkSession | None = None

    @property
    def current(self) -> WorkSession | None:
        with self._lock:
            return self._current

    @property
    def last_finished(self) -> WorkSession | None:
        with self._lock:
            return self._last_finished

    def start(
        self,
        operator_session: OperatorSession,
        operation: Operation,
        authorization: OperationStartAuthorization,
    ) -> WorkSession:
        """Create an active local session from a fresh complete PPE authorization."""

        with self._lock:
            if self._current is not None:
                raise WorkSessionAlreadyActiveError(
                    "Já existe uma operação ativa nesta estação."
                )
            started_at = _as_utc(self._clock())
            self._validate_authorization(operation, authorization, started_at)
            work_session = WorkSession(
                session_id=self._session_id_factory(),
                operator_id=operator_session.operator_id,
                operation_id=operation.operation_id,
                camera_id=None,
                risk_area_id=(
                    operation.risk_area.risk_area_id
                    if operation.risk_area is not None
                    else None
                ),
                verified_ppe_ids=authorization.verified_ppe_ids,
                safety_verified_at=authorization.authorized_at,
                ppe_sample_count=authorization.sample_count,
                ppe_window_size=authorization.window_size,
                started_at=started_at,
                finished_at=None,
                status=WorkSessionStatus.ACTIVE,
            )
            self._current = work_session

        logger.info(
            "work_session_started_locally",
            extra={
                "work_session_id": str(work_session.session_id),
                "operator_id": work_session.operator_id,
                "operation_id": work_session.operation_id,
                "risk_area_id": work_session.risk_area_id,
            },
        )
        return work_session

    def require_current(self) -> WorkSession:
        session = self.current
        if session is None:
            raise WorkSessionNotFoundError("Nenhuma operação está ativa.")
        return session

    def complete(self, session_id: UUID) -> WorkSession:
        """Close the matching active work session as completed."""

        return self._finish(session_id, WorkSessionStatus.COMPLETED)

    def interrupt_active(self) -> WorkSession | None:
        """Close an active session during logout or process shutdown."""

        with self._lock:
            current = self._current
            if current is None:
                return None
            finished = current.finish(
                _as_utc(self._clock()),
                WorkSessionStatus.INTERRUPTED,
            )
            self._current = None
            self._last_finished = finished
        self._log_finished(finished)
        return finished

    def _finish(self, session_id: UUID, status: WorkSessionStatus) -> WorkSession:
        with self._lock:
            current = self._current
            if current is None:
                raise WorkSessionNotFoundError("Nenhuma operação está ativa.")
            if current.session_id != session_id:
                raise WorkSessionNotFoundError(
                    "A sessão informada não corresponde à operação ativa."
                )
            finished = current.finish(_as_utc(self._clock()), status)
            self._current = None
            self._last_finished = finished
        self._log_finished(finished)
        return finished

    def _validate_authorization(
        self,
        operation: Operation,
        authorization: OperationStartAuthorization,
        started_at: datetime,
    ) -> None:
        if not operation.active:
            raise WorkSessionAuthorizationError("A operação não está ativa.")
        if authorization.operation_id != operation.operation_id:
            raise WorkSessionAuthorizationError(
                "A autorização não pertence à operação selecionada."
            )
        required_ids = tuple(item.ppe_id for item in operation.required_ppe)
        if not required_ids or set(authorization.verified_ppe_ids) != set(required_ids):
            raise WorkSessionAuthorizationError(
                "A autorização não cobre todos os EPIs obrigatórios."
            )
        age_seconds = (started_at - authorization.authorized_at).total_seconds()
        if not 0 <= age_seconds <= self._maximum_authorization_age_seconds:
            raise WorkSessionAuthorizationError(
                "A autorização de segurança expirou antes do início."
            )

    @staticmethod
    def _log_finished(session: WorkSession) -> None:
        logger.info(
            "work_session_finished_locally",
            extra={
                "work_session_id": str(session.session_id),
                "operator_id": session.operator_id,
                "operation_id": session.operation_id,
                "status": session.status.value,
                "finished_at": (
                    session.finished_at.isoformat()
                    if session.finished_at is not None
                    else None
                ),
            },
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkSessionError("O relógio deve retornar data com fuso horário.")
    return value.astimezone(UTC)
