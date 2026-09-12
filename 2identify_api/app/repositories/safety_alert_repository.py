"""Transactional persistence and idempotency for Operator safety alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    PERSISTED_SAFETY_ALERTS,
    SAFETY_OCCURRENCES,
    SafetyAlertIngestion,
)
from app.schemas.safety_state import SafetyConditionReason, SafetyConditionSnapshot

_REASON_BY_TYPE: dict[str, SafetyConditionReason] = {
    "ppe_absent": "PPE_MISSING",
    "ergonomic_risk": "ERGONOMIC_RISK",
    "person_in_risk_area": "PERSON_IN_RISK_AREA",
    "monitoring_interrupted": "MONITORING_INTERRUPTED",
}


class AlertEventConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredAlert:
    event_id: UUID
    alert_id: int
    occurrence_id: int
    duplicate: bool
    status: str = "nao_lido"
    severity: str = "warning"


class SafetyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def active_conditions(self) -> tuple[SafetyConditionSnapshot, ...]:
        """Read all non-closed alerts and release the transaction even on WebSockets."""
        alerts = PERSISTED_SAFETY_ALERTS
        try:
            rows = self._session.execute(
                select(alerts.c.id, alerts.c.nivel, alerts.c.criado_em, SAFETY_OCCURRENCES.c.tipo)
                .select_from(
                    alerts.outerjoin(
                        SAFETY_OCCURRENCES, SAFETY_OCCURRENCES.c.id == alerts.c.ocorrencia_id
                    )
                )
                .where(alerts.c.status != "encerrado")
                .order_by(alerts.c.id)
            ).all()
            return tuple(
                SafetyConditionSnapshot(
                    condition_id=f"alert:{row.id}",
                    reason=_REASON_BY_TYPE.get(row.tipo, "OTHER_SAFETY_ALERT"),
                    level="critical"
                    if row.nivel.strip().casefold() in {"critico", "critical"}
                    else "medium",
                    first_observed_at=(
                        row.criado_em.replace(tzinfo=UTC)
                        if row.criado_em.tzinfo is None
                        else row.criado_em
                    ),
                )
                for row in rows
            )
        finally:
            self._session.rollback()

    def store(
        self,
        *,
        event_id: UUID,
        payload_hash: str,
        legacy_payload_hash: str,
        work_session_id: UUID,
        operator_id: int,
        operation_id: int,
        camera_id: int | None,
        risk_area_id: int | None,
        violation_type: str,
        subject_key: str,
        summary: str,
        severity: str,
        detected_at: datetime,
        resolved_at: datetime | None = None,
    ) -> StoredAlert:
        existing = self._session.get(SafetyAlertIngestion, event_id)
        if existing is not None:
            return self._existing(
                existing,
                payload_hash,
                legacy_payload_hash,
                severity,
                operator_id,
                resolved_at,
            )

        now = datetime.now(UTC)
        occurrence_id = self._session.execute(
            insert(SAFETY_OCCURRENCES)
            .values(
                funcionario_id=None,
                camera_id=camera_id,
                tipo=violation_type,
                descricao=summary,
                confianca=None,
                imagem=None,
                video=None,
                detectado_em=detected_at,
            )
            .returning(SAFETY_OCCURRENCES.c.id)
        ).scalar_one()
        alert_id = self._session.execute(
            insert(PERSISTED_SAFETY_ALERTS)
            .values(
                ocorrencia_id=occurrence_id,
                nivel="critico" if severity == "critical" else "aviso",
                status="encerrado" if resolved_at is not None else "nao_lido",
                observacao=summary,
                criado_em=detected_at,
                recebido_em=now,
                encerrado_em=resolved_at,
                encerrado_por=None,
            )
            .returning(PERSISTED_SAFETY_ALERTS.c.id)
        ).scalar_one()
        ingestion = SafetyAlertIngestion(
            evento_id=event_id,
            payload_hash=payload_hash,
            alerta_id=alert_id,
            sessao_trabalho_id=work_session_id,
            operador_usuario_id=operator_id,
            operacao_id=operation_id,
            area_risco_id=risk_area_id,
            violacao_tipo=violation_type,
            assunto_chave=subject_key,
            recebido_em=now,
        )
        self._session.add(ingestion)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raced = self._session.get(SafetyAlertIngestion, event_id)
            if raced is None:
                raise
            return self._existing(
                raced,
                payload_hash,
                legacy_payload_hash,
                severity,
                operator_id,
                resolved_at,
            )
        return StoredAlert(
            event_id,
            alert_id,
            occurrence_id,
            False,
            "encerrado" if resolved_at is not None else "nao_lido",
            severity,
        )

    def _existing(
        self,
        ingestion: SafetyAlertIngestion,
        payload_hash: str,
        legacy_payload_hash: str,
        severity: str,
        operator_id: int,
        resolved_at: datetime | None,
    ) -> StoredAlert:
        if ingestion.operador_usuario_id != operator_id:
            raise AlertEventConflictError("evento pertence a outra sessão de operador")
        if ingestion.payload_hash not in {payload_hash, legacy_payload_hash}:
            raise AlertEventConflictError("event_id já utilizado por outro payload")
        row = self._session.execute(
            select(
                PERSISTED_SAFETY_ALERTS.c.ocorrencia_id,
                PERSISTED_SAFETY_ALERTS.c.status,
                PERSISTED_SAFETY_ALERTS.c.nivel,
            )
            .where(PERSISTED_SAFETY_ALERTS.c.id == ingestion.alerta_id)
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise RuntimeError("registro idempotente aponta para alerta inexistente")
        changed = False
        alert_status = row.status
        stored_severity = "critical" if row.nivel in {"critico", "critical"} else "warning"
        if alert_status != "encerrado" and resolved_at is not None:
            self._session.execute(
                update(PERSISTED_SAFETY_ALERTS)
                .where(PERSISTED_SAFETY_ALERTS.c.id == ingestion.alerta_id)
                .values(status="encerrado", encerrado_em=resolved_at, encerrado_por=None)
            )
            alert_status = "encerrado"
            changed = True
        if row.status != "encerrado" and severity == "critical":
            result = self._session.execute(
                update(PERSISTED_SAFETY_ALERTS)
                .where(
                    PERSISTED_SAFETY_ALERTS.c.id == ingestion.alerta_id,
                    PERSISTED_SAFETY_ALERTS.c.nivel != "critico",
                )
                .values(nivel="critico")
            )
            changed = changed or result.rowcount == 1
            stored_severity = "critical"
        if changed:
            ingestion.payload_hash = payload_hash
            self._session.commit()
        return StoredAlert(
            event_id=ingestion.evento_id,
            alert_id=ingestion.alerta_id,
            occurrence_id=row.ocorrencia_id,
            duplicate=not changed,
            status=alert_status,
            severity=stored_severity,
        )
