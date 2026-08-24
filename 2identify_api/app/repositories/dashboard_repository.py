"""Read-only aggregate queries for the administrative dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect

from app.models import (
    FUNCIONARIO_EPIS,
    FUNCIONARIOS,
    PERSISTED_SAFETY_ALERTS,
    SAFETY_OCCURRENCES,
)


@dataclass(frozen=True, slots=True)
class DailyAlertCount:
    day: date
    alerts: int


@dataclass(frozen=True, slots=True)
class DashboardCounts:
    active_employees: int
    ppe_assignments: int
    delivered_ppe: int
    alerts: int
    critical_alerts: int
    new_alerts: int
    confirmed_alerts: int
    closed_alerts: int
    other_status_alerts: int
    ppe_alerts: int
    ergonomics_alerts: int
    risk_area_alerts: int
    monitoring_alerts: int
    other_category_alerts: int
    daily_alerts: tuple[DailyAlertCount, ...]


class DashboardRepository:
    """Load dashboard counters in one read-only database round trip."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_counts(self, *, start_day: date, end_day: date) -> DashboardCounts:
        if end_day < start_day:
            raise ValueError("end_day não pode anteceder start_day")
        active_employees = (
            select(func.count(FUNCIONARIOS.c.id))
            .where(FUNCIONARIOS.c.ativo.is_(True))
            .scalar_subquery()
        )
        ppe_assignments = select(func.count(FUNCIONARIO_EPIS.c.id)).scalar_subquery()
        delivered_ppe = (
            select(func.count(FUNCIONARIO_EPIS.c.id))
            .where(FUNCIONARIO_EPIS.c.entregue.is_(True))
            .scalar_subquery()
        )
        alerts = select(func.count(PERSISTED_SAFETY_ALERTS.c.id)).scalar_subquery()
        critical_alerts = (
            select(func.count(PERSISTED_SAFETY_ALERTS.c.id))
            .where(
                func.lower(func.trim(PERSISTED_SAFETY_ALERTS.c.nivel)).in_(
                    ("critico", "critical")
                )
            )
            .scalar_subquery()
        )
        normalized_status = func.lower(func.trim(PERSISTED_SAFETY_ALERTS.c.status))
        new_alerts = _alert_count_where(
            normalized_status.in_(("nao_lido", "não_lido"))
        )
        confirmed_alerts = _alert_count_where(
            normalized_status.in_(("lido", "confirmado"))
        )
        closed_alerts = _alert_count_where(normalized_status == "encerrado")
        known_statuses = ("nao_lido", "não_lido", "lido", "confirmado", "encerrado")
        other_status_alerts = _alert_count_where(
            normalized_status.not_in(known_statuses)
        )

        normalized_type = func.lower(func.trim(SAFETY_OCCURRENCES.c.tipo))
        ppe_alerts = _category_count_where(
            normalized_type.in_(("ppe_absent", "ppe", "epi"))
        )
        ergonomics_alerts = _category_count_where(
            normalized_type.in_(("ergonomic_risk", "ergonomics", "ergonomia"))
        )
        risk_area_alerts = _category_count_where(
            normalized_type.in_(("person_in_risk_area", "risk_area", "area_risco"))
        )
        monitoring_alerts = _category_count_where(
            normalized_type.in_(("monitoring_interrupted", "monitoring"))
        )
        known_types = (
            "ppe_absent",
            "ppe",
            "epi",
            "ergonomic_risk",
            "ergonomics",
            "ergonomia",
            "person_in_risk_area",
            "risk_area",
            "area_risco",
            "monitoring_interrupted",
            "monitoring",
        )
        other_category_alerts = _category_count_where(
            normalized_type.not_in(known_types)
        )
        statement = select(
            active_employees.label("active_employees"),
            ppe_assignments.label("ppe_assignments"),
            delivered_ppe.label("delivered_ppe"),
            alerts.label("alerts"),
            critical_alerts.label("critical_alerts"),
            new_alerts.label("new_alerts"),
            confirmed_alerts.label("confirmed_alerts"),
            closed_alerts.label("closed_alerts"),
            other_status_alerts.label("other_status_alerts"),
            ppe_alerts.label("ppe_alerts"),
            ergonomics_alerts.label("ergonomics_alerts"),
            risk_area_alerts.label("risk_area_alerts"),
            monitoring_alerts.label("monitoring_alerts"),
            other_category_alerts.label("other_category_alerts"),
        )
        row = self._session.execute(statement).mappings().one()
        daily_alerts = self._daily_alerts(start_day=start_day, end_day=end_day)
        return DashboardCounts(
            active_employees=int(row["active_employees"] or 0),
            ppe_assignments=int(row["ppe_assignments"] or 0),
            delivered_ppe=int(row["delivered_ppe"] or 0),
            alerts=int(row["alerts"] or 0),
            critical_alerts=int(row["critical_alerts"] or 0),
            new_alerts=int(row["new_alerts"] or 0),
            confirmed_alerts=int(row["confirmed_alerts"] or 0),
            closed_alerts=int(row["closed_alerts"] or 0),
            other_status_alerts=int(row["other_status_alerts"] or 0),
            ppe_alerts=int(row["ppe_alerts"] or 0),
            ergonomics_alerts=int(row["ergonomics_alerts"] or 0),
            risk_area_alerts=int(row["risk_area_alerts"] or 0),
            monitoring_alerts=int(row["monitoring_alerts"] or 0),
            other_category_alerts=int(row["other_category_alerts"] or 0),
            daily_alerts=daily_alerts,
        )

    def _daily_alerts(
        self,
        *,
        start_day: date,
        end_day: date,
    ) -> tuple[DailyAlertCount, ...]:
        alert_day = func.date(PERSISTED_SAFETY_ALERTS.c.criado_em)
        statement = (
            select(
                alert_day.label("day"),
                func.count(PERSISTED_SAFETY_ALERTS.c.id).label("alerts"),
            )
            .where(alert_day.between(start_day, end_day))
            .group_by(alert_day)
            .order_by(alert_day)
        )
        observed = {
            _as_date(row["day"]): int(row["alerts"] or 0)
            for row in self._session.execute(statement).mappings()
        }
        days = (end_day - start_day).days + 1
        return tuple(
            DailyAlertCount(
                day=current_day,
                alerts=observed.get(current_day, 0),
            )
            for offset in range(days)
            if (current_day := start_day + timedelta(days=offset))
        )


def _alert_count_where(condition: ColumnElement[bool]) -> ScalarSelect[int]:
    return (
        select(func.count(PERSISTED_SAFETY_ALERTS.c.id))
        .where(condition)
        .scalar_subquery()
    )


def _category_count_where(condition: ColumnElement[bool]) -> ScalarSelect[int]:
    return (
        select(func.count(PERSISTED_SAFETY_ALERTS.c.id))
        .select_from(
            PERSISTED_SAFETY_ALERTS.join(
                SAFETY_OCCURRENCES,
                PERSISTED_SAFETY_ALERTS.c.ocorrencia_id
                == SAFETY_OCCURRENCES.c.id,
            )
        )
        .where(condition)
        .scalar_subquery()
    )


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
