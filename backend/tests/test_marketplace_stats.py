"""Tests for Phase 5B.2 UsageTracker — event-driven skill stats."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.marketplace.stats import UsageTracker


def _make_event(event_type: str, payload: dict | None = None):
    e = MagicMock()
    e.event_type = event_type
    e.payload = payload or {}
    return e


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return bus


@pytest.fixture
def registry():
    reg = AsyncMock()
    skill = MagicMock()
    skill.install_count = 0
    skill.active_users = 0
    skill.success_rate = 0.0
    reg.get_skill = AsyncMock(return_value=skill)
    return reg


@pytest.fixture
def tracker(event_bus, registry):
    return UsageTracker(event_bus=event_bus, registry=registry)


class TestSkillInstalled:
    @pytest.mark.asyncio
    async def test_increments_install_count(self, tracker, registry):
        skill = MagicMock()
        skill.install_count = 0
        skill.active_users = 0
        registry.get_skill = AsyncMock(return_value=skill)
        event = _make_event("skill.installed", {"skill_id": "s1", "user_id": "u1"})
        await tracker.on_skill_installed(event)
        assert skill.install_count == 1
        assert skill.active_users == 1

    @pytest.mark.asyncio
    async def test_ignores_event_without_skill_id(self, tracker, registry):
        event = _make_event("skill.installed", {})
        await tracker.on_skill_installed(event)
        registry.get_skill.assert_not_called()


class TestSkillUninstalled:
    @pytest.mark.asyncio
    async def test_decrements_active_users(self, tracker, registry):
        skill = MagicMock()
        skill.active_users = 5
        registry.get_skill = AsyncMock(return_value=skill)
        event = _make_event("skill.uninstalled", {"skill_id": "s1", "user_id": "u1"})
        await tracker.on_skill_uninstalled(event)
        assert skill.active_users == 4

    @pytest.mark.asyncio
    async def test_active_users_not_below_zero(self, tracker, registry):
        skill = MagicMock()
        skill.active_users = 0
        registry.get_skill = AsyncMock(return_value=skill)
        event = _make_event("skill.uninstalled", {"skill_id": "s1", "user_id": "u1"})
        await tracker.on_skill_uninstalled(event)
        assert skill.active_users == 0


class TestToolExecuted:
    @pytest.mark.asyncio
    async def test_tracks_success(self, tracker, registry):
        skill = MagicMock()
        skill.success_rate = 0.0
        registry.get_skill = AsyncMock(return_value=skill)
        event = _make_event("tool.executed", {"skill_id": "s1"})
        await tracker.on_tool_executed(event)
        stats = await tracker.get_stats("s1")
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_ignores_without_skill_id(self, tracker):
        event = _make_event("tool.executed", {"tool_name": "some.tool"})
        await tracker.on_tool_executed(event)
        stats = await tracker.get_stats("nonexistent")
        assert stats["success_count"] == 0


class TestToolFailed:
    @pytest.mark.asyncio
    async def test_tracks_failure(self, tracker, registry):
        skill = MagicMock()
        skill.success_rate = 0.0
        registry.get_skill = AsyncMock(return_value=skill)
        event = _make_event("tool.failed", {"skill_id": "s1"})
        await tracker.on_tool_failed(event)
        stats = await tracker.get_stats("s1")
        assert stats["failure_count"] == 1


class TestGetStats:
    @pytest.mark.asyncio
    async def test_success_rate_calculation(self, tracker, registry):
        skill = MagicMock()
        skill.success_rate = 0.0
        registry.get_skill = AsyncMock(return_value=skill)
        for _ in range(3):
            await tracker.on_tool_executed(_make_event("tool.executed", {"skill_id": "s1"}))
        await tracker.on_tool_failed(_make_event("tool.failed", {"skill_id": "s1"}))
        stats = await tracker.get_stats("s1")
        assert stats["success_count"] == 3
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_success_rate_zero_when_no_data(self, tracker):
        stats = await tracker.get_stats("unknown")
        assert stats["success_rate"] == 0.0
