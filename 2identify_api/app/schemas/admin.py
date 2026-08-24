"""Administrative identity and dashboard response contracts."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, Field


class AdminAlertStatusBreakdown(BaseModel):
    new: int = Field(ge=0)
    confirmed: int = Field(ge=0)
    closed: int = Field(ge=0)
    other: int = Field(ge=0)


class AdminAlertCategoryBreakdown(BaseModel):
    ppe: int = Field(ge=0)
    ergonomics: int = Field(ge=0)
    risk_area: int = Field(ge=0)
    monitoring: int = Field(ge=0)
    other: int = Field(ge=0)


class AdminAlertTrendPoint(BaseModel):
    day: date
    alerts: int = Field(ge=0)


class AdminDashboardSummary(BaseModel):
    active_employees: int = Field(ge=0)
    ppe_assignments: int = Field(ge=0)
    delivered_ppe: int = Field(ge=0)
    ppe_delivery_percentage: float = Field(ge=0.0, le=100.0)
    alerts: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)
    alert_status: AdminAlertStatusBreakdown
    alert_categories: AdminAlertCategoryBreakdown
    alert_trend: tuple[AdminAlertTrendPoint, ...] = Field(min_length=7, max_length=7)
    generated_at: AwareDatetime
