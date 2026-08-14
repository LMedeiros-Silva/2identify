import pytest

from app.domain import LoginCredentials, OperatorIdentity


def test_login_credentials_normalize_username_and_hide_password_from_repr() -> None:
    credentials = LoginCredentials(username="  operador.01  ", password="segredo")

    assert credentials.username == "operador.01"
    assert credentials.password == "segredo"
    assert "segredo" not in repr(credentials)


@pytest.mark.parametrize(
    ("username", "password"),
    [("", "senha"), ("   ", "senha"), ("operador", "")],
)
def test_login_credentials_reject_empty_fields(username: str, password: str) -> None:
    with pytest.raises(ValueError):
        LoginCredentials(username=username, password=password)


def test_operator_identity_normalizes_data() -> None:
    identity = OperatorIdentity(
        operator_id=8,
        name="  Marina Costa  ",
        confidence=0.96,
        profile_photo_reference="  operators/8/profile.jpg  ",
    )

    assert identity.name == "Marina Costa"
    assert identity.profile_photo_reference == "operators/8/profile.jpg"


@pytest.mark.parametrize(
    ("operator_id", "name", "confidence"),
    [(0, "Marina", 0.9), (8, " ", 0.9), (8, "Marina", 1.1)],
)
def test_operator_identity_rejects_invalid_data(
    operator_id: int,
    name: str,
    confidence: float,
) -> None:
    with pytest.raises(ValueError):
        OperatorIdentity(operator_id=operator_id, name=name, confidence=confidence)
