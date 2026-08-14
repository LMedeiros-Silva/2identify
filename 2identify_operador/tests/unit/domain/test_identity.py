import pytest

from app.domain import EmployeeIdentity


def test_employee_identity_normalizes_name() -> None:
    identity = EmployeeIdentity(employee_id=15, name="  João Silva  ", confidence=0.94)

    assert identity.name == "João Silva"


@pytest.mark.parametrize(
    "confidence",
    [-0.01, 1.01],
)
def test_employee_identity_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        EmployeeIdentity(employee_id=15, name="João Silva", confidence=confidence)

