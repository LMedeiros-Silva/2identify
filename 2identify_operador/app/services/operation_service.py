"""Use cases for retrieving operations independently from their data source."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from app.domain.operation import Operation

logger = logging.getLogger(__name__)


class OperationServiceError(RuntimeError):
    """Base error exposed by the operation use cases."""


class OperationsUnavailableError(OperationServiceError):
    """The configured source could not provide a trustworthy operation list."""


class InvalidOperationDataError(OperationServiceError):
    """The source returned data that violates the operation contract."""


class OperationProvider(Protocol):
    """Replaceable source used by the operation service."""

    def list_operations(self) -> Sequence[Operation]: ...


class OperationService:
    """Validate and expose active operations from a replaceable provider."""

    def __init__(self, provider: OperationProvider) -> None:
        self._provider = provider

    def list_available_operations(self) -> tuple[Operation, ...]:
        """Return active operations in provider order with unique identifiers."""

        logger.info("operation_list_load_started")
        try:
            received = tuple(self._provider.list_operations())
        except OperationServiceError:
            raise
        except Exception as error:
            raise OperationsUnavailableError(
                "A fonte de operações não pôde ser consultada."
            ) from error

        operation_ids: set[int] = set()
        available: list[Operation] = []
        for operation in received:
            if not isinstance(operation, Operation):
                raise InvalidOperationDataError(
                    "A fonte retornou um item que não é uma Operation."
                )
            if operation.operation_id in operation_ids:
                raise InvalidOperationDataError(
                    f"Identificador de operação duplicado: {operation.operation_id}"
                )
            operation_ids.add(operation.operation_id)
            if operation.active:
                available.append(operation)

        logger.info("operation_list_load_succeeded", extra={"operation_count": len(available)})
        return tuple(available)
