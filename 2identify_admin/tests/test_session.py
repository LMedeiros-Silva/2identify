from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.session import AdminSession, AdminSessionContext
from app.domain import AdminAuthentication, Administrator


def make_administrator() -> Administrator:
    return Administrator(
        id=1,
        name="Admin",
        username="admin",
        profile="administrador",
    )


def test_token_lives_only_in_memory_and_is_redacted_from_repr() -> None:
    authentication = AdminAuthentication(
        administrator=make_administrator(),
        access_token="top-secret-token",
        token_type="bearer",
        expires_in=60,
    )
    context = AdminSessionContext()
    session = context.open(authentication)

    assert context.current() is session
    assert "top-secret-token" not in repr(authentication)
    assert "top-secret-token" not in repr(session)

    context.clear()
    assert context.current() is None


def test_expiration_is_evaluated_in_utc() -> None:
    session = AdminSession(
        administrator=make_administrator(),
        access_token="token",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert session.is_expired()
