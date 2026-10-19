"""Evidence-only multi-camera PPE fusion: UNKNOWN never votes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.operation import Operation, PpeRequirement
from app.engine import (
    PpeMultiCameraFusion,
    PpeRequirementAssessment,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyEngine,
    PpeSafetyStatus,
)
from app.engine.ppe_safety import PpeEvidenceState

_T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
State = PpeRequirementSafetyState


def _operation() -> Operation:
    return Operation(
        41,
        "Fresagem",
        required_ppe=(
            PpeRequirement(1, "Capacete", "capacete"),
            PpeRequirement(2, "Óculos", "oculos"),
        ),
    )


def _assessment(camera_id: int, helmet: State, glasses: State = State.UNSTABLE):
    requirements = (
        PpeRequirementAssessment(1, "Capacete", "capacete", helmet),
        PpeRequirementAssessment(2, "Óculos", "oculos", glasses),
    )
    return PpeSafetyAssessment(
        operation_id=41,
        operation_active=True,
        status=PpeSafetyEngine.status_for(_operation(), requirements),
        requirements=requirements,
        sample_count=5,
        window_size=8,
        camera_id=camera_id,
    )


def _fusion(conflict_seconds: float = 2.0) -> PpeMultiCameraFusion:
    return PpeMultiCameraFusion(
        maximum_evidence_age_seconds=2.0,
        conflict_resolution_seconds=conflict_seconds,
    )


def _helmet(fusion: PpeMultiCameraFusion, now: datetime = _T0):
    result = fusion.consolidate(_operation(), now)
    assert result is not None
    decision = result.decision_for(1)
    assert decision is not None
    return result, decision


def test_scenario_a_single_present_camera_wins_over_four_unknown() -> None:
    fusion = _fusion()
    for camera_id in (1, 2, 3, 4):
        fusion.observe(camera_id, _assessment(camera_id, State.UNSTABLE), _T0)
    fusion.observe(5, _assessment(5, State.CONFIRMED), _T0)

    result, decision = _helmet(fusion)

    assert decision.evidence is PpeEvidenceState.PRESENT
    assert decision.state is State.CONFIRMED
    assert decision.present_camera_ids == (5,)
    assert decision.absent_camera_ids == ()
    assert decision.inconclusive_camera_ids == (1, 2, 3, 4)
    assert decision.decisive_camera_id == 5
    assert result.assessment.camera_id is None
    assert result.assessment.absent_requirement_names == ()


def test_scenario_b_single_confirmed_absence_is_consolidated_absent() -> None:
    fusion = _fusion()
    for camera_id in (1, 2, 4, 5):
        fusion.observe(camera_id, _assessment(camera_id, State.COLLECTING), _T0)
    fusion.observe(3, _assessment(3, State.ABSENT), _T0)

    result, decision = _helmet(fusion)

    assert decision.evidence is PpeEvidenceState.ABSENT
    assert decision.absent_camera_ids == (3,)
    assert decision.decisive_camera_id == 3
    assert result.assessment.status is PpeSafetyStatus.BLOCKED
    assert result.assessment.absent_requirement_names == ("Capacete",)


@pytest.mark.parametrize("unknown_state", [State.COLLECTING, State.UNSTABLE])
def test_scenario_c_all_unknown_stays_unknown_never_absent(unknown_state) -> None:
    fusion = _fusion()
    for camera_id in range(1, 6):
        fusion.observe(camera_id, _assessment(camera_id, unknown_state), _T0)

    result, decision = _helmet(fusion)

    assert decision.evidence is PpeEvidenceState.UNKNOWN
    assert decision.state is unknown_state
    assert decision.decisive_camera_id is None
    assert result.assessment.status is PpeSafetyStatus.PENDING
    assert result.assessment.absent_requirement_names == ()


def test_scenario_d_simultaneous_conflict_is_unknown() -> None:
    fusion = _fusion(conflict_seconds=2.0)
    fusion.observe(1, _assessment(1, State.CONFIRMED), _T0)
    fusion.observe(2, _assessment(2, State.ABSENT), _T0 + timedelta(seconds=1))

    result, decision = _helmet(fusion, _T0 + timedelta(seconds=1))

    assert decision.conflict
    assert decision.evidence is PpeEvidenceState.UNKNOWN
    assert decision.state is State.UNSTABLE
    assert decision.present_camera_ids == (1,)
    assert decision.absent_camera_ids == (2,)
    assert result.assessment.absent_requirement_names == ()


@pytest.mark.parametrize(
    ("newer", "expected"),
    [(State.ABSENT, PpeEvidenceState.ABSENT), (State.CONFIRMED, PpeEvidenceState.PRESENT)],
)
def test_scenario_d_newer_evidence_wins_only_with_enough_advantage(newer, expected) -> None:
    older = State.CONFIRMED if newer is State.ABSENT else State.ABSENT
    fusion = _fusion(conflict_seconds=1.0)
    fusion.observe(1, _assessment(1, older), _T0)
    # The older camera keeps reporting the same state; its onset does not move.
    fusion.observe(1, _assessment(1, older), _T0 + timedelta(seconds=1.5))
    fusion.observe(2, _assessment(2, newer), _T0 + timedelta(seconds=1.5))

    _, decision = _helmet(fusion, _T0 + timedelta(seconds=1.5))

    assert not decision.conflict
    assert decision.evidence is expected
    assert decision.decisive_camera_id == 2


def test_stale_camera_evidence_is_ignored() -> None:
    fusion = _fusion()
    fusion.observe(1, _assessment(1, State.ABSENT), _T0)
    fusion.observe(2, _assessment(2, State.UNSTABLE), _T0 + timedelta(seconds=3))

    result, decision = _helmet(fusion, _T0 + timedelta(seconds=3))

    assert result.camera_ids == (2,)
    assert decision.evidence is PpeEvidenceState.UNKNOWN
    assert decision.observing_camera_ids == (2,)


def test_removed_camera_no_longer_contributes_and_empty_fusion_is_none() -> None:
    fusion = _fusion()
    fusion.observe(1, _assessment(1, State.CONFIRMED), _T0)
    fusion.remove_camera(1)

    assert fusion.consolidate(_operation(), _T0) is None


def test_requirements_are_fused_independently() -> None:
    fusion = _fusion()
    fusion.observe(1, _assessment(1, State.CONFIRMED, State.UNSTABLE), _T0)
    fusion.observe(2, _assessment(2, State.UNSTABLE, State.CONFIRMED), _T0)

    result = fusion.consolidate(_operation(), _T0)

    assert result is not None
    assert [item.state for item in result.assessment.requirements] == [
        State.CONFIRMED,
        State.CONFIRMED,
    ]
    assert result.assessment.status is PpeSafetyStatus.COMPLIANT


def test_unmapped_requirement_stays_unmapped() -> None:
    fusion = _fusion()
    fusion.observe(1, _assessment(1, State.CONFIRMED, State.UNMAPPED), _T0)

    result = fusion.consolidate(_operation(), _T0)

    assert result is not None
    assert result.assessment.unmapped_requirement_names == ("Óculos",)
    assert result.assessment.status is PpeSafetyStatus.BLOCKED


def test_single_camera_matches_its_own_assessment() -> None:
    fusion = _fusion()
    camera = _assessment(1, State.CONFIRMED, State.COLLECTING)
    fusion.observe(1, camera, _T0)

    result = fusion.consolidate(_operation(), _T0)

    assert result is not None
    assert [item.state for item in result.assessment.requirements] == [
        item.state for item in camera.requirements
    ]
    assert result.assessment.status is camera.status


def test_rejects_assessment_from_another_camera_and_naive_timestamps() -> None:
    fusion = _fusion()
    with pytest.raises(ValueError):
        fusion.observe(2, _assessment(1, State.CONFIRMED), _T0)
    with pytest.raises(ValueError):
        fusion.observe(1, _assessment(1, State.CONFIRMED), datetime(2026, 10, 19))
    with pytest.raises(ValueError):
        PpeMultiCameraFusion(maximum_evidence_age_seconds=0, conflict_resolution_seconds=1)
