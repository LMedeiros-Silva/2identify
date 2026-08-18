"""Expected failures raised by PPE model adapters."""


class PpeVisionError(RuntimeError):
    """Base error safe for the PPE inference boundary."""


class PpeModelUnavailableError(PpeVisionError):
    """The configured model artifact or runtime cannot be loaded."""


class PpeInferenceError(PpeVisionError):
    """One frame could not be processed by the loaded model."""
