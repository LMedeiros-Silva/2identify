"""Administrative dashboard aggregation without business-data mutations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.repositories import DashboardRepository


@dataclass(frozen=True, slots=True)
class AdminDashboardData:
    active_employees: int
    ppe_assignments: int
    delivered_ppe: int
    ppe_delivery_percentage: float
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
    daily_alerts: tuple[tuple[date, int], ...]
    generated_at: datetime


class AdminDashboardService:
    """Build operational counters; the percentage describes PPE delivery only."""

    def __init__(
        self,
        repository: DashboardRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_summary(self) -> AdminDashboardData:
        generated_at = self._clock()
        end_day = generated_at.date()
        counts = self._repository.get_counts(
            start_day=end_day - timedelta(days=6),
            end_day=end_day,
        )
        delivery_percentage = (
            round((counts.delivered_ppe / counts.ppe_assignments) * 100, 1)
            if counts.ppe_assignments
            else 0.0
        )
        return AdminDashboardData(
            active_employees=counts.active_employees,
            ppe_assignments=counts.ppe_assignments,
            delivered_ppe=counts.delivered_ppe,
            ppe_delivery_percentage=delivery_percentage,
            alerts=counts.alerts,
            critical_alerts=counts.critical_alerts,
            new_alerts=counts.new_alerts,
            confirmed_alerts=counts.confirmed_alerts,
            closed_alerts=counts.closed_alerts,
            other_status_alerts=counts.other_status_alerts,
            ppe_alerts=counts.ppe_alerts,
            ergonomics_alerts=counts.ergonomics_alerts,
            risk_area_alerts=counts.risk_area_alerts,
            monitoring_alerts=counts.monitoring_alerts,
            other_category_alerts=counts.other_category_alerts,
            daily_alerts=tuple(
                (item.day, item.alerts) for item in counts.daily_alerts
            ),
            generated_at=generated_at,
        )
