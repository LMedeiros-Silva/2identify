import pytest

from app.domain.operation import (
    ManualReferenceKind,
    Operation,
    OperationManual,
    PpeRequirement,
    RiskAreaReference,
)
from app.domain.risk_area import NormalizedPoint, RiskAreaGeometry


def test_risk_area_reference_normalizes_identity() -> None:
    risk_area = RiskAreaReference(risk_area_id=12, name="  Linha de Produção A  ")

    assert risk_area.risk_area_id == 12
    assert risk_area.name == "Linha de Produção A"


def test_risk_area_reference_requires_geometry_before_calibration() -> None:
    geometry = RiskAreaGeometry(
        (
            NormalizedPoint(0.1, 0.1),
            NormalizedPoint(0.9, 0.1),
            NormalizedPoint(0.5, 0.9),
        )
    )

    calibrated = RiskAreaReference(12, "Linha A", geometry, True)

    assert calibrated.geometry is geometry
    assert calibrated.geometry_calibrated
    with pytest.raises(ValueError, match="exige geometria"):
        RiskAreaReference(12, "Linha A", geometry_calibrated=True)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"risk_area_id": 0, "name": "Linha A"},
        {"risk_area_id": 1, "name": "  "},
        {"risk_area_id": 1, "name": "Linha A", "geometry_calibrated": 1},
    ],
)
def test_risk_area_reference_rejects_invalid_identity(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        RiskAreaReference(**kwargs)  # type: ignore[arg-type]


def test_local_operation_manual_normalizes_safe_relative_reference() -> None:
    manual = OperationManual(
        reference="  development/manual.pdf  ",
        kind=ManualReferenceKind.LOCAL_FILE,
        title="  Manual controlado  ",
    )

    assert manual.reference == "development/manual.pdf"
    assert manual.title == "Manual controlado"


@pytest.mark.parametrize(
    "reference",
    [
        "C:\\manuais\\manual.pdf",
        "C:manual.pdf",
        "/opt/manuais/manual.pdf",
        "../manual.pdf",
        "manual.txt",
    ],
)
def test_local_operation_manual_rejects_unsafe_or_non_pdf_reference(
    reference: str,
) -> None:
    with pytest.raises(ValueError):
        OperationManual(reference, ManualReferenceKind.LOCAL_FILE)


def test_remote_operation_manual_requires_safe_http_url() -> None:
    manual = OperationManual(
        "https://api.example.test/operations/7/manual",
        ManualReferenceKind.REMOTE_URL,
    )

    assert manual.kind is ManualReferenceKind.REMOTE_URL
    with pytest.raises(ValueError, match="credenciais"):
        OperationManual(
            "https://usuario:senha@example.test/manual.pdf",
            ManualReferenceKind.REMOTE_URL,
        )


def test_ppe_requirement_normalizes_catalog_name() -> None:
    requirement = PpeRequirement(
        ppe_id=4,
        name="  Mangotes  ",
        detection_class="  MANGOTE  ",
    )

    assert requirement.ppe_id == 4
    assert requirement.name == "Mangotes"
    assert requirement.detection_class == "mangote"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ppe_id": 0, "name": "Capacete"},
        {"ppe_id": 1, "name": "  "},
    ],
)
def test_ppe_requirement_rejects_invalid_catalog_identity(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        PpeRequirement(**kwargs)  # type: ignore[arg-type]


def test_operation_normalizes_text_fields() -> None:
    operation = Operation(
        operation_id=7,
        name="  Manutenção elétrica  ",
        description="   ",
    )

    assert operation.name == "Manutenção elétrica"
    assert operation.description is None
    assert operation.required_ppe == ()
    assert operation.manual is None
    assert operation.risk_area is None
    assert operation.active is True


def test_operation_preserves_configured_ppe_relationship() -> None:
    helmet = PpeRequirement(1, "Capacete")
    boots = PpeRequirement(2, "Botas")

    operation = Operation(
        operation_id=7,
        name="Manutenção",
        required_ppe=(helmet, boots),
    )

    assert operation.required_ppe == (helmet, boots)


def test_operation_rejects_duplicate_required_ppe() -> None:
    with pytest.raises(ValueError, match="duplicado"):
        Operation(
            operation_id=7,
            name="Manutenção",
            required_ppe=(
                PpeRequirement(1, "Capacete"),
                PpeRequirement(1, "Outro capacete"),
            ),
        )


def test_operation_rejects_duplicate_detection_class_mapping() -> None:
    with pytest.raises(ValueError, match="detection_class.*duplicada"):
        Operation(
            operation_id=7,
            name="Manutenção",
            required_ppe=(
                PpeRequirement(1, "Capacete", "capacete"),
                PpeRequirement(2, "Outro capacete", "CAPACETE"),
            ),
        )


def test_operation_accepts_a_typed_manual_reference() -> None:
    manual = OperationManual("manual.pdf", ManualReferenceKind.LOCAL_FILE)

    operation = Operation(operation_id=7, name="Manutenção", manual=manual)

    assert operation.manual is manual


def test_operation_accepts_a_typed_risk_area_reference() -> None:
    risk_area = RiskAreaReference(12, "Linha de Produção A")

    operation = Operation(operation_id=7, name="Manutenção", risk_area=risk_area)

    assert operation.risk_area is risk_area


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation_id": 0, "name": "Manutenção"},
        {"operation_id": 1, "name": "  "},
        {"operation_id": 1, "name": "Manutenção", "active": 1},
    ],
)
def test_operation_rejects_invalid_identity_or_state(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Operation(**kwargs)  # type: ignore[arg-type]
