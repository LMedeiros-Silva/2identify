from app.vision.frame_scheduler import LatestFrameScheduler


def test_latest_frame_wins_and_round_robin_prevents_fast_camera_monopoly() -> None:
    scheduler: LatestFrameScheduler[str] = LatestFrameScheduler()
    scheduler.submit(1, "old-A")
    scheduler.submit(1, "new-A")
    scheduler.submit(2, "B")
    assert scheduler.take() == "new-A"
    scheduler.submit(1, "newer-A")
    assert scheduler.take() == "B"
    assert scheduler.take() == "newer-A"
    assert scheduler.metrics() == {1: 1}
    scheduler.stop()
    scheduler.submit(1, "late")
    assert scheduler.take() is None
