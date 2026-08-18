from app.core.constants import PROJECT_ROOT
from app.domain.operation import Operation
from app.providers import MockOperationProvider


def test_mock_operation_provider_exposes_clearly_scoped_development_data() -> None:
    operations = MockOperationProvider().list_operations()

    assert len(operations) == 4
    assert all(isinstance(operation, Operation) for operation in operations)
    assert [operation.name for operation in operations] == [
        "Manutenção industrial",
        "Soldagem",
        "Manutenção elétrica",
        "Carga e descarga",
    ]
    requirements_by_operation = {
        operation.name: [requirement.name for requirement in operation.required_ppe]
        for operation in operations
    }
    assert requirements_by_operation["Manutenção industrial"] == [
        "Capacete de segurança",
        "Mangotes",
        "Botas de segurança",
    ]
    assert requirements_by_operation["Soldagem"] == [
        "Capacete de segurança",
        "Luvas de proteção",
        "Botas de segurança",
        "Mangotes",
    ]
    assert {
        requirement.detection_class
        for operation in operations
        for requirement in operation.required_ppe
    } == {"bota", "capacete", "luva", "mangote"}
    assert operations[0].manual is not None
    assert operations[0].manual.reference == "development/manutencao-industrial-demo.pdf"
    assert all(operation.manual is None for operation in operations[1:])
    assert [
        operation.risk_area.name if operation.risk_area is not None else None
        for operation in operations
    ] == [
        "Linha de Produção A",
        "Célula de soldagem",
        "Sala elétrica",
        "Doca de recebimento",
    ]
    assert all(
        operation.risk_area is not None
        and operation.risk_area.geometry is not None
        and not operation.risk_area.geometry_calibrated
        for operation in operations
    )


def test_mock_operation_provider_accepts_an_explicit_empty_dataset() -> None:
    assert MockOperationProvider(()).list_operations() == ()


def test_mock_operation_manual_points_to_packaged_pdf_asset() -> None:
    operation = MockOperationProvider().list_operations()[0]
    assert operation.manual is not None
    manual_path = PROJECT_ROOT / "assets/manuals" / operation.manual.reference

    assert manual_path.is_file()
    assert manual_path.read_bytes()[:5] == b"%PDF-"
