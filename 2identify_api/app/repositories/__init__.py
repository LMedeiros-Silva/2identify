"""Persistence adapters for existing 2Identify entities."""

from app.repositories.admin_alert_repository import (
    AdminAlertNotFoundError,
    AdminAlertRecord,
    AdminAlertRepository,
    AdminAlertStateConflictError,
)
from app.repositories.dashboard_repository import DashboardCounts, DashboardRepository
from app.repositories.operation_repository import (
    OperationConfigurationConflictError,
    OperationConfigurationNotFoundError,
    OperationRepository,
)
from app.repositories.safety_alert_repository import (
    AlertEventConflictError,
    SafetyAlertRepository,
    StoredAlert,
)
from app.repositories.user_repository import UserRepository

__all__ = [
    "AdminAlertNotFoundError",
    "AdminAlertRecord",
    "AdminAlertRepository",
    "AdminAlertStateConflictError",
    "AlertEventConflictError",
    "DashboardCounts",
    "DashboardRepository",
    "OperationConfigurationConflictError",
    "OperationConfigurationNotFoundError",
    "OperationRepository",
    "SafetyAlertRepository",
    "StoredAlert",
    "UserRepository",
]
