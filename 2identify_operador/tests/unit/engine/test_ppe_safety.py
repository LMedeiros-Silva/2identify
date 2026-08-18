import pytest

from app.domain.operation import Operation, PpeRequirement
from app.engine import (
    PpeRequirementAssessment,
    PpeRequirementSafetyState,
    PpeSafetyAssessment,
    PpeSafetyEngine,
    PpeSafetyStatus,
    PpeStabilityDecision,
    PpeStabilitySnapshot,
    PpeStabilityState,
)


def _operation(*, active: bool = True) -> Operation:
    return Operation(
        41,
        "Inspeção de segurança",
        required_ppe=(
            PpeRequirement(1, "Capacete", "capacete"),
            PpeRequirement(2, "Botas", "bota"),
        ),
        active=active,
    )


def _snapshot(
    helmet: PpeStabilityState,
    boots: PpeStabilityState,
) -> PpeStabilitySnapshot:
    ratios = {
        PpeStabilityState.COLLECTING: (3, 5, 0.6),
        PpeStabilityState.CONFIRMED_PRESENT: (4, 5, 0.8),
        PpeStabilityState.CONFIRMED_ABSENT: (1, 5, 0.2),
        PpeStabilityState.UNSTABLE: (3, 5, 0.6),
    }
    helmet_observed, helmet_samples, helmet_ratio = ratios[helmet]
    boots_observed, boots_samples, boots_ratio = ratios[boots]
    assert helmet_samples == boots_samples
    sample_count = helmet_samples
    return PpeStabilitySnapshot(
        decisions=(
            PpeStabilityDecision(
                "capacete",
                helmet,
                helmet_observed,
                sample_count,
                helmet_ratio,
            ),
            PpeStabilityDecision(
                "bota",
                boots,
                boots_observed,
                sample_count,
                boots_ratio,
            ),
        ),
        sample_count=sample_count,
        window_size=8,
    )


def test_safety_engine_releases_only_when_every_requirement_is_confirmed() -> None:
    assessment = PpeSafetyEngine().evaluate(
        _operation(),
        ("BOTA", "CAPACETE"),
        _snapshot(
            PpeStabilityState.CONFIRMED_PRESENT,
            PpeStabilityState.CONFIRMED_PRESENT,
        ),
    )

    assert assessment.status is PpeSafetyStatus.COMPLIANT
    assert assessment.can_start_operation
    assert {item.state for item in assessment.requirements} == {
        PpeRequirementSafetyState.CONFIRMED
    }


def test_safety_engine_blocks_and_identifies_absent_requirements() -> None:
    assessment = PpeSafetyEngine().evaluate(
        _operation(),
        ("bota", "capacete"),
        _snapshot(
            PpeStabilityState.CONFIRMED_PRESENT,
            PpeStabilityState.CONFIRMED_ABSENT,
        ),
    )

    assert assessment.status is PpeSafetyStatus.BLOCKED
    assert not assessment.can_start_operation
    assert assessment.absent_requirement_names == ("Botas",)


def test_safety_engine_blocks_requirements_unknown_to_the_model() -> None:
    assessment = PpeSafetyEngine().evaluate(
        _operation(),
        ("capacete",),
        _snapshot(
            PpeStabilityState.CONFIRMED_PRESENT,
            PpeStabilityState.CONFIRMED_PRESENT,
        ),
    )

    assert assessment.status is PpeSafetyStatus.BLOCKED
    assert assessment.unmapped_requirement_names == ("Botas",)
    assert assessment.assessment_for(2).state is PpeRequirementSafetyState.UNMAPPED


@pytest.mark.parametrize(
    "unsettled_state",
    [PpeStabilityState.COLLECTING, PpeStabilityState.UNSTABLE],
)
def test_safety_engine_keeps_unsettled_evidence_pending(
    unsettled_state: PpeStabilityState,
) -> None:
    assessment = PpeSafetyEngine().evaluate(
        _operation(),
        ("bota", "capacete"),
        _snapshot(PpeStabilityState.CONFIRMED_PRESENT, unsettled_state),
    )

    assert assessment.status is PpeSafetyStatus.PENDING
    assert not assessment.can_start_operation


def test_safety_engine_blocks_empty_or_inactive_operations() -> None:
    empty = Operation(42, "Operação sem requisitos")
    empty_snapshot = PpeStabilitySnapshot((), sample_count=1, window_size=8)

    assert PpeSafetyEngine().evaluate(empty, (), empty_snapshot).status is (
        PpeSafetyStatus.BLOCKED
    )
    inactive = PpeSafetyEngine().evaluate(
        _operation(active=False),
        ("bota", "capacete"),
        _snapshot(
            PpeStabilityState.CONFIRMED_PRESENT,
            PpeStabilityState.CONFIRMED_PRESENT,
        ),
    )
    assert inactive.status is PpeSafetyStatus.BLOCKED


def test_safety_assessment_rejects_an_inconsistent_release_status() -> None:
    with pytest.raises(ValueError, match="não corresponde"):
        PpeSafetyAssessment(
            operation_id=41,
            operation_active=True,
            status=PpeSafetyStatus.COMPLIANT,
            requirements=(
                PpeRequirementAssessment(
                    1,
                    "Capacete",
                    "capacete",
                    PpeRequirementSafetyState.ABSENT,
                ),
            ),
            sample_count=5,
            window_size=8,
        )
