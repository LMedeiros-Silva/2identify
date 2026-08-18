"""Authentication use cases independent from HTTP and Qt."""

from __future__ import annotations

import logging
from typing import Protocol

from app.domain.auth import CredentialAuthenticationResult, LoginCredentials

logger = logging.getLogger(__name__)


class AuthenticationError(RuntimeError):
    """Base error exposed by authentication providers."""


class CredentialsRejectedError(AuthenticationError):
    """The remote authority rejected the supplied credentials."""


class AuthenticationUnavailableError(AuthenticationError):
    """The authentication authority could not produce a trustworthy answer."""


class CredentialAuthenticationProvider(Protocol):
    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult: ...


class AuthService:
    """Orchestrate credential authentication through a replaceable provider."""

    def __init__(self, provider: CredentialAuthenticationProvider) -> None:
        self._provider = provider

    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        logger.info("credential_authentication_started")
        result = self._provider.authenticate_credentials(credentials)
        logger.info(
            "credential_authentication_succeeded",
            extra={"operator_id": result.operator_id},
        )
        return result
