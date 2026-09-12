"""Pure aggregation contracts; lifecycle/WebSocket integration is tested separately."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.realtime import InMemoryRealtimeEventBroker
from app.schemas.safety_state import SafetyConditionSnapshot
from app.services import SafetyStateAggregator


class RecordingBroker(InMemoryRealtimeEventBroker):
    def __init__(self):
        super().__init__()
        self.published = []

    async def publish(self, event):
        self.published.append(event)
        return await super().publish(event)


def _conditions(*levels):
    return tuple(
        SafetyConditionSnapshot(
            condition_id=f"alert:{index}",
            reason="PPE_MISSING",
            level=level,
            first_observed_at=datetime.now(UTC),
        )
        for index, level in enumerate(levels)
    )


@pytest.mark.parametrize(
    ("levels", "state"),
    [
        ((), "GREEN"),
        (("medium",), "YELLOW"),
        (("critical",), "RED"),
        (("medium", "critical"), "RED"),
        (("medium", "medium"), "YELLOW"),
    ],
)
def test_aggregator_uses_highest_active_severity(levels, state):
    async def scenario():
        aggregator = SafetyStateAggregator(RecordingBroker())
        result = await aggregator.refresh(lambda: _conditions(*levels))
        assert result.message.state == state
        assert result.message.active_conditions == len(levels)

    asyncio.run(scenario())


def test_aggregator_publishes_changes_and_suppresses_duplicate_state():
    async def scenario():
        broker = RecordingBroker()
        aggregator = SafetyStateAggregator(broker)
        assert await aggregator.current() is None
        for levels in [("medium",), ("medium", "critical"), ("medium",), ()]:
            conditions = _conditions(*levels)
            assert (await aggregator.refresh(lambda current=conditions: current)).published
            assert not (await aggregator.refresh(lambda current=conditions: current)).published
        assert [event.state for event in broker.published] == [
            "YELLOW",
            "RED",
            "YELLOW",
            "GREEN",
        ]

    asyncio.run(scenario())


def test_failed_database_read_invalidates_previously_green_cache():
    def unavailable():
        raise RuntimeError("database unavailable")

    async def scenario():
        aggregator = SafetyStateAggregator(RecordingBroker())
        await aggregator.refresh(lambda: ())
        with pytest.raises(RuntimeError, match="database unavailable"):
            await aggregator.refresh(unavailable)
        assert await aggregator.current() is None
        assert await aggregator.send_current(uuid4()) is False

    asyncio.run(scenario())
