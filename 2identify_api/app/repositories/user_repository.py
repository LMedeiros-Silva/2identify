"""Read access to existing user accounts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Usuario


class UserRepository:
    """Query active accounts without mutating the Admin-owned table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_active_by_username(self, username: str) -> Usuario | None:
        statement = select(Usuario).where(
            Usuario.username == username,
            Usuario.ativo.is_(True),
        )
        return self._session.scalar(statement)

    def find_active_by_id(self, account_id: int) -> Usuario | None:
        statement = select(Usuario).where(
            Usuario.id == account_id,
            Usuario.ativo.is_(True),
        )
        return self._session.scalar(statement)
