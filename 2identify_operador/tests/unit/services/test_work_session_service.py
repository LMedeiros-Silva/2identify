from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.session import AuthenticationMethod, OperatorSession
from app.domain import (
    Operation,
    OperationStartAuthorization,
    PpeRequirement,
    RiskAreaReference,
    WorkSessionStatus,
)
from app.services import (
    WorkSessionAlreadyActiveError,
    WorkSessionAuthorizationError,
    WorkSessionNotFoundError,
    WorkSessionService,
)

_SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")
_STARTED_AT = datetime(2026, 8, 17, 12, 0, 1, tzinfo=UTC)


def _operator() -> OperatorSession:
    return OperatorSession(
        15,
        "João Silva",
        datetime(2026, 8, 17, 11, 0, tzinfo=UTC),
        AuthenticationMethod.FACE_ID,
    )


def _operation() -> Operation:
    return Operation(
        41,
        "Inspeção",
        required_ppe=(
            PpeRequirement(1, "Capacete", "capacete"),
            PpeRequirement(2, "Botas", "bota"),
        ),
        risk_area=RiskAreaReference(7, "Linha A"),
    )


def _authorization(*, age_seconds: float = 0.5) -> OperationStartAuthorization:
    return OperationStartAuthorization(
        operation_id=41,
        verified_ppe_ids=(1, 2),
        sample_count=8,
        window_size=8,
        authorized_at=_STARTED_AT - timedelta(seconds=age_seconds),
    )


def _service(*times: datetime) -> WorkSessionService:
    values = iter(times or (_STARTED_AT,))
    return WorkSessionService(
        maximum_authorization_age_seconds=2,
        clock=lambda: next(values),
        session_id_factory=lambda: _SESSION_ID,
    )


def test_work_session_service_starts_and_completes_one_local_session() -> None:
    finished_at = _STARTED_AT + timedelta(minutes=10)
    service = _service(_STARTED_AT, finished_at)

    active = service.start(_operator(), _operation(), _authorization())

    assert service.require_current() is active
    assert active.session_id == _SESSION_ID
    assert active.operator_id == 15
    assert active.operation_id == 41
    assert active.risk_area_id == 7
    assert active.verified_ppe_ids == (1, 2)
    assert active.status is WorkSessionStatus.ACTIVE

    completed = service.complete(_SESSION_ID)

    assert service.current is None
    assert service.last_finished is completed
    assert completed.status is WorkSessionStatus.COMPLETED
    assert completed.finished_at == finished_at


def test_work_session_service_rejects_second_or_unknown_session() -> None:
    service = _service(_STARTED_AT)
    service.start(_operator(), _operation(), _authorization())

    with pytest.raises(WorkSessionAlreadyActiveError):
        service.start(_operator(), _operation(), _authorization())
    with pytest.raises(WorkSessionNotFoundError):
        service.complete(UUID("22222222-2222-2222-2222-222222222222"))


@pytest.mark.parametrize(
    "authorization",
    [
        OperationStartAuthorization(
            42,
            (1, 2),
            8,
            8,
            _STARTED_AT - timedelta(seconds=0.5),
        ),
        OperationStartAuthorization(
            41,
            (1,),
            8,
            8,
            _STARTED_AT - timedelta(seconds=0.5),
        ),
        _authorization(age_seconds=3),
    ],
)
def test_work_session_service_rejects_invalid_authorization(
    authorization: OperationStartAuthorization,
) -> None:
    with pytest.raises(WorkSessionAuthorizationError):
        _service(_STARTED_AT).start(_operator(), _operation(), authorization)


def test_work_session_service_interrupts_active_work_on_teardown() -> None:
    interrupted_at = _STARTED_AT + timedelta(minutes=2)
    service = _service(_STARTED_AT, interrupted_at)
    service.start(_operator(), _operation(), _authorization())

    interrupted = service.interrupt_active()

    assert interrupted is not None
    assert interrupted.status is WorkSessionStatus.INTERRUPTED
    assert interrupted.finished_at == interrupted_at
    assert service.current is None
