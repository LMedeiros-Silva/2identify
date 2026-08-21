"""Administrative dashboard aggregation without business-data mutations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.repositories import DashboardRepository


@dataclass(frozen=True, slots=True)
class AdminDashboardData:
    active_employees: int
    ppe_assignments: int
    delivered_ppe: int
    ppe_delivery_percentage: float
    alerts: int
    critical_alerts: int
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
        counts = self._repository.get_counts()
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
            generated_at=self._clock(),
        )
