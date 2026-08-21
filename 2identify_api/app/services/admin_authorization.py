"""Administrative bearer authorization with database-backed account checks."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.security import AccessTokenService, InvalidAccessTokenError
from app.repositories import UserRepository

_ADMIN_PROFILE = "administrador"


class AdminAuthorizationRejectedError(RuntimeError):
    """The supplied bearer token does not authorize an active administrator."""


@dataclass(frozen=True, slots=True)
class AdministratorPrincipal:
    account_id: int
    name: str
    username: str
    profile: str


class AdminAuthorizationService:
    """Validate the admin JWT and re-check its subject against ``usuarios``."""

    def __init__(self, repository: UserRepository, tokens: AccessTokenService) -> None:
        self._repository = repository
        self._tokens = tokens

    def authorize(self, token: str) -> AdministratorPrincipal:
        try:
            claims = self._tokens.verify(token)
        except InvalidAccessTokenError as error:
            raise AdminAuthorizationRejectedError("acesso administrativo rejeitado") from error

        if claims.profile != _ADMIN_PROFILE:
            raise AdminAuthorizationRejectedError("perfil do token rejeitado")

        account = self._repository.find_active_by_id(claims.subject)
        if account is None:
            raise AdminAuthorizationRejectedError("conta administrativa indisponível")

        name = account.nome.strip()
        username = account.username.strip()
        profile = account.perfil.strip().casefold()
        if not name or not username or profile != _ADMIN_PROFILE:
            raise AdminAuthorizationRejectedError("conta administrativa não autorizada")

        return AdministratorPrincipal(
            account_id=account.id,
            name=name,
            username=username,
            profile=profile,
        )
