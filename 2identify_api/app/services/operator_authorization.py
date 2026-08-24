"""Database-backed bearer authorization for Operator API calls."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.security import AccessTokenService, InvalidAccessTokenError
from app.repositories.user_repository import UserRepository


class OperatorAuthorizationRejectedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperatorPrincipal:
    account_id: int
    name: str
    profile: str


class OperatorAuthorizationService:
    def __init__(
        self,
        repository: UserRepository,
        tokens: AccessTokenService,
        allowed_profiles: frozenset[str],
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._allowed_profiles = allowed_profiles

    def authorize(self, token: str) -> OperatorPrincipal:
        try:
            claims = self._tokens.verify(token)
        except InvalidAccessTokenError as error:
            raise OperatorAuthorizationRejectedError("acesso do operador rejeitado") from error
        if claims.profile not in self._allowed_profiles:
            raise OperatorAuthorizationRejectedError("perfil do token rejeitado")
        account = self._repository.find_active_by_id(claims.subject)
        if account is None:
            raise OperatorAuthorizationRejectedError("conta do operador indisponível")
        name = account.nome.strip()
        profile = account.perfil.strip().casefold()
        if not name or profile != claims.profile or profile not in self._allowed_profiles:
            raise OperatorAuthorizationRejectedError("conta do operador não autorizada")
        return OperatorPrincipal(account_id=account.id, name=name, profile=profile)
