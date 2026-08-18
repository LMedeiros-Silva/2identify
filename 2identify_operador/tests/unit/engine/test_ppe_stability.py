import pytest

from app.engine import PpeStabilityEngine, PpeStabilityState


def _engine(
    *,
    window_size: int = 4,
    minimum_samples: int = 4,
) -> PpeStabilityEngine:
    engine = PpeStabilityEngine(
        window_size=window_size,
        minimum_samples=minimum_samples,
        present_ratio=0.75,
        absent_ratio=0.25,
    )
    engine.reset(("capacete",))
    return engine


def test_engine_collects_minimum_samples_before_confirming() -> None:
    engine = _engine()

    for _ in range(3):
        snapshot = engine.observe(("capacete",))

    decision = snapshot.decision_for("CAPACETE")
    assert decision is not None
    assert decision.state is PpeStabilityState.COLLECTING
    assert decision.observed_frames == 3
    assert decision.presence_ratio == 1.0
    assert not snapshot.all_confirmed_present

    snapshot = engine.observe(("capacete",))

    assert snapshot.decision_for("capacete").state is (
        PpeStabilityState.CONFIRMED_PRESENT
    )
    assert snapshot.all_confirmed_present


def test_engine_rejects_an_isolated_positive_as_absent() -> None:
    engine = _engine()

    engine.observe(("capacete",))
    engine.observe(())
    engine.observe(())
    snapshot = engine.observe(())

    decision = snapshot.decision_for("capacete")
    assert decision is not None
    assert decision.state is PpeStabilityState.CONFIRMED_ABSENT
    assert decision.presence_ratio == 0.25


def test_engine_marks_ambiguous_window_as_unstable() -> None:
    engine = _engine()

    engine.observe(("capacete",))
    engine.observe(())
    engine.observe(("capacete",))
    snapshot = engine.observe(())

    decision = snapshot.decision_for("capacete")
    assert decision is not None
    assert decision.state is PpeStabilityState.UNSTABLE
    assert decision.presence_ratio == 0.5


def test_engine_ages_old_evidence_out_of_the_rolling_window() -> None:
    engine = _engine()

    for _ in range(4):
        snapshot = engine.observe(("capacete",))
    assert snapshot.all_confirmed_present

    snapshot = engine.observe(())
    assert snapshot.decision_for("capacete").state is (
        PpeStabilityState.CONFIRMED_PRESENT
    )
    snapshot = engine.observe(())
    assert snapshot.decision_for("capacete").state is PpeStabilityState.UNSTABLE
    engine.observe(())
    snapshot = engine.observe(())
    assert snapshot.decision_for("capacete").state is (
        PpeStabilityState.CONFIRMED_ABSENT
    )


def test_engine_reset_discards_previous_operation_evidence() -> None:
    engine = _engine()
    for _ in range(4):
        engine.observe(("capacete",))

    engine.reset(("bota",))
    snapshot = engine.observe(("bota",))

    assert snapshot.sample_count == 1
    assert snapshot.decision_for("capacete") is None
    assert snapshot.decision_for("bota").state is PpeStabilityState.COLLECTING


@pytest.mark.parametrize(
    "arguments",
    [
        {"window_size": 0, "minimum_samples": 1},
        {"window_size": 4, "minimum_samples": 5},
    ],
)
def test_engine_rejects_invalid_window_configuration(arguments) -> None:
    with pytest.raises(ValueError):
        PpeStabilityEngine(
            **arguments,
            present_ratio=0.75,
            absent_ratio=0.25,
        )


def test_engine_rejects_overlapping_decision_thresholds() -> None:
    with pytest.raises(ValueError):
        PpeStabilityEngine(
            window_size=4,
            minimum_samples=4,
            present_ratio=0.50,
            absent_ratio=0.50,
        )
