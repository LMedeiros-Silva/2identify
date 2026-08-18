"""Fail-closed PPE compliance assessment for one industrial operation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.operation import Operation, PpeRequirement
from app.engine.ppe_stability import PpeStabilitySnapshot, PpeStabilityState


class PpeRequirementSafetyState(StrEnum):
    """Safety meaning assigned to one configured PPE requirement."""

    COLLECTING = "collecting"
    CONFIRMED = "confirmed"
    ABSENT = "absent"
    UNSTABLE = "unstable"
    UNMAPPED = "unmapped"


class PpeSafetyStatus(StrEnum):
    """Overall PPE verification state used by the operation release gate."""

    PENDING = "pending"
    BLOCKED = "blocked"
    COMPLIANT = "compliant"


@dataclass(frozen=True, slots=True)
class PpeRequirementAssessment:
    """One operation requirement compared with stabilized model evidence."""

    ppe_id: int
    name: str
    detection_class: str | None
    state: PpeRequirementSafetyState

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if self.ppe_id <= 0:
            raise ValueError("ppe_id deve ser maior que zero")
        if not normalized_name:
            raise ValueError("name do requisito não pode ser vazio")
        if not isinstance(self.state, PpeRequirementSafetyState):
            raise ValueError("state deve ser um PpeRequirementSafetyState")

        detection_class = self.detection_class
        if detection_class is not None:
            detection_class = detection_class.strip().casefold()
            if not detection_class:
                raise ValueError("detection_class não pode ser vazia")
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "detection_class", detection_class)


@dataclass(frozen=True, slots=True)
class PpeSafetyAssessment:
    """Immutable, operation-bound result of the PPE safety gate."""

    operation_id: int
    operation_active: bool
    status: PpeSafetyStatus
    requirements: tuple[PpeRequirementAssessment, ...]
    sample_count: int
    window_size: int

    def __post_init__(self) -> None:
        if self.operation_id <= 0:
            raise ValueError("operation_id deve ser maior que zero")
        if not isinstance(self.operation_active, bool):
            raise ValueError("operation_active deve ser booleano")
        if not isinstance(self.status, PpeSafetyStatus):
            raise ValueError("status deve ser um PpeSafetyStatus")
        if self.window_size < 1 or not 1 <= self.sample_count <= self.window_size:
            raise ValueError("a amostragem deve estar dentro da janela")
        if any(
            not isinstance(item, PpeRequirementAssessment)
            for item in self.requirements
        ):
            raise ValueError(
                "requirements deve conter somente PpeRequirementAssessment"
            )
        ppe_ids = {item.ppe_id for item in self.requirements}
        if len(ppe_ids) != len(self.requirements):
            raise ValueError("requirements não pode repetir ppe_id")
        if self.status is not self._expected_status():
            raise ValueError("status não corresponde às avaliações dos requisitos")

    @property
    def can_start_operation(self) -> bool:
        """Return whether this exact assessment passes the PPE release gate."""

        return self.status is PpeSafetyStatus.COMPLIANT

    @property
    def absent_requirement_names(self) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.requirements
            if item.state is PpeRequirementSafetyState.ABSENT
        )

    @property
    def unmapped_requirement_names(self) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.requirements
            if item.state is PpeRequirementSafetyState.UNMAPPED
        )

    def assessment_for(self, ppe_id: int) -> PpeRequirementAssessment | None:
        return next(
            (item for item in self.requirements if item.ppe_id == ppe_id),
            None,
        )

    def _expected_status(self) -> PpeSafetyStatus:
        if not self.operation_active or not self.requirements:
            return PpeSafetyStatus.BLOCKED
        states = {item.state for item in self.requirements}
        if states & {
            PpeRequirementSafetyState.ABSENT,
            PpeRequirementSafetyState.UNMAPPED,
        }:
            return PpeSafetyStatus.BLOCKED
        if states == {PpeRequirementSafetyState.CONFIRMED}:
            return PpeSafetyStatus.COMPLIANT
        return PpeSafetyStatus.PENDING


class PpeSafetyEngine:
    """Compare operation requirements with temporal evidence deterministically."""

    def evaluate(
        self,
        operation: Operation,
        model_classes: Iterable[str],
        snapshot: PpeStabilitySnapshot,
    ) -> PpeSafetyAssessment:
        """Create a fail-closed assessment bound to the selected operation."""

        normalized_model_classes = frozenset(
            normalized
            for item in model_classes
            if (normalized := item.strip().casefold())
        )
        requirements = tuple(
            self._evaluate_requirement(
                requirement,
                normalized_model_classes,
                snapshot,
            )
            for requirement in operation.required_ppe
        )
        status = self._status_for(operation, requirements)
        return PpeSafetyAssessment(
            operation_id=operation.operation_id,
            operation_active=operation.active,
            status=status,
            requirements=requirements,
            sample_count=snapshot.sample_count,
            window_size=snapshot.window_size,
        )

    @staticmethod
    def _evaluate_requirement(
        requirement: PpeRequirement,
        model_classes: frozenset[str],
        snapshot: PpeStabilitySnapshot,
    ) -> PpeRequirementAssessment:
        detection_class = requirement.detection_class
        if detection_class is None or detection_class not in model_classes:
            state = PpeRequirementSafetyState.UNMAPPED
        else:
            decision = snapshot.decision_for(detection_class)
            states = {
                PpeStabilityState.COLLECTING: PpeRequirementSafetyState.COLLECTING,
                PpeStabilityState.CONFIRMED_PRESENT: (
                    PpeRequirementSafetyState.CONFIRMED
                ),
                PpeStabilityState.CONFIRMED_ABSENT: PpeRequirementSafetyState.ABSENT,
                PpeStabilityState.UNSTABLE: PpeRequirementSafetyState.UNSTABLE,
            }
            state = (
                states[decision.state]
                if decision is not None
                else PpeRequirementSafetyState.COLLECTING
            )
        return PpeRequirementAssessment(
            ppe_id=requirement.ppe_id,
            name=requirement.name,
            detection_class=detection_class,
            state=state,
        )

    @staticmethod
    def _status_for(
        operation: Operation,
        requirements: tuple[PpeRequirementAssessment, ...],
    ) -> PpeSafetyStatus:
        if not operation.active or not requirements:
            return PpeSafetyStatus.BLOCKED
        states = {item.state for item in requirements}
        if states & {
            PpeRequirementSafetyState.ABSENT,
            PpeRequirementSafetyState.UNMAPPED,
        }:
            return PpeSafetyStatus.BLOCKED
        if states == {PpeRequirementSafetyState.CONFIRMED}:
            return PpeSafetyStatus.COMPLIANT
        return PpeSafetyStatus.PENDING
