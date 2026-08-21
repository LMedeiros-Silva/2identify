"""Credential authentication use case independent from FastAPI."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import SecretStr

from app.core.security import AccessTokenService, dummy_password_hash, verify_password
from app.repositories import UserRepository


class AuthenticationRejectedError(RuntimeError):
    """Credentials or account policy did not authorize access."""


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    account_id: int
    name: str
    username: str
    profile: str
    access_token: str = field(repr=False)
    expires_in_seconds: int


class AuthenticationService:
    """Authenticate an active account and issue a short-lived access token."""

    def __init__(
        self,
        repository: UserRepository,
        tokens: AccessTokenService,
        allowed_profiles: frozenset[str],
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._allowed_profiles = allowed_profiles

    def authenticate(self, username: str, password: SecretStr) -> AuthenticatedAccount:
        account = self._repository.find_active_by_username(username)
        password_hash = account.senha_hash if account is not None else dummy_password_hash()
        password_matches = verify_password(password, password_hash)

        if account is None or not password_matches:
            raise AuthenticationRejectedError("credenciais rejeitadas")

        name = account.nome.strip()
        username = account.username.strip()
        profile = account.perfil.strip().casefold()
        if not name or not username or profile not in self._allowed_profiles:
            raise AuthenticationRejectedError("conta não autorizada")

        access_token = self._tokens.issue(
            subject=account.id,
            name=name,
            profile=profile,
        )
        return AuthenticatedAccount(
            account_id=account.id,
            name=name,
            username=username,
            profile=profile,
            access_token=access_token,
            expires_in_seconds=self._tokens.expires_in_seconds,
        )
