"""Errors with user-safe messages for biometric initialization and execution."""


class FaceAuthenticationError(RuntimeError):
    """Base error for the facial-authentication subsystem."""


class FaceAuthenticationUnavailableError(FaceAuthenticationError):
    """A required camera, model or enrollment resource is unavailable."""


class FaceAuthenticationProcessingError(FaceAuthenticationError):
    """A frame could not be processed by the configured biometric pipeline."""

