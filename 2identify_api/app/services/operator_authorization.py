"""Database-backed bearer authorization for Operator API calls."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass

from app.core.security import (
    SUBJECT_ACCOUNT,
    SUBJECT_EMPLOYEE,
    AccessTokenService,
    InvalidAccessTokenError,
)
from app.repositories.face_identity_repository import FaceIdentityRepository
from app.repositories.safety_alert_repository import session_owner
from app.repositories.user_repository import UserRepository
from app.services.face_authentication import EMPLOYEE_PROFILE


class OperatorAuthorizationRejectedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperatorPrincipal:
    """A password account (usuarios) or an employee identified by Face ID (funcionarios)."""

    account_id: int | None
    name: str
    profile: str
    employee_id: int | None = None

    def __post_init__(self) -> None:
        if (self.account_id is None) == (self.employee_id is None):
            raise ValueError("o operador deve ser uma conta ou um funcionário")

    @property
    def operator_id(self) -> int:
        """Display id: the account id, or the employee id for a Face ID session."""

        return self.account_id if self.account_id is not None else self.employee_id  # type: ignore[return-value]

    @property
    def session_owner(self) -> Hashable:
        return session_owner(self.account_id, self.employee_id)


class OperatorAuthorizationService:
    def __init__(
        self,
        repository: UserRepository,
        tokens: AccessTokenService,
        allowed_profiles: frozenset[str],
        employees: FaceIdentityRepository | None = None,
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._allowed_profiles = allowed_profiles
        self._employees = employees

    def authorize(self, token: str) -> OperatorPrincipal:
        try:
            claims = self._tokens.verify(token)
        except InvalidAccessTokenError as error:
            raise OperatorAuthorizationRejectedError("acesso do operador rejeitado") from error
        if claims.subject_type == SUBJECT_EMPLOYEE:
            return self._authorize_employee(claims.subject, claims.profile)
        if claims.subject_type != SUBJECT_ACCOUNT or claims.profile not in self._allowed_profiles:
            raise OperatorAuthorizationRejectedError("perfil do token rejeitado")
        account = self._repository.find_active_by_id(claims.subject)
        if account is None:
            raise OperatorAuthorizationRejectedError("conta do operador indisponível")
        name = account.nome.strip()
        profile = account.perfil.strip().casefold()
        if not name or profile != claims.profile or profile not in self._allowed_profiles:
            raise OperatorAuthorizationRejectedError("conta do operador não autorizada")
        return OperatorPrincipal(account_id=account.id, name=name, profile=profile)

    def _authorize_employee(self, employee_id: int, profile: str) -> OperatorPrincipal:
        # Revalidated on every call: deactivating the employee ends the session at once.
        if self._employees is None or profile != EMPLOYEE_PROFILE:
            raise OperatorAuthorizationRejectedError("perfil do token rejeitado")
        employee = self._employees.find_authorized_employee(employee_id)
        if employee is None:
            raise OperatorAuthorizationRejectedError("funcionário não autorizado")
        return OperatorPrincipal(
            account_id=None,
            name=employee.name,
            profile=EMPLOYEE_PROFILE,
            employee_id=employee.employee_id,
        )
