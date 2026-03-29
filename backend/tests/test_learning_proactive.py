"""Tests for Phase 5B.1 ProactiveEngine — suggestions, snooze, dismiss, auto-expire."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.proactive import ProactiveEngine
from nobla.learning.models import (
    ProactiveConfig,
    ProactiveLevel,
    ProactiveSuggestion,
    SuggestionStatus,
    SuggestionType,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


def _make_config(level=ProactiveLevel.CONSERVATIVE, max_per_day=1):
    return ProactiveConfig(level=level, max_suggestions_per_day=max_per_day)


def _make_suggestion(suggestion_id=None, confidence=0.95, status=SuggestionStatus.PENDING,
                     stype=SuggestionType.PATTERN, snooze_count=0, snooze_until=None):
    return ProactiveSuggestion(
        id=suggestion_id or str(uuid.uuid4()),
        type=stype, title="Test", description="desc",
        confidence=confidence, action={"wf": "1"}, user_id="user-1",
        status=status, snooze_until=snooze_until, snooze_count=snooze_count,
        expires_at=None, created_at=datetime.now(timezone.utc), source_pattern_id=None,
    )


class TestLevelFiltering:
    @pytest.mark.asyncio
    async def test_off_returns_nothing(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.OFF))
        engine.add_candidate(_make_suggestion(confidence=0.99))
        result = await engine.evaluate_suggestions("user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_conservative_filters_below_90(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.CONSERVATIVE))
        engine.add_candidate(_make_suggestion(confidence=0.85))
        engine.add_candidate(_make_suggestion(confidence=0.95))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1
        assert result[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_moderate_filters_below_70(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.MODERATE))
        engine.add_candidate(_make_suggestion(confidence=0.65))
        engine.add_candidate(_make_suggestion(confidence=0.75))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_aggressive_filters_below_50(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.AGGRESSIVE))
        engine.add_candidate(_make_suggestion(confidence=0.45))
        engine.add_candidate(_make_suggestion(confidence=0.55))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1


class TestMaxPerDay:
    @pytest.mark.asyncio
    async def test_conservative_max_1_per_day(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(max_per_day=1))
        engine.add_candidate(_make_suggestion(confidence=0.95))
        engine.add_candidate(_make_suggestion(confidence=0.92))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1


class TestAccept:
    @pytest.mark.asyncio
    async def test_accept_returns_action(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        s = _make_suggestion(suggestion_id="s1")
        engine.add_candidate(s)
        action = await engine.accept_suggestion("s1")
        assert action == {"wf": "1"}

    @pytest.mark.asyncio
    async def test_accept_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.accept_suggestion("s1")
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.accepted"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_accept_boosts_confidence(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.PATTERN))
        await engine.accept_suggestion("s1")
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(0.1)


class TestDismiss:
    @pytest.mark.asyncio
    async def test_dismiss_sets_status(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.dismiss_suggestion("s1", reason="irrelevant")
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.DISMISSED

    @pytest.mark.asyncio
    async def test_dismiss_applies_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.PATTERN))
        await engine.dismiss_suggestion("s1", reason="wrong")
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(-0.2)

    @pytest.mark.asyncio
    async def test_dismiss_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.dismiss_suggestion("s1")
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.dismissed"]
        assert len(calls) == 1


class TestSnooze:
    @pytest.mark.asyncio
    async def test_snooze_sets_status_and_until(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.snooze_suggestion("s1", days=3)
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.SNOOZED
        assert s.snooze_count == 1
        assert s.snooze_until is not None

    @pytest.mark.asyncio
    async def test_snooze_1_2x_no_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.OPTIMIZATION))
        await engine.snooze_suggestion("s1", days=1)
        assert engine.get_confidence_adjustment(SuggestionType.OPTIMIZATION) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_snooze_3x_applies_soft_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", snooze_count=2, stype=SuggestionType.PATTERN))
        await engine.snooze_suggestion("s1", days=1)  # now count=3
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(-0.05)

    @pytest.mark.asyncio
    async def test_snooze_5x_auto_expires(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", snooze_count=4))
        await engine.snooze_suggestion("s1", days=1)  # now count=5
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_snooze_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.snooze_suggestion("s1", days=7)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.snoozed"]
        assert len(calls) == 1


class TestCheckSnoozed:
    @pytest.mark.asyncio
    async def test_expired_snooze_resets_to_pending(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        engine.add_candidate(_make_suggestion(
            suggestion_id="s1", status=SuggestionStatus.SNOOZED,
            snooze_until=past, snooze_count=1,
        ))
        reactivated = await engine.check_snoozed()
        assert len(reactivated) == 1
        assert reactivated[0].status == SuggestionStatus.PENDING

    @pytest.mark.asyncio
    async def test_future_snooze_stays_snoozed(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        future = datetime.now(timezone.utc) + timedelta(days=2)
        engine.add_candidate(_make_suggestion(
            suggestion_id="s1", status=SuggestionStatus.SNOOZED,
            snooze_until=future, snooze_count=1,
        ))
        reactivated = await engine.check_snoozed()
        assert len(reactivated) == 0


class TestBriefing:
    @pytest.mark.asyncio
    async def test_briefing_only_when_aggressive(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.CONSERVATIVE))
        result = await engine.generate_briefing("user-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_briefing_generated_when_aggressive(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.AGGRESSIVE))
        result = await engine.generate_briefing("user-1")
        assert result is not None
        assert result.type == SuggestionType.BRIEFING
