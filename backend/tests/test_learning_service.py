"""Tests for LearningService orchestrator."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from nobla.learning.service import LearningService


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.subscribe = MagicMock(side_effect=lambda t, h: f"sub_{t}")
    bus.unsubscribe = MagicMock()
    return bus

@pytest.fixture
def settings():
    s = MagicMock()
    s.enabled = True
    s.proactive_level = "conservative"
    return s

@pytest.fixture
def components():
    return {
        "feedback": AsyncMock(),
        "patterns": AsyncMock(),
        "generator": AsyncMock(),
        "ab_testing": AsyncMock(),
        "proactive": AsyncMock(),
    }

@pytest.fixture
def service(event_bus, settings, components):
    return LearningService(
        event_bus=event_bus, settings=settings,
        **components,
    )


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_subscribes_events(self, service, event_bus):
        await service.start()
        assert event_bus.subscribe.call_count == 2
        event_types = [c[0][0] for c in event_bus.subscribe.call_args_list]
        assert "tool.executed" in event_types
        assert "tool.failed" in event_types

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self, service, event_bus):
        await service.start()
        await service.stop()
        assert event_bus.unsubscribe.call_count == 2

    @pytest.mark.asyncio
    async def test_start_disabled_is_noop(self, event_bus, components):
        s = MagicMock()
        s.enabled = False
        svc = LearningService(event_bus=event_bus, settings=s, **components)
        await svc.start()
        event_bus.subscribe.assert_not_called()


class TestDelegation:
    @pytest.mark.asyncio
    async def test_submit_feedback_delegates(self, service, components):
        fb = MagicMock()
        await service.submit_feedback(fb)
        components["feedback"].submit_feedback.assert_called_once_with(fb)

    @pytest.mark.asyncio
    async def test_get_patterns_delegates(self, service, components):
        await service.get_patterns("user-1", status=None)
        components["patterns"].get_patterns.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_experiment_delegates(self, service, components):
        await service.create_experiment("hard", [{"model": "a"}])
        components["ab_testing"].create_experiment.assert_called_once()

    @pytest.mark.asyncio
    async def test_snooze_suggestion_delegates(self, service, components):
        await service.snooze_suggestion("s1", days=3)
        components["proactive"].snooze_suggestion.assert_called_once_with("s1", days=3)


class TestSettings:
    def test_get_settings(self, service):
        result = service.get_settings()
        assert result["enabled"] is True
        assert result["proactive_level"] == "conservative"
