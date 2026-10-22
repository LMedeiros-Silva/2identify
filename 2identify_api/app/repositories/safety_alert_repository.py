"""Transactional persistence and idempotency for Operator safety alerts."""

from __future__ import annotations

from collections.abc import Hashable, Set
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import SUBJECT_EMPLOYEE
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
    "fall_detected": "FALL_DETECTED",
}


def session_owner(account_id: int | None, employee_id: int | None) -> Hashable:
    """Who opened a WorkSession: a password account id, or a Face ID employee.

    Face ID sessions store no ``operador_usuario_id``; their employee is the
    occurrence's ``funcionario_id``, so ids of the two tables never collide.
    """

    return account_id if account_id is not None else (SUBJECT_EMPLOYEE, employee_id)


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

    def active_conditions(
        self,
        live_sessions: Set[tuple[Hashable, UUID]] | None = None,
    ) -> tuple[SafetyConditionSnapshot, ...]:
        """Read physically active Operator conditions, whatever their Admin review status.

        Closing an alert in the Admin does not hide a hazard that is still present, and
        alerts without an Operator physical lifecycle never drive the device tower. When
        ``live_sessions`` is given, only conditions of those (operator, WorkSession) pairs
        are returned: an unresolved row whose session stopped reporting is history.
        """
        alerts = PERSISTED_SAFETY_ALERTS
        ingestion = SafetyAlertIngestion.__table__
        try:
            rows = self._session.execute(
                select(
                    alerts.c.id,
                    alerts.c.nivel,
                    alerts.c.criado_em,
                    SAFETY_OCCURRENCES.c.tipo,
                    SAFETY_OCCURRENCES.c.funcionario_id,
                    ingestion.c.operador_usuario_id,
                    ingestion.c.sessao_trabalho_id,
                )
                .select_from(
                    ingestion.join(alerts, alerts.c.id == ingestion.c.alerta_id).outerjoin(
                        SAFETY_OCCURRENCES, SAFETY_OCCURRENCES.c.id == alerts.c.ocorrencia_id
                    )
                )
                .where(ingestion.c.condicao_resolvida_em.is_(None))
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
                if live_sessions is None
                or (
                    session_owner(row.operador_usuario_id, row.funcionario_id),
                    row.sessao_trabalho_id,
                )
                in live_sessions
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
        operator_id: int | None,
        operation_id: int,
        camera_id: int | None,
        risk_area_id: int | None,
        violation_type: str,
        subject_key: str,
        summary: str,
        severity: str,
        detected_at: datetime,
        resolved_at: datetime | None = None,
        employee_id: int | None = None,
    ) -> StoredAlert:
        owner = session_owner(operator_id, employee_id)
        existing = self._session.get(SafetyAlertIngestion, event_id)
        if existing is not None:
            return self._existing(
                existing,
                payload_hash,
                legacy_payload_hash,
                severity,
                owner,
                resolved_at,
            )

        now = datetime.now(UTC)
        occurrence_id = self._session.execute(
            insert(SAFETY_OCCURRENCES)
            .values(
                funcionario_id=employee_id,
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
                # The Admin review starts unread even when the hazard already ended.
                status="nao_lido",
                observacao=summary,
                criado_em=detected_at,
                recebido_em=now,
                encerrado_em=None,
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
            condicao_resolvida_em=resolved_at,
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
                owner,
                resolved_at,
            )
        return StoredAlert(event_id, alert_id, occurrence_id, False, "nao_lido", severity)

    def _existing(
        self,
        ingestion: SafetyAlertIngestion,
        payload_hash: str,
        legacy_payload_hash: str,
        severity: str,
        owner: Hashable,
        resolved_at: datetime | None,
    ) -> StoredAlert:
        if self._owner_of(ingestion) != owner:
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
        stored_severity = "critical" if row.nivel in {"critico", "critical"} else "warning"
        physically_active = ingestion.condicao_resolvida_em is None
        if physically_active and resolved_at is not None:
            # Physical resolution only; the Admin review status is left untouched.
            ingestion.condicao_resolvida_em = resolved_at
            changed = True
        if physically_active and severity == "critical":
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
            status=row.status,
            severity=stored_severity,
        )

    def _owner_of(self, ingestion: SafetyAlertIngestion) -> Hashable:
        if ingestion.operador_usuario_id is not None:
            return ingestion.operador_usuario_id
        employee_id = self._session.scalar(
            select(SAFETY_OCCURRENCES.c.funcionario_id)
            .select_from(
                PERSISTED_SAFETY_ALERTS.join(
                    SAFETY_OCCURRENCES,
                    SAFETY_OCCURRENCES.c.id == PERSISTED_SAFETY_ALERTS.c.ocorrencia_id,
                )
            )
            .where(PERSISTED_SAFETY_ALERTS.c.id == ingestion.alerta_id)
        )
        return session_owner(None, employee_id)

    def resolve_session_conditions(
        self,
        *,
        owner: Hashable,
        work_session_id: UUID,
        session_ended: bool,
    ) -> int:
        """Physically resolve conditions no live Operator session can resolve anymore.

        An ended WorkSession resolves its own conditions; an active one resolves those
        left behind by earlier sessions of the same operator (e.g. after a crash).
        """
        ingestion = SafetyAlertIngestion.__table__
        if isinstance(owner, tuple):
            employee_alerts = (
                select(PERSISTED_SAFETY_ALERTS.c.id)
                .select_from(
                    PERSISTED_SAFETY_ALERTS.join(
                        SAFETY_OCCURRENCES,
                        SAFETY_OCCURRENCES.c.id == PERSISTED_SAFETY_ALERTS.c.ocorrencia_id,
                    )
                )
                .where(SAFETY_OCCURRENCES.c.funcionario_id == owner[1])
            )
            owner_filter = and_(
                ingestion.c.operador_usuario_id.is_(None),
                ingestion.c.alerta_id.in_(employee_alerts),
            )
        else:
            owner_filter = ingestion.c.operador_usuario_id == owner
        session_filter = (
            ingestion.c.sessao_trabalho_id == work_session_id
            if session_ended
            else ingestion.c.sessao_trabalho_id != work_session_id
        )
        try:
            result = self._session.execute(
                update(ingestion)
                .where(
                    owner_filter,
                    ingestion.c.condicao_resolvida_em.is_(None),
                    session_filter,
                )
                .values(condicao_resolvida_em=datetime.now(UTC))
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return result.rowcount or 0
