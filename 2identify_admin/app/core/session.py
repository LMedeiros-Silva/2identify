from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock

from app.domain import AdminAuthentication, Administrator


@dataclass(frozen=True, slots=True)
class AdminSession:
    administrator: Administrator
    access_token: str = field(repr=False)
    expires_at: datetime

    def __post_init__(self) -> None:
        token = self.access_token.strip()
        if not token:
            raise ValueError("O token da sessão está vazio.")
        if self.expires_at.tzinfo is None:
            raise ValueError("A expiração da sessão deve conter fuso horário.")
        object.__setattr__(self, "access_token", token)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        reference = now or datetime.now(UTC)
        return reference >= self.expires_at


class AdminSessionContext:
    """Mantém o token somente em memória durante a execução do desktop."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._session: AdminSession | None = None

    def open(self, authentication: AdminAuthentication) -> AdminSession:
        session = AdminSession(
            administrator=authentication.administrator,
            access_token=authentication.access_token,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=authentication.expires_in),
        )
        with self._lock:
            self._session = session
        return session

    def current(self) -> AdminSession | None:
        with self._lock:
            session = self._session
            if session is not None and session.is_expired():
                self._session = None
                return None
            return session

    def clear(self) -> None:
        with self._lock:
            self._session = None
