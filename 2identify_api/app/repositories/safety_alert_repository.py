"""Transactional persistence and idempotency for Operator safety alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    PERSISTED_SAFETY_ALERTS,
    SAFETY_OCCURRENCES,
    SafetyAlertIngestion,
)


class AlertEventConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredAlert:
    event_id: UUID
    alert_id: int
    occurrence_id: int
    duplicate: bool


class SafetyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def store(
        self,
        *,
        event_id: UUID,
        payload_hash: str,
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
    ) -> StoredAlert:
        existing = self._session.get(SafetyAlertIngestion, event_id)
        if existing is not None:
            return self._existing(existing, payload_hash)

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
        )
        self._session.add(ingestion)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raced = self._session.get(SafetyAlertIngestion, event_id)
            if raced is None:
                raise
            return self._existing(raced, payload_hash)
        return StoredAlert(event_id, alert_id, occurrence_id, False)

    def _existing(
        self,
        ingestion: SafetyAlertIngestion,
        payload_hash: str,
    ) -> StoredAlert:
        if ingestion.payload_hash != payload_hash:
            raise AlertEventConflictError("event_id já utilizado por outro payload")
        occurrence_id = self._session.scalar(
            select(PERSISTED_SAFETY_ALERTS.c.ocorrencia_id).where(
                PERSISTED_SAFETY_ALERTS.c.id == ingestion.alerta_id
            )
        )
        if occurrence_id is None:
            raise RuntimeError("registro idempotente aponta para alerta inexistente")
        return StoredAlert(
            event_id=ingestion.evento_id,
            alert_id=ingestion.alerta_id,
            occurrence_id=occurrence_id,
            duplicate=True,
        )
