import pytest

from app.vision.ppe import DetectionBox, PpeDetection, PpeDetectionBatch


def test_detection_batch_exposes_normalized_observed_classes() -> None:
    batch = PpeDetectionBatch(
        detections=(
            PpeDetection(1, " Capacete ", 0.91, DetectionBox(10, 20, 80, 100)),
            PpeDetection(4, "Mangote", 0.84, DetectionBox(90, 20, 140, 110)),
        ),
        frame_width=640,
        frame_height=480,
        inference_milliseconds=18.5,
    )

    assert batch.observed_classes == frozenset({"capacete", "mangote"})


def test_detection_contracts_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="invertidos"):
        DetectionBox(20, 10, 5, 30)
    with pytest.raises(ValueError, match="confidence"):
        PpeDetection(1, "capacete", 1.1, DetectionBox(0, 0, 1, 1))
    with pytest.raises(ValueError, match="dimensões"):
        PpeDetectionBatch((), 0, 480, 10)
