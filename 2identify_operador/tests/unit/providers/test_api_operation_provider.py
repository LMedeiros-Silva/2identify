from datetime import UTC, datetime

import pytest

from app.core.session import AuthenticationMethod, OperatorSessionContext
from app.domain import Operation
from app.providers.api_operation_provider import ApiOperationProvider
from app.services.operation_service import OperationsUnavailableError


class RecordingClient:
    def __init__(self) -> None:
        self.token: str | None = None
        self.catalog_token: str | None = None

    def list_operations(self, access_token: str) -> tuple[Operation, ...]:
        self.token = access_token
        return (Operation(41, "Soldagem"),)

    def list_operations_with_catalog_token(
        self,
        catalog_token: str,
    ) -> tuple[Operation, ...]:
        self.catalog_token = catalog_token
        return (Operation(41, "Soldagem"),)


def test_api_provider_uses_current_session_token() -> None:
    client = RecordingClient()
    context = OperatorSessionContext(
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    )
    context.open(2, "Operador Teste", AuthenticationMethod.CREDENTIALS, "token-api")
    provider = ApiOperationProvider(client, context)  # type: ignore[arg-type]

    operations = provider.list_operations()

    assert operations == (Operation(41, "Soldagem"),)
    assert client.token == "token-api"


def test_api_provider_uses_read_only_catalog_token_for_face_id_session() -> None:
    client = RecordingClient()
    context = OperatorSessionContext(
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    )
    context.open(2, "Operador Teste", AuthenticationMethod.FACE_ID)
    provider = ApiOperationProvider(  # type: ignore[arg-type]
        client,
        context,
        operator_catalog_token="catalog-token-with-at-least-thirty-two-bytes",
    )

    operations = provider.list_operations()

    assert operations == (Operation(41, "Soldagem"),)
    assert client.catalog_token == "catalog-token-with-at-least-thirty-two-bytes"
    assert client.token is None


def test_api_provider_reports_missing_catalog_token_for_face_id_session() -> None:
    context = OperatorSessionContext(
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    )
    context.open(2, "Operador Teste", AuthenticationMethod.FACE_ID)
    provider = ApiOperationProvider(RecordingClient(), context)  # type: ignore[arg-type]

    with pytest.raises(OperationsUnavailableError, match="token de catálogo"):
        provider.list_operations()
