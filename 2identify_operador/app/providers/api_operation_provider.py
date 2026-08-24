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
    ) -> None:
        self._client = client
        self._session_context = session_context

    def list_operations(self) -> tuple[Operation, ...]:
        session = self._session_context.current
        if session is None:
            raise OperationsUnavailableError(
                "Nenhum operador está autenticado para consultar as operações."
            )
        if session.access_token is None:
            raise OperationsUnavailableError(
                "Entre com usuário e senha para carregar as operações cadastradas na API."
            )
        return self._client.list_operations(session.access_token)
