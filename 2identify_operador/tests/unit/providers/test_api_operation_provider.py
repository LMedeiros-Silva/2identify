from datetime import UTC, datetime

import pytest

from app.core.session import AuthenticationMethod, OperatorSessionContext
from app.domain import Operation
from app.providers.api_operation_provider import ApiOperationProvider
from app.services.operation_service import OperationsUnavailableError


class RecordingClient:
    def __init__(self) -> None:
        self.token: str | None = None

    def list_operations(self, access_token: str) -> tuple[Operation, ...]:
        self.token = access_token
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


def test_api_provider_requires_credential_api_session() -> None:
    context = OperatorSessionContext(
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    )
    context.open(2, "Operador Teste", AuthenticationMethod.FACE_ID)
    provider = ApiOperationProvider(RecordingClient(), context)  # type: ignore[arg-type]

    with pytest.raises(OperationsUnavailableError, match="usuário e senha"):
        provider.list_operations()
