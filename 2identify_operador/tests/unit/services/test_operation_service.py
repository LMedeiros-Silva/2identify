import pytest

from app.domain.operation import Operation
from app.services.operation_service import (
    InvalidOperationDataError,
    OperationService,
    OperationsUnavailableError,
)


class StaticProvider:
    def __init__(self, operations: tuple[Operation, ...]) -> None:
        self.operations = operations

    def list_operations(self) -> tuple[Operation, ...]:
        return self.operations


class FailingProvider:
    def list_operations(self) -> tuple[Operation, ...]:
        raise OSError("fonte indisponível")


def test_operation_service_returns_only_active_operations_in_provider_order() -> None:
    first = Operation(2, "Soldagem")
    inactive = Operation(3, "Operação suspensa", active=False)
    second = Operation(1, "Manutenção")

    result = OperationService(StaticProvider((first, inactive, second))).list_available_operations()

    assert result == (first, second)


def test_operation_service_rejects_duplicate_identifiers() -> None:
    provider = StaticProvider((Operation(1, "Manutenção"), Operation(1, "Soldagem")))

    with pytest.raises(InvalidOperationDataError, match="duplicado"):
        OperationService(provider).list_available_operations()


def test_operation_service_normalizes_unexpected_provider_failures() -> None:
    with pytest.raises(OperationsUnavailableError) as raised:
        OperationService(FailingProvider()).list_available_operations()

    assert isinstance(raised.value.__cause__, OSError)
