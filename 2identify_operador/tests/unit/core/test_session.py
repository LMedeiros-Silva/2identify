from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.session import (
    AuthenticationMethod,
    OperatorSession,
    OperatorSessionAlreadyActiveError,
    OperatorSessionContext,
    OperatorSessionNotFoundError,
)
from app.domain import OperatorIdentity


def test_operator_session_normalizes_name_and_login_time_to_utc() -> None:
    local_time = datetime(2026, 8, 16, 10, 30, tzinfo=timezone(timedelta(hours=-3)))

    session = OperatorSession(
        operator_id=15,
        operator_name="  João Silva  ",
        login_time=local_time,
        authentication_method=AuthenticationMethod.FACE_ID,
    )

    assert session.operator_name == "João Silva"
    assert session.login_time == datetime(2026, 8, 16, 13, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("operator_id", "operator_name", "login_time", "authentication_method"),
    [
        (0, "João", datetime.now(UTC), AuthenticationMethod.FACE_ID),
        (15, " ", datetime.now(UTC), AuthenticationMethod.FACE_ID),
        (15, "João", datetime(2026, 8, 16, 10, 30), AuthenticationMethod.FACE_ID),
        (15, "João", datetime.now(UTC), "face_id"),
    ],
)
def test_operator_session_rejects_invalid_values(
    operator_id: int,
    operator_name: str,
    login_time: datetime,
    authentication_method: object,
) -> None:
    with pytest.raises(ValueError):
        OperatorSession(
            operator_id=operator_id,
            operator_name=operator_name,
            login_time=login_time,
            authentication_method=authentication_method,  # type: ignore[arg-type]
        )


def test_context_opens_and_exposes_face_id_session() -> None:
    login_time = datetime(2026, 8, 16, 13, 32, 15, tzinfo=UTC)
    context = OperatorSessionContext(clock=lambda: login_time)
    identity = OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)

    session = context.open(
        identity.operator_id,
        identity.name,
        AuthenticationMethod.FACE_ID,
    )

    assert context.is_authenticated
    assert context.current is session
    assert context.require_current() is session
    assert session.operator_id == identity.operator_id
    assert session.operator_name == identity.name
    assert session.login_time is login_time
    assert session.authentication_method is AuthenticationMethod.FACE_ID


def test_context_refuses_to_replace_an_active_session() -> None:
    context = OperatorSessionContext()
    first = OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    second = OperatorIdentity(operator_id=22, name="Ana Lima", confidence=0.97)
    context.open(first.operator_id, first.name, AuthenticationMethod.FACE_ID)

    with pytest.raises(OperatorSessionAlreadyActiveError):
        context.open(second.operator_id, second.name, AuthenticationMethod.FACE_ID)

    assert context.require_current().operator_id == first.operator_id


def test_credentials_session_retains_token_without_exposing_it_in_repr() -> None:
    context = OperatorSessionContext()

    session = context.open(
        15,
        "João Silva",
        AuthenticationMethod.CREDENTIALS,
        access_token="token-confidencial",
    )

    assert session.access_token == "token-confidencial"
    assert "token-confidencial" not in repr(session)


def test_context_closes_session_and_protected_access_fails_closed() -> None:
    context = OperatorSessionContext()
    identity = OperatorIdentity(operator_id=15, name="João Silva", confidence=0.94)
    opened = context.open(
        identity.operator_id,
        identity.name,
        AuthenticationMethod.FACE_ID,
    )

    closed = context.close()

    assert closed is opened
    assert context.current is None
    assert not context.is_authenticated
    with pytest.raises(OperatorSessionNotFoundError):
        context.require_current()
