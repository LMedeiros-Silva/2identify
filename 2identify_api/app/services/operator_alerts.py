"""Operator alert ingestion use case and realtime event composition."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast

from app.repositories.safety_alert_repository import SafetyAlertRepository, StoredAlert
from app.schemas.operator_alerts import OperatorAlertCreate
from app.schemas.realtime import AlertCreatedPayload, RealtimeEventEnvelope


@dataclass(frozen=True, slots=True)
class OperatorAlertResult:
    stored: StoredAlert
    event: RealtimeEventEnvelope


class OperatorAlertService:
    def __init__(self, repository: SafetyAlertRepository) -> None:
        self._repository = repository

    def ingest(
        self,
        payload: OperatorAlertCreate,
        *,
        operator_id: int,
    ) -> OperatorAlertResult:
        payload_hash = sha256(
            payload.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        stored = self._repository.store(
            event_id=payload.event_id,
            payload_hash=payload_hash,
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
            event_id=payload.event_id,
            event_type="alert.created",
            occurred_at=payload.raised_at,
            payload=AlertCreatedPayload(
                alert_id=stored.alert_id,
                occurrence_id=stored.occurrence_id,
                category=category,
                level=payload.severity,
                status="nao_lido",
                summary=payload.summary,
                detected_at=payload.raised_at,
                camera_id=payload.camera_id,
            ),
        )
        return OperatorAlertResult(stored=stored, event=event)
