"""Password verification and signed access-token infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

import bcrypt
import jwt
from pydantic import SecretStr

from app.core.config import Settings

_JWT_ALGORITHM = "HS256"
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"2identify-dummy-password", bcrypt.gensalt())


def verify_password(password: SecretStr, password_hash: str) -> bool:
    """Fail closed for invalid hashes and bcrypt inputs longer than 72 bytes."""

    password_bytes = password.get_secret_value().encode("utf-8")
    if not password_bytes or len(password_bytes) > 72:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def dummy_password_hash() -> str:
    """Provide a valid hash so unknown accounts still perform one bcrypt check."""

    return _DUMMY_PASSWORD_HASH.decode("ascii")


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: int
    name: str
    profile: str
    issued_at: datetime
    expires_at: datetime
    token_id: str


class InvalidAccessTokenError(RuntimeError):
    """Raised when a bearer token is invalid, expired or from another audience."""


class AccessTokenService:
    """Issue and verify short-lived JWT access tokens with fixed cryptographic policy."""

    def __init__(self, settings: Settings, *, audience: str | None = None) -> None:
        self._secret = settings.auth_token_secret
        self._ttl = timedelta(minutes=settings.auth_token_ttl_minutes)
        self._issuer = settings.auth_token_issuer
        self._audience = audience if audience is not None else settings.auth_token_audience
        if not isinstance(self._audience, str) or not self._audience.strip():
            raise ValueError("audience do token não pode ser vazio")

    @property
    def expires_in_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, *, subject: int, name: str, profile: str) -> str:
        normalized_name = name.strip()
        normalized_profile = profile.strip().casefold()
        if subject <= 0 or not normalized_name or not normalized_profile:
            raise ValueError("identidade inválida para emissão do token")

        now = datetime.now(UTC)
        payload = {
            "sub": str(subject),
            "name": normalized_name,
            "profile": normalized_profile,
            "iat": now,
            "nbf": now,
            "exp": now + self._ttl,
            "iss": self._issuer,
            "aud": self._audience,
            "jti": token_urlsafe(24),
        }
        return jwt.encode(
            payload,
            self._secret.get_secret_value(),
            algorithm=_JWT_ALGORITHM,
        )

    def verify(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret.get_secret_value(),
                algorithms=[_JWT_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": [
                        "sub",
                        "name",
                        "profile",
                        "iat",
                        "nbf",
                        "exp",
                        "iss",
                        "aud",
                        "jti",
                    ],
                    "strict_aud": True,
                },
            )
            subject = payload["sub"]
            name = payload["name"]
            profile = payload["profile"]
            issued_at = payload["iat"]
            expires_at = payload["exp"]
            not_before = payload["nbf"]
            token_id = payload["jti"]
            if (
                type(subject) is not str
                or not subject.isascii()
                or not subject.isdecimal()
                or int(subject) <= 0
                or str(int(subject)) != subject
                or type(name) is not str
                or not name.strip()
                or name != name.strip()
                or type(profile) is not str
                or not profile.strip()
                or profile != profile.strip().casefold()
                or type(token_id) is not str
                or not token_id.strip()
                or token_id != token_id.strip()
                or type(issued_at) is not int
                or type(expires_at) is not int
                or type(not_before) is not int
                or not issued_at <= not_before < expires_at
            ):
                raise InvalidAccessTokenError("token de acesso inválido")

            return AccessTokenClaims(
                subject=int(subject),
                name=name,
                profile=profile,
                issued_at=datetime.fromtimestamp(issued_at, tz=UTC),
                expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
                token_id=token_id,
            )
        except (jwt.PyJWTError, KeyError, OSError, OverflowError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError("token de acesso inválido") from error
