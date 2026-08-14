"""Normalized cosine matching for registered operator templates."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.vision.face_auth.errors import FaceAuthenticationUnavailableError
from app.vision.face_auth.types import Embedding, FaceMatch, RegisteredFaceTemplate


class CosineFaceMatcher:
    def __init__(
        self,
        templates: Sequence[RegisteredFaceTemplate],
        similarity_threshold: float,
    ) -> None:
        if not templates:
            raise FaceAuthenticationUnavailableError(
                "Nenhum operador possui biometria facial cadastrada neste equipamento."
            )
        dimensions = {len(template.embedding) for template in templates}
        if len(dimensions) != 1:
            raise FaceAuthenticationUnavailableError(
                "O cadastro biométrico contém embeddings incompatíveis."
            )

        matrix = np.asarray([template.embedding for template in templates], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 1e-12):
            raise FaceAuthenticationUnavailableError(
                "O cadastro biométrico contém embeddings inválidos."
            )

        self._templates = tuple(templates)
        self._matrix = np.asarray(matrix / norms, dtype=np.float32)
        self._similarity_threshold = similarity_threshold

    def match(self, embedding: Embedding) -> FaceMatch | None:
        normalized = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if normalized.shape[0] != self._matrix.shape[1]:
            raise FaceAuthenticationUnavailableError(
                "O embedding capturado não é compatível com os templates cadastrados."
            )
        norm = float(np.linalg.norm(normalized))
        if not np.isfinite(norm) or norm <= 1e-12:
            return None

        similarities = self._matrix @ (normalized / norm)
        best_index = int(np.argmax(similarities))
        best_similarity = float(similarities[best_index])
        if best_similarity < self._similarity_threshold:
            return None
        return FaceMatch(self._templates[best_index], best_similarity)

