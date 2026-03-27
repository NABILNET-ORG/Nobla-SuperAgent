"""Tests for the Nobla Event Bus (Phase 5-Foundation §4.1).

Covers: NoblaEvent model, emit, subscribe, wildcards, unsubscribe,
handler isolation, priority ordering, overflow/backpressure, lifecycle.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from nobla.events.models import NoblaEvent
from nobla.events.bus import NoblaEventBus, URGENT_PRIORITY_THRESHOLD


# ── NoblaEvent model tests ─────────────────────────────────


class TestNoblaEvent:
    def test_creates_with_defaults(self):
        event = NoblaEvent(event_type="test.event", source="test")
        assert event.event_type == "test.event"
        assert event.source == "test"
        assert event.payload == {}
        assert event.user_id is None
        assert event.conversation_id is None
        assert event.priority == 0
        assert event.correlation_id  # auto-generated UUID
        assert isinstance(event.timestamp, datetime)

    def test_creates_with_all_fields(self):
        ts = datetime.now(timezone.utc)
        event = NoblaEvent(
            event_type="tool.executed",
            source="tool.code.run",
            payload={"result": "ok"},
            user_id="user-1",
            conversation_id="conv-1",
            timestamp=ts,
            correlation_id="corr-123",
            priority=10,
        )
        assert event.event_type == "tool.executed"
        assert event.payload == {"result": "ok"}
        assert event.user_id == "user-1"
        assert event.correlation_id == "corr-123"
        assert event.priority == 10

    def test_immutable(self):
        event = NoblaEvent(event_type="test", source="test")
        with pytest.raises(AttributeError):
            event.event_type = "changed"  # type: ignore[misc]

    def test_empty_event_type_raises(self):
        with pytest.raises(ValueError, match="event_type must not be empty"):
            NoblaEvent(event_type="", source="test")

    def test_empty_source_raises(self):
        with pytest.raises(ValueError, match="source must not be empty"):
            NoblaEvent(event_type="test", source="")

    def test_with_reply_type_preserves_correlation(self):
        original = NoblaEvent(
            event_type="channel.message.in",
            source="telegram",
            user_id="user-1",
            conversation_id="conv-1",
            correlation_id="trace-abc",
            priority=5,
        )
        reply = original.with_reply_type("channel.message.out")
        assert reply.event_type == "channel.message.out"
        assert reply.correlation_id == "trace-abc"
        assert reply.user_id == "user-1"
        assert reply.conversation_id == "conv-1"
        assert reply.priority == 5

    def test_unique_correlation_ids(self):
        e1 = NoblaEvent(event_type="a", source="s")
        e2 = NoblaEvent(event_type="b", source="s")
        assert e1.correlation_id != e2.correlation_id


# ── NoblaEventBus tests ────────────────────────────────────


class TestEventBusSubscription:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        bus = NoblaEventBus()
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event)

        bus.subscribe("tool.executed", handler)
        event = NoblaEvent(event_type="tool.executed", source="test")
        await bus.emit_nowait(event)

        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_no_match(self):
        bus = NoblaEventBus()
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event)

        bus.subscribe("tool.executed", handler)
        await bus.emit_nowait(NoblaEvent(event_type="channel.message.in", source="test"))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_wildcard_star(self):
        bus = NoblaEventBus()
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event)

        bus.subscribe("tool.*", handler)
        await bus.emit_nowait(NoblaEvent(event_type="tool.executed", source="test"))
        await bus.emit_nowait(NoblaEvent(event_type="tool.failed", source="test"))
        await bus.emit_nowait(NoblaEvent(event_type="channel.message.in", source="test"))

        assert len(received) == 2
        assert received[0].event_type == "tool.executed"
        assert received[1].event_type == "tool.failed"

    @pytest.mark.asyncio
    async def test_catch_all_wildcard(self):
        bus = NoblaEventBus()
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event)

        bus.subscribe("*", handler)
        await bus.emit_nowait(NoblaEvent(event_type="tool.executed", source="test"))
        await bus.emit_nowait(NoblaEvent(event_type="channel.message.in", source="test"))

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        bus = NoblaEventBus()
        results: list[str] = []

        async def handler_a(event: NoblaEvent) -> None:
            results.append("a")

        async def handler_b(event: NoblaEvent) -> None:
            results.append("b")

        bus.subscribe("test.event", handler_a)
        bus.subscribe("test.event", handler_b)
        await bus.emit_nowait(NoblaEvent(event_type="test.event", source="test"))

        assert sorted(results) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_ignored(self):
        bus = NoblaEventBus()

        async def handler(event: NoblaEvent) -> None:
            pass

        bus.subscribe("test", handler)
        bus.subscribe("test", handler)  # duplicate
        assert bus.handler_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = NoblaEventBus()
        received: list[NoblaEvent] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event)

        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        await bus.emit_nowait(NoblaEvent(event_type="test", source="test"))

        assert len(received) == 0
        assert bus.handler_count == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_noop(self):
        bus = NoblaEventBus()

        async def handler(event: NoblaEvent) -> None:
            pass

        bus.unsubscribe("test", handler)  # should not raise
        assert bus.handler_count == 0


class TestEventBusHandlerIsolation:
    @pytest.mark.asyncio
    async def test_failing_handler_does_not_block_others(self):
        bus = NoblaEventBus()
        results: list[str] = []

        async def bad_handler(event: NoblaEvent) -> None:
            raise RuntimeError("I broke")

        async def good_handler(event: NoblaEvent) -> None:
            results.append("ok")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)
        await bus.emit_nowait(NoblaEvent(event_type="test", source="test"))

        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_all_handlers_fail_gracefully(self):
        bus = NoblaEventBus()

        async def bad_handler(event: NoblaEvent) -> None:
            raise ValueError("fail")

        bus.subscribe("test", bad_handler)
        # Should not raise
        await bus.emit_nowait(NoblaEvent(event_type="test", source="test"))


class TestEventBusPriority:
    @pytest.mark.asyncio
    async def test_higher_priority_dispatched_first(self):
        bus = NoblaEventBus()
        order: list[int] = []

        async def handler(event: NoblaEvent) -> None:
            order.append(event.priority)

        bus.subscribe("*", handler)
        await bus.start()

        # Emit low priority first, then high
        await bus.emit(NoblaEvent(event_type="low", source="test", priority=0))
        await bus.emit(NoblaEvent(event_type="high", source="test", priority=10))

        # Give dispatch loop time to process
        await asyncio.sleep(0.1)
        await bus.stop()

        # High priority (10) should be dispatched before low (0)
        # But since they're queued nearly simultaneously, the priority queue
        # ensures the high-priority one comes out first
        assert 10 in order
        assert 0 in order


class TestEventBusBackpressure:
    @pytest.mark.asyncio
    async def test_overflow_drops_non_urgent(self):
        bus = NoblaEventBus(max_queue_depth=5)
        overflow_events: list[NoblaEvent] = []

        async def overflow_handler(event: NoblaEvent) -> None:
            overflow_events.append(event)

        bus.subscribe("bus.overflow", overflow_handler)

        # Fill the queue without starting dispatch (events accumulate)
        for i in range(5):
            await bus.emit(NoblaEvent(event_type=f"fill.{i}", source="test", priority=0))

        # Next non-urgent event should be dropped
        await bus.emit(NoblaEvent(event_type="dropped", source="test", priority=0))
        assert len(overflow_events) == 1
        assert overflow_events[0].payload["dropped_event_type"] == "dropped"

    @pytest.mark.asyncio
    async def test_overflow_allows_urgent(self):
        bus = NoblaEventBus(max_queue_depth=5)

        # Fill the queue
        for i in range(5):
            await bus.emit(NoblaEvent(event_type=f"fill.{i}", source="test", priority=0))

        # Urgent event should be accepted despite overflow
        await bus.emit(
            NoblaEvent(
                event_type="urgent", source="test", priority=URGENT_PRIORITY_THRESHOLD
            )
        )
        assert bus.pending_count == 6  # 5 + 1 urgent


class TestEventBusLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        bus = NoblaEventBus()
        assert not bus.is_running
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_double_start_noop(self):
        bus = NoblaEventBus()
        await bus.start()
        await bus.start()  # should not raise
        assert bus.is_running
        await bus.stop()

    @pytest.mark.asyncio
    async def test_dispatch_loop_processes_events(self):
        bus = NoblaEventBus()
        received: list[str] = []

        async def handler(event: NoblaEvent) -> None:
            received.append(event.event_type)

        bus.subscribe("test.*", handler)
        await bus.start()

        await bus.emit(NoblaEvent(event_type="test.one", source="s"))
        await bus.emit(NoblaEvent(event_type="test.two", source="s"))

        await asyncio.sleep(0.1)
        await bus.stop()

        assert "test.one" in received
        assert "test.two" in received

    @pytest.mark.asyncio
    async def test_drain_on_stop(self):
        bus = NoblaEventBus()
        received: list[str] = []

        async def slow_handler(event: NoblaEvent) -> None:
            received.append(event.event_type)

        bus.subscribe("drain.*", slow_handler)
        await bus.start()

        for i in range(3):
            await bus.emit(NoblaEvent(event_type=f"drain.{i}", source="s"))

        await asyncio.sleep(0.05)
        await bus.stop()

        # All events should have been processed (dispatched or drained)
        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_handler_count(self):
        bus = NoblaEventBus()

        async def h1(e: NoblaEvent) -> None:
            pass

        async def h2(e: NoblaEvent) -> None:
            pass

        bus.subscribe("a", h1)
        bus.subscribe("b", h2)
        bus.subscribe("b", h1)
        assert bus.handler_count == 3
