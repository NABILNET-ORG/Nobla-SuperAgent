"""Tests for Phase 5B.1 FeedbackCollector — capture, store, emit events."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.feedback import FeedbackCollector
from nobla.learning.models import (
    FeedbackContext,
    ResponseFeedback,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def collector(event_bus):
    return FeedbackCollector(event_bus=event_bus)


def _make_feedback(quick_rating=1, star_rating=None, comment=None, ab_variant_id=None):
    return ResponseFeedback(
        id=str(uuid.uuid4()),
        conversation_id="conv-1",
        message_id="msg-1",
        user_id="user-1",
        quick_rating=quick_rating,
        star_rating=star_rating,
        comment=comment,
        context=FeedbackContext(
            llm_model="gemini-pro",
            prompt_template=None,
            tool_chain=["code.run"],
            intent_category="medium",
            ab_variant_id=ab_variant_id,
        ),
        timestamp=datetime.now(timezone.utc),
    )


class TestSubmitFeedback:
    @pytest.mark.asyncio
    async def test_submit_stores_feedback(self, collector):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        result = await collector.get_feedback_for_conversation("conv-1")
        assert len(result) == 1
        assert result[0].id == fb.id

    @pytest.mark.asyncio
    async def test_submit_emits_submitted_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.submitted"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_positive_feedback_emits_positive_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.positive"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_negative_feedback_emits_negative_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=-1, star_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.negative"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_neutral_feedback_no_positive_or_negative_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=0, star_rating=3)
        await collector.submit_feedback(fb)
        pos = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.positive"]
        neg = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.negative"]
        assert len(pos) == 0
        assert len(neg) == 0


class TestToolChainTracking:
    @pytest.mark.asyncio
    async def test_on_tool_executed_records_chain(self, collector):
        event = MagicMock()
        event.event_type = "tool.executed"
        event.correlation_id = "corr-1"
        event.payload = {"tool_name": "file.manage"}
        await collector.on_tool_executed(event)
        chain = collector.get_tool_chain("corr-1")
        assert chain == ["file.manage"]

    @pytest.mark.asyncio
    async def test_multiple_tools_build_chain(self, collector):
        for tool in ["file.manage", "code.run", "ssh.exec"]:
            event = MagicMock()
            event.event_type = "tool.executed"
            event.correlation_id = "corr-1"
            event.payload = {"tool_name": tool}
            await collector.on_tool_executed(event)
        chain = collector.get_tool_chain("corr-1")
        assert chain == ["file.manage", "code.run", "ssh.exec"]


class TestFeedbackStats:
    @pytest.mark.asyncio
    async def test_stats_count(self, collector):
        await collector.submit_feedback(_make_feedback(quick_rating=1))
        await collector.submit_feedback(_make_feedback(quick_rating=1, star_rating=5))
        await collector.submit_feedback(_make_feedback(quick_rating=-1))
        stats = await collector.get_feedback_stats("user-1")
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1
