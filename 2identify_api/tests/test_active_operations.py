"""Realtime active-operation registry contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.schemas.active_operations import ActiveOperationOverallStatus
from app.schemas.operations import OperationDetail
from app.schemas.safety_state import OperatorSafetyStateSnapshot
from app.services.active_operations import (
    ActiveOperationRegistry,
    ActiveOperationSnapshotConflictError,
)

_SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_STARTED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
_OBSERVED_AT = _STARTED_AT + timedelta(seconds=5)


class RecordingBroker:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object) -> object:
        self.published.append(event)
        return object()


def _operation() -> OperationDetail:
    return OperationDetail.model_validate(
        {
            "id": 7,
            "name": "Linha de montagem",
            "description": None,
            "required_ppe": [
                {"id": 1, "name": "Capacete", "code": "CAP"},
                {"id": 2, "name": "Luvas", "code": "LUV"},
            ],
            "risk_area": {
                "id": 9,
                "camera_id": 3,
                "camera_name": "Câmera Linha A",
                "name": "Linha A",
                "geometry": {
                    "type": "polygon",
                    "points": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
                },
                "active": True,
                "created_at": _STARTED_AT,
                "updated_at": _STARTED_AT,
            },
            "active": True,
            "created_at": _STARTED_AT,
            "updated_at": _STARTED_AT,
        }
    )


def _snapshot(
    *states: tuple[int, str],
    status: str = "active",
    observed_at: datetime = _OBSERVED_AT,
) -> OperatorSafetyStateSnapshot:
    return OperatorSafetyStateSnapshot.model_validate(
        {
            "work_session_id": str(_SESSION_ID),
            "operation_id": 7,
            "camera_id": 3,
            "observed_at": observed_at.isoformat(),
            "started_at": _STARTED_AT.isoformat(),
            "session_status": status,
            "ppe": [
                {"ppe_id": ppe_id, "state": state}
                for ppe_id, state in states
            ],
            "conditions": [],
        }
    )


def test_registry_enriches_snapshot_and_broadcasts_updates_and_end() -> None:
    broker = RecordingBroker()
    registry = ActiveOperationRegistry(broker)  # type: ignore[arg-type]

    async def scenario() -> None:
        first = await registry.update(
            operator_id=15,
            operator_name="Breno Barbosa",
            operation=_operation(),
            snapshot=_snapshot((1, "confirmed"), (2, "absent")),
        )
        assert first.overall_status is ActiveOperationOverallStatus.NON_COMPLIANT
        assert first.operator_name == "Breno Barbosa"
        assert first.operation_name == "Linha de montagem"
        assert first.camera_name == "Câmera Linha A"
        assert [item.name for item in first.ppe] == ["Capacete", "Luvas"]
        assert [item.state for item in first.ppe] == ["confirmed", "absent"]
        assert await registry.list_active() == (first,)

        second = await registry.update(
            operator_id=15,
            operator_name="Breno Barbosa",
            operation=_operation(),
            snapshot=_snapshot(
                (1, "confirmed"),
                (2, "collecting"),
                observed_at=_OBSERVED_AT + timedelta(seconds=2),
            ),
        )
        assert second.overall_status is ActiveOperationOverallStatus.ATTENTION

        ended = await registry.update(
            operator_id=15,
            operator_name="Breno Barbosa",
            operation=_operation(),
            snapshot=_snapshot(status="ended", observed_at=_OBSERVED_AT + timedelta(seconds=3)),
        )
        assert ended.session_status == "ended"
        assert await registry.list_active() == ()

        events = [item.as_json_message() for item in broker.published]  # type: ignore[attr-defined]
        assert [item["event_type"] for item in events] == [
            "ppe.session.updated",
            "ppe.session.updated",
            "ppe.session.updated",
        ]
        assert events[-1]["payload"]["session_status"] == "ended"  # type: ignore[index]
        assert events[-1]["payload"]["work_session_id"] == str(_SESSION_ID)  # type: ignore[index]

    asyncio.run(scenario())


def test_registry_rejects_ppe_or_camera_not_bound_to_operation() -> None:
    registry = ActiveOperationRegistry(RecordingBroker())  # type: ignore[arg-type]

    async def scenario() -> None:
        with pytest.raises(ActiveOperationSnapshotConflictError):
            await registry.update(
                operator_id=15,
                operator_name="Breno Barbosa",
                operation=_operation(),
                snapshot=_snapshot((1, "confirmed")),
            )
        mismatched_camera = _snapshot((1, "confirmed"), (2, "confirmed")).model_copy(
            update={"camera_id": 99}
        )
        with pytest.raises(ActiveOperationSnapshotConflictError):
            await registry.update(
                operator_id=15,
                operator_name="Breno Barbosa",
                operation=_operation(),
                snapshot=mismatched_camera,
            )

    asyncio.run(scenario())


def test_snapshot_keeps_legacy_hardware_payload_compatible() -> None:
    legacy = OperatorSafetyStateSnapshot.model_validate(
        {
            "work_session_id": str(_SESSION_ID),
            "operation_id": 7,
            "camera_id": 3,
            "observed_at": _OBSERVED_AT,
            "conditions": [],
        }
    )
    assert legacy.started_at is None
    assert legacy.ppe == ()
    assert legacy.session_status == "active"
