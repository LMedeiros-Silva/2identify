"""Administrative alert queries and audited lifecycle transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.models import (
    PERSISTED_SAFETY_ALERTS,
    SAFETY_CAMERAS,
    SAFETY_EMPLOYEES,
    SAFETY_OCCURRENCES,
    SAFETY_SECTORS,
    SafetyAlertIngestion,
    Usuario,
)


class AdminAlertNotFoundError(RuntimeError):
    pass


class AdminAlertStateConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdminAlertRecord:
    alert_id: int
    occurrence_id: int
    level: str
    status: str
    observation: str | None
    created_at: datetime
    received_at: datetime | None
    confirmed_at: datetime | None
    confirmed_by_id: int | None
    confirmed_by_name: str | None
    closed_at: datetime | None
    closed_by_id: int | None
    closed_by_name: str | None
    occurrence_type: str
    occurrence_description: str | None
    confidence: float | None
    image_reference: str | None
    video_reference: str | None
    detected_at: datetime
    employee_id: int | None
    employee_name: str | None
    employee_registration: str | None
    employee_role: str | None
    employee_shift: str | None
    employee_sector_id: int | None
    employee_sector_name: str | None
    camera_id: int | None
    camera_name: str | None
    camera_description: str | None
    camera_sector_id: int | None
    camera_sector_name: str | None
    event_id: UUID | None
    work_session_id: UUID | None
    operator_id: int | None
    operator_name: str | None
    operation_id: int | None
    risk_area_id: int | None
    violation_type: str | None
    subject_key: str | None
    ingestion_received_at: datetime | None


class AdminAlertRepository:
    """Read complete alert details and enforce its lifecycle in one transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._employee_sector = SAFETY_SECTORS.alias("setor_funcionario")
        self._camera_sector = SAFETY_SECTORS.alias("setor_camera")
        users = Usuario.__table__
        self._operator = users.alias("usuario_operador")
        self._confirmer = users.alias("usuario_confirmacao")
        self._closer = users.alias("usuario_encerramento")
        self._ingestion = SafetyAlertIngestion.__table__

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: str | None,
    ) -> tuple[tuple[AdminAlertRecord, ...], int]:
        condition = (
            None if status_filter is None else PERSISTED_SAFETY_ALERTS.c.status == status_filter
        )
        count_statement = select(func.count(PERSISTED_SAFETY_ALERTS.c.id))
        statement = self._detail_statement().order_by(
            PERSISTED_SAFETY_ALERTS.c.criado_em.desc(),
            PERSISTED_SAFETY_ALERTS.c.id.desc(),
        )
        if condition is not None:
            count_statement = count_statement.where(condition)
            statement = statement.where(condition)
        total = int(self._session.scalar(count_statement) or 0)
        rows = self._session.execute(statement.limit(limit).offset(offset)).mappings()
        return tuple(self._to_record(row) for row in rows), total

    def get(self, alert_id: int) -> AdminAlertRecord:
        row = (
            self._session.execute(
                self._detail_statement().where(PERSISTED_SAFETY_ALERTS.c.id == alert_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AdminAlertNotFoundError("alerta não encontrado")
        return self._to_record(row)

    def confirm(
        self,
        alert_id: int,
        *,
        administrator_id: int,
        observation: str | None,
    ) -> AdminAlertRecord:
        status = self._locked_status(alert_id)
        if status == "encerrado":
            raise AdminAlertStateConflictError("alerta já encerrado")
        if status == "nao_lido":
            values: dict[str, Any] = {
                "status": "lido",
                "confirmado_em": datetime.now(UTC),
                "confirmado_por": administrator_id,
            }
            if observation is not None:
                values["observacao"] = observation
            self._session.execute(
                update(PERSISTED_SAFETY_ALERTS)
                .where(PERSISTED_SAFETY_ALERTS.c.id == alert_id)
                .values(**values)
            )
            self._session.commit()
        elif status != "lido":
            raise AdminAlertStateConflictError("estado do alerta é incompatível")
        return self.get(alert_id)

    def close(
        self,
        alert_id: int,
        *,
        administrator_id: int,
        observation: str | None,
    ) -> AdminAlertRecord:
        status = self._locked_status(alert_id)
        if status == "nao_lido":
            raise AdminAlertStateConflictError("confirme o alerta antes de encerrar a ocorrência")
        if status == "lido":
            values: dict[str, Any] = {
                "status": "encerrado",
                "encerrado_em": datetime.now(UTC),
                "encerrado_por": administrator_id,
            }
            if observation is not None:
                values["observacao"] = observation
            self._session.execute(
                update(PERSISTED_SAFETY_ALERTS)
                .where(PERSISTED_SAFETY_ALERTS.c.id == alert_id)
                .values(**values)
            )
            self._session.commit()
        elif status != "encerrado":
            raise AdminAlertStateConflictError("estado do alerta é incompatível")
        return self.get(alert_id)

    def _locked_status(self, alert_id: int) -> str:
        value = self._session.scalar(
            select(PERSISTED_SAFETY_ALERTS.c.status)
            .where(PERSISTED_SAFETY_ALERTS.c.id == alert_id)
            .with_for_update()
        )
        if value is None:
            raise AdminAlertNotFoundError("alerta não encontrado")
        return str(value).strip().casefold()

    def _detail_statement(self) -> Select[Any]:
        alerts = PERSISTED_SAFETY_ALERTS
        occurrences = SAFETY_OCCURRENCES
        employees = SAFETY_EMPLOYEES
        cameras = SAFETY_CAMERAS
        joined = (
            alerts.join(occurrences, occurrences.c.id == alerts.c.ocorrencia_id)
            .outerjoin(employees, employees.c.id == occurrences.c.funcionario_id)
            .outerjoin(
                self._employee_sector,
                self._employee_sector.c.id == employees.c.setor_id,
            )
            .outerjoin(cameras, cameras.c.id == occurrences.c.camera_id)
            .outerjoin(
                self._camera_sector,
                self._camera_sector.c.id == cameras.c.setor_id,
            )
            .outerjoin(self._ingestion, self._ingestion.c.alerta_id == alerts.c.id)
            .outerjoin(
                self._operator,
                self._operator.c.id == self._ingestion.c.operador_usuario_id,
            )
            .outerjoin(
                self._confirmer,
                self._confirmer.c.id == alerts.c.confirmado_por,
            )
            .outerjoin(self._closer, self._closer.c.id == alerts.c.encerrado_por)
        )
        return select(
            alerts.c.id.label("alert_id"),
            alerts.c.ocorrencia_id.label("occurrence_id"),
            alerts.c.nivel.label("level"),
            alerts.c.status.label("status"),
            alerts.c.observacao.label("observation"),
            alerts.c.criado_em.label("created_at"),
            alerts.c.recebido_em.label("received_at"),
            alerts.c.confirmado_em.label("confirmed_at"),
            alerts.c.confirmado_por.label("confirmed_by_id"),
            self._confirmer.c.nome.label("confirmed_by_name"),
            alerts.c.encerrado_em.label("closed_at"),
            alerts.c.encerrado_por.label("closed_by_id"),
            self._closer.c.nome.label("closed_by_name"),
            occurrences.c.tipo.label("occurrence_type"),
            occurrences.c.descricao.label("occurrence_description"),
            occurrences.c.confianca.label("confidence"),
            occurrences.c.imagem.label("image_reference"),
            occurrences.c.video.label("video_reference"),
            occurrences.c.detectado_em.label("detected_at"),
            employees.c.id.label("employee_id"),
            employees.c.nome.label("employee_name"),
            employees.c.matricula.label("employee_registration"),
            employees.c.cargo.label("employee_role"),
            employees.c.turno.label("employee_shift"),
            self._employee_sector.c.id.label("employee_sector_id"),
            self._employee_sector.c.nome.label("employee_sector_name"),
            cameras.c.id.label("camera_id"),
            cameras.c.nome.label("camera_name"),
            cameras.c.descricao.label("camera_description"),
            self._camera_sector.c.id.label("camera_sector_id"),
            self._camera_sector.c.nome.label("camera_sector_name"),
            self._ingestion.c.evento_id.label("event_id"),
            self._ingestion.c.sessao_trabalho_id.label("work_session_id"),
            self._ingestion.c.operador_usuario_id.label("operator_id"),
            self._operator.c.nome.label("operator_name"),
            self._ingestion.c.operacao_id.label("operation_id"),
            self._ingestion.c.area_risco_id.label("risk_area_id"),
            self._ingestion.c.violacao_tipo.label("violation_type"),
            self._ingestion.c.assunto_chave.label("subject_key"),
            self._ingestion.c.recebido_em.label("ingestion_received_at"),
        ).select_from(joined)

    @staticmethod
    def _to_record(row: RowMapping) -> AdminAlertRecord:
        return AdminAlertRecord(**dict(row))


__all__ = [
    "AdminAlertNotFoundError",
    "AdminAlertRecord",
    "AdminAlertRepository",
    "AdminAlertStateConflictError",
]
