"""Evidence-only fusion of independent per-camera PPE assessments.

Each camera keeps its own temporal stabilization. This engine only combines the
conclusions: a camera without conclusive evidence (UNKNOWN) never votes against
a requirement, and there is no majority vote. A conflict between PRESENT and
ABSENT is resolved only when one side changed state sufficiently later than the
other; otherwise the consolidated result stays UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite

from app.domain.operation import Operation
from app.engine.ppe_safety import (
    PpeEvidenceState,
    PpeRequirementAssessment,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyEngine,
)


@dataclass(frozen=True, slots=True)
class PpeFusionDecision:
    """Consolidated evidence for one required PPE item and its provenance."""

    ppe_id: int
    name: str
    evidence: PpeEvidenceState
    state: PpeRequirementSafetyState
    observing_camera_ids: tuple[int, ...]
    present_camera_ids: tuple[int, ...]
    absent_camera_ids: tuple[int, ...]
    conflict: bool = False
    decisive_camera_id: int | None = None

    @property
    def inconclusive_camera_ids(self) -> tuple[int, ...]:
        conclusive = {*self.present_camera_ids, *self.absent_camera_ids}
        return tuple(item for item in self.observing_camera_ids if item not in conclusive)


@dataclass(frozen=True, slots=True)
class PpeFusionResult:
    """Fused operation assessment plus the per-requirement evidence trail."""

    assessment: PpeSafetyAssessment
    decisions: tuple[PpeFusionDecision, ...]
    camera_ids: tuple[int, ...]

    def decision_for(self, ppe_id: int) -> PpeFusionDecision | None:
        return next((item for item in self.decisions if item.ppe_id == ppe_id), None)


@dataclass(slots=True)
class _CameraRequirementEvidence:
    state: PpeRequirementSafetyState
    since: datetime


@dataclass(slots=True)
class _CameraEvidence:
    assessment: PpeSafetyAssessment
    observed_at: datetime
    requirements: dict[int, _CameraRequirementEvidence] = field(default_factory=dict)


class PpeMultiCameraFusion:
    """Combine fresh per-camera PPE conclusions without counting UNKNOWN as a vote."""

    def __init__(
        self,
        *,
        maximum_evidence_age_seconds: float,
        conflict_resolution_seconds: float,
    ) -> None:
        if not isfinite(maximum_evidence_age_seconds) or maximum_evidence_age_seconds <= 0:
            raise ValueError("maximum_evidence_age_seconds deve ser positivo")
        if not isfinite(conflict_resolution_seconds) or conflict_resolution_seconds <= 0:
            raise ValueError("conflict_resolution_seconds deve ser positivo")
        self._maximum_age = timedelta(seconds=maximum_evidence_age_seconds)
        self._conflict_resolution = timedelta(seconds=conflict_resolution_seconds)
        self._cameras: dict[int, _CameraEvidence] = {}

    @property
    def camera_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._cameras))

    def reset(self) -> None:
        self._cameras.clear()

    def remove_camera(self, camera_id: int) -> None:
        """Forget a camera whose evidence is no longer valid (offline, stale, failed)."""

        self._cameras.pop(camera_id, None)

    def observe(
        self,
        camera_id: int,
        assessment: PpeSafetyAssessment,
        observed_at: datetime,
    ) -> None:
        """Record the latest stabilized assessment produced by one camera."""

        if camera_id <= 0:
            raise ValueError("camera_id deve ser positivo")
        if not isinstance(assessment, PpeSafetyAssessment):
            raise ValueError("assessment deve ser um PpeSafetyAssessment")
        if assessment.camera_id is not None and assessment.camera_id != camera_id:
            raise ValueError("assessment pertence a outra câmera")
        observed_at = _as_utc(observed_at)
        previous = self._cameras.get(camera_id)
        if previous is not None and previous.assessment.operation_id != assessment.operation_id:
            previous = None
        requirements: dict[int, _CameraRequirementEvidence] = {}
        for item in assessment.requirements:
            earlier = previous.requirements.get(item.ppe_id) if previous is not None else None
            since = (
                earlier.since
                if earlier is not None and earlier.state is item.state
                else observed_at
            )
            requirements[item.ppe_id] = _CameraRequirementEvidence(item.state, since)
        self._cameras[camera_id] = _CameraEvidence(assessment, observed_at, requirements)

    def consolidate(self, operation: Operation, now: datetime) -> PpeFusionResult | None:
        """Return the fused assessment, or None when no camera has fresh evidence."""

        now = _as_utc(now)
        fresh = {
            camera_id: evidence
            for camera_id, evidence in sorted(self._cameras.items())
            if evidence.assessment.operation_id == operation.operation_id
            and now - evidence.observed_at <= self._maximum_age
        }
        if not fresh:
            return None
        decisions = tuple(
            self._decide(requirement.ppe_id, requirement.name, fresh)
            for requirement in operation.required_ppe
        )
        requirements = tuple(
            PpeRequirementAssessment(
                ppe_id=requirement.ppe_id,
                name=requirement.name,
                detection_class=requirement.detection_class,
                state=decision.state,
            )
            for requirement, decision in zip(operation.required_ppe, decisions, strict=True)
        )
        window_size = max(item.assessment.window_size for item in fresh.values())
        sample_count = max(item.assessment.sample_count for item in fresh.values())
        return PpeFusionResult(
            assessment=PpeSafetyAssessment(
                operation_id=operation.operation_id,
                operation_active=operation.active,
                status=PpeSafetyEngine.status_for(operation, requirements),
                requirements=requirements,
                sample_count=sample_count,
                window_size=window_size,
            ),
            decisions=decisions,
            camera_ids=tuple(fresh),
        )

    def _decide(
        self,
        ppe_id: int,
        name: str,
        cameras: dict[int, _CameraEvidence],
    ) -> PpeFusionDecision:
        observing: list[int] = []
        present: list[tuple[int, datetime]] = []
        absent: list[tuple[int, datetime]] = []
        states: set[PpeRequirementSafetyState] = set()
        for camera_id, evidence in cameras.items():
            requirement = evidence.requirements.get(ppe_id)
            if requirement is None:
                continue
            observing.append(camera_id)
            states.add(requirement.state)
            if requirement.state is PpeRequirementSafetyState.CONFIRMED:
                present.append((camera_id, requirement.since))
            elif requirement.state is PpeRequirementSafetyState.ABSENT:
                absent.append((camera_id, requirement.since))

        present_ids = tuple(camera_id for camera_id, _ in present)
        absent_ids = tuple(camera_id for camera_id, _ in absent)
        if present and not absent:
            evidence = PpeEvidenceState.PRESENT
            decisive = _latest(present)
            conflict = False
        elif absent and not present:
            evidence = PpeEvidenceState.ABSENT
            decisive = _latest(absent)
            conflict = False
        elif present and absent:
            latest_present = max(since for _, since in present)
            latest_absent = max(since for _, since in absent)
            if latest_absent - latest_present >= self._conflict_resolution:
                evidence, decisive, conflict = PpeEvidenceState.ABSENT, _latest(absent), False
            elif latest_present - latest_absent >= self._conflict_resolution:
                evidence, decisive, conflict = PpeEvidenceState.PRESENT, _latest(present), False
            else:
                evidence, decisive, conflict = PpeEvidenceState.UNKNOWN, None, True
        else:
            evidence, decisive, conflict = PpeEvidenceState.UNKNOWN, None, False

        return PpeFusionDecision(
            ppe_id=ppe_id,
            name=name,
            evidence=evidence,
            state=_state_for(evidence, states, conflict),
            observing_camera_ids=tuple(observing),
            present_camera_ids=present_ids,
            absent_camera_ids=absent_ids,
            conflict=conflict,
            decisive_camera_id=decisive,
        )


def _latest(items: list[tuple[int, datetime]]) -> int:
    return max(items, key=lambda item: (item[1], -item[0]))[0]


def _state_for(
    evidence: PpeEvidenceState,
    states: set[PpeRequirementSafetyState],
    conflict: bool,
) -> PpeRequirementSafetyState:
    if evidence is PpeEvidenceState.PRESENT:
        return PpeRequirementSafetyState.CONFIRMED
    if evidence is PpeEvidenceState.ABSENT:
        return PpeRequirementSafetyState.ABSENT
    if PpeRequirementSafetyState.UNMAPPED in states:
        return PpeRequirementSafetyState.UNMAPPED
    if conflict or PpeRequirementSafetyState.UNSTABLE in states:
        return PpeRequirementSafetyState.UNSTABLE
    return PpeRequirementSafetyState.COLLECTING


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp deve possuir fuso horário")
    return value.astimezone(UTC)
