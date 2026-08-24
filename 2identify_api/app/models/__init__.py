"""SQLAlchemy mappings explicitly reconciled with the real PostgreSQL schema."""

from app.models.base import Base
from app.models.dashboard import ALERTAS, FUNCIONARIO_EPIS, FUNCIONARIOS
from app.models.operation import (
    CATALOG_CAMERAS,
    CATALOG_EPIS,
    CATALOG_SECTORS,
    OPERATION_EPIS,
    OPERATIONS,
    RISK_AREAS,
)
from app.models.safety_alert import (
    PERSISTED_SAFETY_ALERTS,
    SAFETY_CAMERAS,
    SAFETY_EMPLOYEES,
    SAFETY_OCCURRENCES,
    SAFETY_SECTORS,
    SafetyAlertIngestion,
)
from app.models.usuario import Usuario

__all__ = [
    "ALERTAS",
    "Base",
    "CATALOG_CAMERAS",
    "CATALOG_EPIS",
    "CATALOG_SECTORS",
    "FUNCIONARIO_EPIS",
    "FUNCIONARIOS",
    "OPERATIONS",
    "OPERATION_EPIS",
    "PERSISTED_SAFETY_ALERTS",
    "SAFETY_CAMERAS",
    "SAFETY_EMPLOYEES",
    "SAFETY_OCCURRENCES",
    "SAFETY_SECTORS",
    "SafetyAlertIngestion",
    "RISK_AREAS",
    "Usuario",
]
