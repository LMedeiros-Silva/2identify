"""Authenticated API-backed operation catalog provider."""

from __future__ import annotations

from app.api.client import OperatorApiClient
from app.core.session import OperatorSessionContext
from app.domain.operation import Operation
from app.services.operation_service import OperationsUnavailableError


class ApiOperationProvider:
    """Read active operations using the current authenticated API session."""

    def __init__(
        self,
        client: OperatorApiClient,
        session_context: OperatorSessionContext,
        operator_catalog_token: str | None = None,
    ) -> None:
        self._client = client
        self._session_context = session_context
        self._operator_catalog_token = (
            operator_catalog_token.strip() if operator_catalog_token is not None else None
        )

    def list_operations(self) -> tuple[Operation, ...]:
        session = self._session_context.current
        if session is None:
            raise OperationsUnavailableError(
                "Nenhum operador está autenticado para consultar as operações."
            )
        if session.access_token is not None:
            return self._client.list_operations(session.access_token)
        if self._operator_catalog_token:
            return self._client.list_operations_with_catalog_token(
                self._operator_catalog_token
            )
        raise OperationsUnavailableError(
            "Configure o token de catálogo nesta estação para carregar operações "
            "após o acesso por Face ID."
        )
