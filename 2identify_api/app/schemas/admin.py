"""Administrative identity and dashboard response contracts."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field


class AdminDashboardSummary(BaseModel):
    active_employees: int = Field(ge=0)
    ppe_assignments: int = Field(ge=0)
    delivered_ppe: int = Field(ge=0)
    ppe_delivery_percentage: float = Field(ge=0.0, le=100.0)
    alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    generated_at: AwareDatetime
