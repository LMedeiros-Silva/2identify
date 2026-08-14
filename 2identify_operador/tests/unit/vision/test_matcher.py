import numpy as np

from app.vision.face_auth.matcher import CosineFaceMatcher
from app.vision.face_auth.types import RegisteredFaceTemplate


def _template(operator_id: int, name: str, embedding: tuple[float, ...]):
    return RegisteredFaceTemplate(
        operator_id=operator_id,
        name=name,
        model_id="test-model",
        embedding=embedding,
    )


def test_cosine_matcher_returns_best_operator_above_threshold() -> None:
    matcher = CosineFaceMatcher(
        [
            _template(1, "Ana", (1.0, 0.0, 0.0) * 11),
            _template(2, "Bruno", (0.0, 1.0, 0.0) * 11),
        ],
        similarity_threshold=0.8,
    )
    query = np.asarray((0.99, 0.01, 0.0) * 11, dtype=np.float32)

    match = matcher.match(query)

    assert match is not None
    assert match.template.operator_id == 1
    assert match.similarity > 0.99


def test_cosine_matcher_rejects_below_threshold() -> None:
    matcher = CosineFaceMatcher(
        [_template(1, "Ana", (1.0, 0.0, 0.0) * 11)],
        similarity_threshold=0.9,
    )
    query = np.asarray((0.0, 1.0, 0.0) * 11, dtype=np.float32)

    assert matcher.match(query) is None

