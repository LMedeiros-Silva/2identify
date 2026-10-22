"""Server-side Face ID: match station probes against Admin templates, issue a session."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite, sqrt

from app.core.security import SUBJECT_EMPLOYEE, AccessTokenService
from app.repositories.face_identity_repository import (
    EmployeeFaceTemplate,
    FaceIdentityRepository,
)

EMPLOYEE_PROFILE = "funcionario"


class FaceAuthenticationRejectedError(RuntimeError):
    """The probes did not identify exactly one authorized employee."""


@dataclass(frozen=True, slots=True)
class AuthenticatedEmployee:
    employee_id: int
    name: str
    access_token: str = field(repr=False)
    expires_in_seconds: int


class FaceAuthenticationService:
    """Every probe must match the same employee, clearly ahead of every other employee.

    Liveness and face detection run at the authenticated station; the API owns the
    templates and the identity decision, so the client never names the employee.
    """

    def __init__(
        self,
        repository: FaceIdentityRepository,
        tokens: AccessTokenService,
        *,
        model_id: str,
        similarity_threshold: float,
        ambiguity_margin: float,
        minimum_probes: int,
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._model_id = model_id
        self._threshold = similarity_threshold
        self._margin = ambiguity_margin
        self._minimum_probes = minimum_probes

    def authenticate(
        self,
        model_id: str,
        probes: Sequence[Sequence[float]],
    ) -> AuthenticatedEmployee:
        if model_id != self._model_id:
            raise FaceAuthenticationRejectedError("modelo facial não suportado")
        if len(probes) < self._minimum_probes:
            raise FaceAuthenticationRejectedError("quadros insuficientes")
        if len({tuple(probe) for probe in probes}) != len(probes):
            # Successive camera frames always differ; a repeated vector is a replay.
            raise FaceAuthenticationRejectedError("quadros repetidos")

        templates = self._repository.templates(model_id)
        matched = {self._best_employee(templates, probe) for probe in probes}
        if len(matched) != 1 or None in matched:
            raise FaceAuthenticationRejectedError("rosto não identificado")
        template = next(item for item in templates if item.employee_id in matched)
        token = self._tokens.issue(
            subject=template.employee_id,
            name=template.name,
            profile=EMPLOYEE_PROFILE,
            subject_type=SUBJECT_EMPLOYEE,
        )
        return AuthenticatedEmployee(
            employee_id=template.employee_id,
            name=template.name,
            access_token=token,
            expires_in_seconds=self._tokens.expires_in_seconds,
        )

    def _best_employee(
        self,
        templates: Sequence[EmployeeFaceTemplate],
        probe: Sequence[float],
    ) -> int | None:
        probe_vector = _normalized(probe)
        if probe_vector is None:
            return None
        scores: list[tuple[float, int]] = []
        for template in templates:
            vector = _normalized(template.embedding)
            if vector is None or len(vector) != len(probe_vector):
                continue
            score = sum(a * b for a, b in zip(vector, probe_vector, strict=True))
            scores.append((score, template.employee_id))
        if not scores:
            return None
        scores.sort(reverse=True)
        best_score, best_employee = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else -1.0
        if best_score < self._threshold or best_score - runner_up < self._margin:
            return None
        return best_employee


def _normalized(values: Sequence[float]) -> tuple[float, ...] | None:
    if not values or not all(isfinite(value) for value in values):
        return None
    norm = sqrt(sum(value * value for value in values))
    if norm <= 1e-12:
        return None
    return tuple(value / norm for value in values)
