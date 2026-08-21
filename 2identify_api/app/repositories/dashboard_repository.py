"""Read-only aggregate queries for the administrative dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ALERTAS, FUNCIONARIO_EPIS, FUNCIONARIOS


@dataclass(frozen=True, slots=True)
class DashboardCounts:
    active_employees: int
    ppe_assignments: int
    delivered_ppe: int
    alerts: int
    critical_alerts: int


class DashboardRepository:
    """Load dashboard counters in one read-only database round trip."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_counts(self) -> DashboardCounts:
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
        alerts = select(func.count(ALERTAS.c.id)).scalar_subquery()
        critical_alerts = (
            select(func.count(ALERTAS.c.id))
            .where(func.lower(func.trim(ALERTAS.c.nivel)) == "critico")
            .scalar_subquery()
        )
        statement = select(
            active_employees.label("active_employees"),
            ppe_assignments.label("ppe_assignments"),
            delivered_ppe.label("delivered_ppe"),
            alerts.label("alerts"),
            critical_alerts.label("critical_alerts"),
        )
        row = self._session.execute(statement).mappings().one()
        return DashboardCounts(
            active_employees=int(row["active_employees"] or 0),
            ppe_assignments=int(row["ppe_assignments"] or 0),
            delivered_ppe=int(row["delivered_ppe"] or 0),
            alerts=int(row["alerts"] or 0),
            critical_alerts=int(row["critical_alerts"] or 0),
        )
