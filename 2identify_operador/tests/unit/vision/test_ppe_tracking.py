import pytest

from app.vision.ppe import (
    DetectionBox,
    PpeDetection,
    PpeDetectionBatch,
    PpeDetectionTracker,
)


def _detection(class_id: int, class_name: str, x: float) -> PpeDetection:
    return PpeDetection(
        class_id,
        class_name,
        0.9,
        DetectionBox(x, 10, x + 40, 60),
    )


def _batch(*detections: PpeDetection) -> PpeDetectionBatch:
    return PpeDetectionBatch(tuple(detections), 320, 240, 8.5)


def _tracker(
    *,
    maximum_missed_batches: int = 2,
    minimum_confirmation_hits: int = 2,
) -> PpeDetectionTracker:
    return PpeDetectionTracker(
        iou_threshold=0.3,
        maximum_missed_batches=maximum_missed_batches,
        minimum_confirmation_hits=minimum_confirmation_hits,
    )


def test_tracker_preserves_ids_across_order_and_position_changes() -> None:
    tracker = _tracker()

    first = tracker.update(
        _batch(
            _detection(0, "capacete", 10),
            _detection(1, "bota", 180),
        )
    )
    second = tracker.update(
        _batch(
            _detection(1, "bota", 184),
            _detection(0, "capacete", 14),
        )
    )

    assert [(item.track_id, item.detection.class_name) for item in first.tracks] == [
        (1, "capacete"),
        (2, "bota"),
    ]
    assert [(item.track_id, item.detection.class_name) for item in second.tracks] == [
        (1, "capacete"),
        (2, "bota"),
    ]
    assert all(item.confirmed for item in second.tracks)


def test_tracker_never_associates_different_classes() -> None:
    tracker = _tracker(minimum_confirmation_hits=1)
    tracker.update(_batch(_detection(0, "capacete", 10)))

    result = tracker.update(_batch(_detection(1, "bota", 10)))

    assert [(item.track_id, item.detection.class_name) for item in result.tracks] == [
        (1, "capacete"),
        (2, "bota"),
    ]
    assert not result.tracks[0].is_visible
    assert result.tracks[1].is_visible


def test_tracker_recovers_identity_after_short_detection_gap() -> None:
    tracker = _tracker(maximum_missed_batches=2, minimum_confirmation_hits=1)
    tracker.update(_batch(_detection(0, "capacete", 10)))

    first_gap = tracker.update(_batch())
    second_gap = tracker.update(_batch())
    recovered = tracker.update(_batch(_detection(0, "capacete", 12)))

    assert first_gap.tracks[0].missed_batches == 1
    assert second_gap.tracks[0].missed_batches == 2
    assert recovered.visible_tracks[0].track_id == 1
    assert recovered.visible_tracks[0].hit_count == 2


def test_tracker_expires_stale_track_and_reset_scopes_ids() -> None:
    tracker = _tracker(maximum_missed_batches=1, minimum_confirmation_hits=1)
    tracker.update(_batch(_detection(0, "capacete", 10)))
    tracker.update(_batch())

    expired = tracker.update(_batch())
    replacement = tracker.update(_batch(_detection(0, "capacete", 10)))

    assert expired.tracks == ()
    assert replacement.visible_tracks[0].track_id == 2
    tracker.reset()
    restarted = tracker.update(_batch(_detection(0, "capacete", 10)))
    assert restarted.sequence_number == 1
    assert restarted.visible_tracks[0].track_id == 1


@pytest.mark.parametrize(
    ("iou_threshold", "maximum_missed_batches", "minimum_confirmation_hits"),
    [
        (0.0, 1, 1),
        (1.1, 1, 1),
        (0.3, -1, 1),
        (0.3, 1, 0),
    ],
)
def test_tracker_rejects_invalid_configuration(
    iou_threshold: float,
    maximum_missed_batches: int,
    minimum_confirmation_hits: int,
) -> None:
    with pytest.raises(ValueError):
        PpeDetectionTracker(
            iou_threshold=iou_threshold,
            maximum_missed_batches=maximum_missed_batches,
            minimum_confirmation_hits=minimum_confirmation_hits,
        )
