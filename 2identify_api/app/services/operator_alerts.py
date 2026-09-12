"""Operator alert ingestion use case and realtime event composition."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast

from app.repositories.safety_alert_repository import SafetyAlertRepository, StoredAlert
from app.schemas.operator_alerts import OperatorAlertCreate
from app.schemas.realtime import AlertCreatedPayload, RealtimeEventEnvelope
from app.schemas.safety_state import SafetyConditionSnapshot


@dataclass(frozen=True, slots=True)
class OperatorAlertResult:
    stored: StoredAlert
    event: RealtimeEventEnvelope


class OperatorAlertService:
    def __init__(self, repository: SafetyAlertRepository) -> None:
        self._repository = repository

    def active_conditions(self) -> tuple[SafetyConditionSnapshot, ...]:
        return self._repository.active_conditions()

    def ingest(
        self,
        payload: OperatorAlertCreate,
        *,
        operator_id: int,
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
        stored = self._repository.store(
            event_id=payload.event_id,
            payload_hash=payload_hash,
            legacy_payload_hash=legacy_payload_hash,
            work_session_id=payload.work_session_id,
            operator_id=operator_id,
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
            Literal["ppe", "ergonomics", "monitoring", "risk_area"],
            {
                "ergonomic_risk": "ergonomics",
                "ppe_absent": "ppe",
                "person_in_risk_area": "risk_area",
                "monitoring_interrupted": "monitoring",
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
