"""Framework-independent business concepts."""

from app.domain.alert import (
    SafetyAlert,
    SafetyAlertSeverity,
    SafetyAlertStatus,
    SafetyViolation,
    SafetyViolationType,
)
from app.domain.auth import CredentialAuthenticationResult, LoginCredentials, OperatorIdentity
from app.domain.identity import EmployeeIdentity
from app.domain.operation import (
    ManualReferenceKind,
    Operation,
    OperationManual,
    PpeRequirement,
    RiskAreaReference,
)
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry
from app.domain.work_session import (
    OperationStartAuthorization,
    WorkSession,
    WorkSessionStatus,
)

__all__ = [
    "CredentialAuthenticationResult",
    "EmployeeIdentity",
    "LoginCredentials",
    "ManualReferenceKind",
    "NormalizedPoint",
    "OperatorIdentity",
    "Operation",
    "OperationManual",
    "OperationStartAuthorization",
    "PpeRequirement",
    "RiskAreaReference",
    "RiskAreaGeometry",
    "SafetyAlert",
    "SafetyAlertSeverity",
    "SafetyAlertStatus",
    "SafetyViolation",
    "SafetyViolationType",
    "WorkSession",
    "WorkSessionStatus",
]
