"""Application-scoped operator authentication session."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class AuthenticationMethod(StrEnum):
    """Supported ways to establish an operator session."""

    FACE_ID = "face_id"
    CREDENTIALS = "credentials"


@dataclass(frozen=True, slots=True)
class OperatorSession:
    """Immutable authentication context shared during the application lifetime."""

    operator_id: int
    operator_name: str
    login_time: datetime
    authentication_method: AuthenticationMethod
    access_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        normalized_name = self.operator_name.strip()
        if self.operator_id <= 0:
            raise ValueError("operator_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("operator_name não pode ser vazio")
        if self.login_time.tzinfo is None or self.login_time.utcoffset() is None:
            raise ValueError("login_time deve possuir fuso horário")
        if not isinstance(self.authentication_method, AuthenticationMethod):
            raise ValueError("authentication_method inválido")

        access_token = self.access_token
        if access_token is not None:
            access_token = access_token.strip()
            if not access_token:
                raise ValueError("access_token não pode ser vazio")

        object.__setattr__(self, "operator_name", normalized_name)
        object.__setattr__(self, "login_time", self.login_time.astimezone(UTC))
        object.__setattr__(self, "access_token", access_token)


class OperatorSessionError(RuntimeError):
    """Base error for invalid authentication-session lifecycle operations."""


class OperatorSessionAlreadyActiveError(OperatorSessionError):
    """Raised when authentication is attempted while another session is active."""


class OperatorSessionNotFoundError(OperatorSessionError):
    """Raised when an authenticated context is required but none exists."""


class OperatorSessionContext:
    """Thread-safe owner of the single authenticated operator session.

    The context is intentionally in-memory. It represents who is using the current
    application process; it is not a persistence mechanism or a work session.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or _utc_now
        self._lock = RLock()
        self._current: OperatorSession | None = None

    @property
    def current(self) -> OperatorSession | None:
        """Return the current immutable session snapshot, when authenticated."""

        with self._lock:
            return self._current

    @property
    def is_authenticated(self) -> bool:
        with self._lock:
            return self._current is not None

    def open(
        self,
        operator_id: int,
        operator_name: str,
        authentication_method: AuthenticationMethod,
        access_token: str | None = None,
    ) -> OperatorSession:
        """Create the process session after an authoritative authentication result."""

        with self._lock:
            if self._current is not None:
                raise OperatorSessionAlreadyActiveError(
                    "Já existe uma sessão de operador ativa."
                )

            session = OperatorSession(
                operator_id=operator_id,
                operator_name=operator_name,
                login_time=self._clock(),
                authentication_method=authentication_method,
                access_token=access_token,
            )
            self._current = session

        logger.info(
            "operator_session_created",
            extra={
                "operator_id": session.operator_id,
                "authentication_method": session.authentication_method.value,
                "login_time": session.login_time.isoformat(),
            },
        )
        return session

    def require_current(self) -> OperatorSession:
        """Return the active session or fail closed for protected workflows."""

        session = self.current
        if session is None:
            raise OperatorSessionNotFoundError("Nenhum operador está autenticado.")
        return session

    def close(self) -> OperatorSession | None:
        """Clear and return the previous session, making logout explicit."""

        with self._lock:
            previous = self._current
            self._current = None

        if previous is not None:
            logger.info("operator_session_closed", extra={"operator_id": previous.operator_id})
        return previous


def _utc_now() -> datetime:
    return datetime.now(UTC)
