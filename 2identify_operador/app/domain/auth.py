"""Authentication value objects independent from UI and transport layers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LoginCredentials:
    """Credentials submitted by the login view.

    The password is intentionally excluded from the object representation to reduce
    accidental exposure in logs, tracebacks and diagnostics.
    """

    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        normalized_username = self.username.strip()
        if not normalized_username:
            raise ValueError("username não pode ser vazio")
        if not self.password:
            raise ValueError("password não pode ser vazio")
        object.__setattr__(self, "username", normalized_username)


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    """Operator identity returned after an authoritative biometric match."""

    operator_id: int
    name: str
    confidence: float
    profile_photo_reference: str | None = None

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.operator_id <= 0:
            raise ValueError("operator_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name não pode ser vazio")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence deve estar entre 0.0 e 1.0")

        photo_reference = self.profile_photo_reference
        if photo_reference is not None:
            photo_reference = photo_reference.strip()
            if not photo_reference:
                photo_reference = None

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "profile_photo_reference", photo_reference)


@dataclass(frozen=True, slots=True)
class CredentialAuthenticationResult:
    """Authoritative operator account returned by the authentication API."""

    operator_id: int
    name: str
    access_token: str = field(repr=False)
    token_type: str = "bearer"
    profile_photo_reference: str | None = None

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        normalized_token = self.access_token.strip()
        normalized_token_type = self.token_type.strip().lower()
        if self.operator_id <= 0:
            raise ValueError("operator_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name não pode ser vazio")
        if not normalized_token:
            raise ValueError("access_token não pode ser vazio")
        if normalized_token_type != "bearer":
            raise ValueError("token_type não suportado")

        photo_reference = self.profile_photo_reference
        if photo_reference is not None:
            photo_reference = photo_reference.strip() or None

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "access_token", normalized_token)
        object.__setattr__(self, "token_type", normalized_token_type)
        object.__setattr__(self, "profile_photo_reference", photo_reference)
