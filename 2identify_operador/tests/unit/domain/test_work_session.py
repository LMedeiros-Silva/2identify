from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain import OperationStartAuthorization, WorkSession, WorkSessionStatus


def _active_session() -> WorkSession:
    verified_at = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    return WorkSession(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        operator_id=15,
        operation_id=41,
        camera_id=None,
        risk_area_id=7,
        verified_ppe_ids=(1, 2),
        safety_verified_at=verified_at,
        ppe_sample_count=8,
        ppe_window_size=8,
        started_at=verified_at + timedelta(milliseconds=100),
        finished_at=None,
        status=WorkSessionStatus.ACTIVE,
    )


def test_operation_start_authorization_normalizes_time_and_ids() -> None:
    authorization = OperationStartAuthorization(
        operation_id=41,
        verified_ppe_ids=(1, 2),
        sample_count=5,
        window_size=8,
        authorized_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    )

    assert authorization.verified_ppe_ids == (1, 2)
    assert authorization.authorized_at.tzinfo is UTC


def test_work_session_finishes_as_a_new_immutable_snapshot() -> None:
    active = _active_session()
    finished_at = active.started_at + timedelta(minutes=20)

    completed = active.finish(finished_at, WorkSessionStatus.COMPLETED)

    assert active.is_active
    assert active.finished_at is None
    assert not completed.is_active
    assert completed.status is WorkSessionStatus.COMPLETED
    assert completed.finished_at == finished_at


def test_work_session_rejects_inconsistent_lifecycle_data() -> None:
    active = _active_session()
    with pytest.raises(ValueError, match="sessão ativa"):
        WorkSession(
            session_id=active.session_id,
            operator_id=active.operator_id,
            operation_id=active.operation_id,
            camera_id=None,
            risk_area_id=None,
            verified_ppe_ids=(1,),
            safety_verified_at=active.safety_verified_at,
            ppe_sample_count=5,
            ppe_window_size=8,
            started_at=active.started_at,
            finished_at=active.started_at,
            status=WorkSessionStatus.ACTIVE,
        )
    with pytest.raises(ValueError, match="identificadores positivos"):
        OperationStartAuthorization(
            41,
            (),
            5,
            8,
            active.safety_verified_at,
        )
