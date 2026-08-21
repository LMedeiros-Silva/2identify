"""Security primitive tests without external services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.security import (
    AccessTokenService,
    InvalidAccessTokenError,
    dummy_password_hash,
    verify_password,
)

TEST_SECRET = "another-test-secret-with-at-least-32-bytes"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": (
            "postgresql+psycopg2://test_user:test_password@localhost:5432/test_database"
        ),
        "app_env": "testing",
        "auth_token_secret": TEST_SECRET,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_password_verification_is_compatible_with_admin_bcrypt_hashes() -> None:
    password_hash = bcrypt.hashpw(b"senha-segura", bcrypt.gensalt()).decode()

    assert verify_password(SecretStr("senha-segura"), password_hash) is True
    assert verify_password(SecretStr("senha-errada"), password_hash) is False
    assert verify_password(SecretStr("senha"), "hash-malformado") is False
    assert verify_password(SecretStr("x" * 73), password_hash) is False
    assert verify_password(SecretStr("qualquer"), dummy_password_hash()) is False


def test_access_token_round_trip_uses_fixed_algorithm_and_required_claims() -> None:
    service = AccessTokenService(make_settings())

    token = service.issue(subject=15, name="João Silva", profile="operador")
    claims = service.verify(token)

    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    assert claims.subject == 15
    assert claims.expires_at > claims.issued_at
    assert claims.token_id


def test_tampered_or_wrong_audience_tokens_are_rejected() -> None:
    service = AccessTokenService(make_settings())
    token = service.issue(subject=15, name="João Silva", profile="operador")
    header, payload, signature = token.split(".")
    altered_first_character = "A" if signature[0] != "A" else "B"
    tampered = f"{header}.{payload}.{altered_first_character}{signature[1:]}"

    with pytest.raises(InvalidAccessTokenError):
        service.verify(tampered)

    other_audience_service = AccessTokenService(
        make_settings(auth_token_audience="different-client")
    )
    with pytest.raises(InvalidAccessTokenError):
        other_audience_service.verify(token)


def test_operator_and_admin_audiences_are_mutually_exclusive() -> None:
    settings = make_settings()
    operator_tokens = AccessTokenService(settings)
    admin_tokens = AccessTokenService(
        settings,
        audience=settings.auth_admin_token_audience,
    )
    operator_token = operator_tokens.issue(subject=15, name="Operador", profile="operador")
    admin_token = admin_tokens.issue(
        subject=1,
        name="Administrador",
        profile="administrador",
    )

    with pytest.raises(InvalidAccessTokenError):
        admin_tokens.verify(operator_token)
    with pytest.raises(InvalidAccessTokenError):
        operator_tokens.verify(admin_token)


@pytest.mark.parametrize(
    ("subject", "name", "profile"),
    [(0, "Conta", "operador"), (-1, "Conta", "operador"), (1, " ", "operador")],
)
def test_access_token_issuance_rejects_invalid_identity(
    subject: int,
    name: str,
    profile: str,
) -> None:
    with pytest.raises(ValueError):
        AccessTokenService(make_settings()).issue(
            subject=subject,
            name=name,
            profile=profile,
        )


def test_expired_token_is_rejected() -> None:
    settings = make_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "15",
            "name": "João Silva",
            "profile": "operador",
            "iat": now - timedelta(minutes=2),
            "nbf": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
            "iss": settings.auth_token_issuer,
            "aud": settings.auth_token_audience,
            "jti": "expired-token-id",
        },
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        AccessTokenService(settings).verify(token)


@pytest.mark.parametrize(
    "claim_override",
    [
        {"sub": "01"},
        {"name": " Operador"},
        {"profile": "Operador"},
        {"jti": " token-id"},
    ],
)
def test_signed_tokens_with_noncanonical_claims_are_rejected(
    claim_override: dict[str, object],
) -> None:
    settings = make_settings()
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": "15",
        "name": "João Silva",
        "profile": "operador",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.auth_token_issuer,
        "aud": settings.auth_token_audience,
        "jti": "canonical-token-id",
    }
    payload.update(claim_override)
    token = jwt.encode(
        payload,
        settings.auth_token_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        AccessTokenService(settings).verify(token)


@pytest.mark.parametrize(
    "secret",
    ["short", "CHANGE_ME_WITH_AT_LEAST_32_RANDOM_CHARACTERS"],
)
def test_auth_token_secret_must_be_strong_and_not_a_placeholder(secret: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(auth_token_secret=secret)


def test_auth_token_secret_is_hidden_from_settings_representation() -> None:
    settings = make_settings()

    assert TEST_SECRET not in repr(settings)
