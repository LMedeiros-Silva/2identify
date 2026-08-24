"""Errors exposed by the local pose-estimation boundary."""


class PoseVisionError(RuntimeError):
    """Base error for pose model loading and inference."""


class PoseModelUnavailableError(PoseVisionError):
    """The configured pose checkpoint cannot be loaded safely."""


class PoseInferenceError(PoseVisionError):
    """The loaded pose model failed while processing a frame."""
