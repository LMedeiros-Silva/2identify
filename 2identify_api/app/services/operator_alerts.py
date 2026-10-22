"""Operator alert ingestion use case and realtime event composition."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from app.repositories.safety_alert_repository import (
    SafetyAlertRepository,
    StoredAlert,
    session_owner,
)
from app.schemas.operator_alerts import OperatorAlertCreate
from app.schemas.realtime import AlertCreatedPayload, RealtimeEventEnvelope
from app.schemas.safety_state import SafetyConditionSnapshot
from app.services.session_liveness import SessionLiveness


@dataclass(frozen=True, slots=True)
class OperatorAlertResult:
    stored: StoredAlert
    event: RealtimeEventEnvelope


class OperatorAlertService:
    def __init__(
        self,
        repository: SafetyAlertRepository,
        *,
        liveness: SessionLiveness | None = None,
    ) -> None:
        self._repository = repository
        self._liveness = liveness

    def active_conditions(self) -> tuple[SafetyConditionSnapshot, ...]:
        """Physical conditions of sessions still reporting; history never drives the tower."""

        live = self._liveness.live_sessions() if self._liveness is not None else None
        return self._repository.active_conditions(live_sessions=live)

    def resolve_session_conditions(
        self,
        *,
        owner: Hashable,
        work_session_id: UUID,
        session_ended: bool,
    ) -> int:
        return self._repository.resolve_session_conditions(
            owner=owner,
            work_session_id=work_session_id,
            session_ended=session_ended,
        )

    def ingest(
        self,
        payload: OperatorAlertCreate,
        *,
        operator_id: int | None,
        employee_id: int | None = None,
    ) -> OperatorAlertResult:
        legacy_payload_hash = sha256(
            payload.model_dump_json(exclude={"status", "resolved_at"}, exclude_none=False).encode(
                "utf-8"
            )
        ).hexdigest()
        payload_hash = sha256(
            payload.model_dump_json(
                exclude={"severity", "status", "resolved_at"},
                exclude_none=False,
            ).encode("utf-8")
        ).hexdigest()
        if self._liveness is not None:
            # An alert proves the Operator session is alive (an ended one stays ended).
            self._liveness.touch(session_owner(operator_id, employee_id), payload.work_session_id)
        stored = self._repository.store(
            event_id=payload.event_id,
            payload_hash=payload_hash,
            legacy_payload_hash=legacy_payload_hash,
            work_session_id=payload.work_session_id,
            operator_id=operator_id,
            employee_id=employee_id,
            operation_id=payload.operation_id,
            camera_id=payload.camera_id,
            risk_area_id=payload.risk_area_id,
            violation_type=payload.violation_type,
            subject_key=payload.subject_key,
            summary=payload.summary,
            severity=payload.severity,
            detected_at=payload.raised_at,
            resolved_at=payload.resolved_at,
        )
        category = cast(
            Literal["ppe", "ergonomics", "monitoring", "risk_area", "safety"],
            {
                "ergonomic_risk": "ergonomics",
                "ppe_absent": "ppe",
                "person_in_risk_area": "risk_area",
                "monitoring_interrupted": "monitoring",
                "fall_detected": "safety",
            }[payload.violation_type],
        )
        event = RealtimeEventEnvelope(
            event_type="alert.created",
            occurred_at=payload.resolved_at or payload.raised_at,
            payload=AlertCreatedPayload(
                alert_id=stored.alert_id,
                occurrence_id=stored.occurrence_id,
                category=category,
                level=cast(Literal["warning", "critical"], stored.severity),
                status=cast(Literal["nao_lido", "lido", "encerrado"], stored.status),
                summary=payload.summary,
                detected_at=payload.raised_at,
                camera_id=payload.camera_id,
            ),
        )
        return OperatorAlertResult(stored=stored, event=event)
