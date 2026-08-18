from app.domain import CredentialAuthenticationResult, LoginCredentials
from app.services.auth_service import AuthService


class RecordingProvider:
    def __init__(self, result: CredentialAuthenticationResult) -> None:
        self.result = result
        self.received: LoginCredentials | None = None

    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        self.received = credentials
        return self.result


def test_auth_service_delegates_to_configured_provider() -> None:
    expected = CredentialAuthenticationResult(
        operator_id=15,
        name="João Silva",
        access_token="token",
    )
    provider = RecordingProvider(expected)
    service = AuthService(provider)
    credentials = LoginCredentials("operador.15", "segredo")

    result = service.authenticate_credentials(credentials)

    assert result is expected
    assert provider.received is credentials
