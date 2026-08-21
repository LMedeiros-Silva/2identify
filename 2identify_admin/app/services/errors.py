class AdminServiceError(RuntimeError):
    """Erro conhecido da camada de serviços do desktop Admin."""


class InvalidCredentialsError(AdminServiceError):
    """As credenciais não foram aceitas pela API."""


class SessionExpiredError(AdminServiceError):
    """O token expirou ou não pode acessar um recurso protegido."""


class ApiUnavailableError(AdminServiceError):
    """A API não pôde ser alcançada ou não respondeu a tempo."""


class InvalidApiResponseError(AdminServiceError):
    """A API respondeu com um payload incompatível com o contrato."""
