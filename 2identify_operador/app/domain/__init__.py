"""Framework-independent business concepts."""

from app.domain.auth import LoginCredentials, OperatorIdentity
from app.domain.identity import EmployeeIdentity

__all__ = ["EmployeeIdentity", "LoginCredentials", "OperatorIdentity"]
