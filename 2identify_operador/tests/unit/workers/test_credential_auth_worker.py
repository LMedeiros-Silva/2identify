from app.domain import CredentialAuthenticationResult, LoginCredentials
from app.services.auth_service import (
    AuthenticationUnavailableError,
    AuthService,
    CredentialsRejectedError,
)
from app.workers.credential_auth_worker import CredentialAuthenticationWorker


class SuccessfulProvider:
    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        assert credentials.username == "operador.15"
        return CredentialAuthenticationResult(15, "João Silva", "token")


class FailingProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def authenticate_credentials(
        self,
        credentials: LoginCredentials,
    ) -> CredentialAuthenticationResult:
        del credentials
        raise self._error


def test_worker_emits_successful_result(qtbot) -> None:
    worker = CredentialAuthenticationWorker(
        AuthService(SuccessfulProvider()),
        LoginCredentials("operador.15", "segredo"),
    )

    with qtbot.waitSignal(worker.authentication_succeeded, timeout=2_000) as emitted:
        worker.start()

    assert isinstance(emitted.args[0], CredentialAuthenticationResult)
    assert worker.wait(2_000)


def test_worker_distinguishes_rejected_credentials(qtbot) -> None:
    worker = CredentialAuthenticationWorker(
        AuthService(FailingProvider(CredentialsRejectedError("Usuário ou senha inválidos."))),
        LoginCredentials("operador.15", "incorreta"),
    )

    with qtbot.waitSignal(worker.authentication_failed, timeout=2_000) as emitted:
        worker.start()

    assert emitted.args == ["Usuário ou senha inválidos.", False]
    assert worker.wait(2_000)


def test_worker_marks_api_failure_as_unavailable(qtbot) -> None:
    worker = CredentialAuthenticationWorker(
        AuthService(FailingProvider(AuthenticationUnavailableError("API indisponível."))),
        LoginCredentials("operador.15", "segredo"),
    )

    with qtbot.waitSignal(worker.authentication_failed, timeout=2_000) as emitted:
        worker.start()

    assert emitted.args == ["API indisponível.", True]
    assert worker.wait(2_000)
