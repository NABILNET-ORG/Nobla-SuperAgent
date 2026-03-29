"""Tests for Phase 5B.2 MarketplaceService orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.marketplace.service import MarketplaceService


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return bus


@pytest.fixture
def registry():
    r = AsyncMock()
    r.publish = AsyncMock()
    r.get_skill = AsyncMock()
    r.get_ratings = AsyncMock(return_value=[])
    r.submit_rating = AsyncMock()
    r.check_updates = AsyncMock(return_value=[])
    r.get_categories = AsyncMock(return_value={})
    r.request_verification = AsyncMock()
    r.admin_review = AsyncMock()
    r.publish_version = AsyncMock()
    r.unpublish = AsyncMock()
    return r


@pytest.fixture
def discovery():
    d = AsyncMock()
    d.search = AsyncMock()
    d.get_recommendations = AsyncMock(return_value={
        "based_on_patterns": [], "similar_to_installed": []
    })
    return d


@pytest.fixture
def usage_tracker():
    return MagicMock()


@pytest.fixture
def skill_runtime():
    rt = AsyncMock()
    rt.install = AsyncMock()
    rt.uninstall = AsyncMock()
    return rt


@pytest.fixture
def settings():
    s = MagicMock()
    s.enabled = True
    return s


@pytest.fixture
def service(event_bus, registry, discovery, usage_tracker, skill_runtime, settings):
    return MarketplaceService(
        event_bus=event_bus,
        registry=registry,
        discovery=discovery,
        usage_tracker=usage_tracker,
        skill_runtime=skill_runtime,
        settings=settings,
    )


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_subscribes_to_events(self, service, event_bus):
        await service.start()
        assert event_bus.subscribe.call_count == 4
        event_types = [c[0][0] for c in event_bus.subscribe.call_args_list]
        assert "tool.executed" in event_types
        assert "tool.failed" in event_types
        assert "skill.installed" in event_types
        assert "skill.uninstalled" in event_types

    @pytest.mark.asyncio
    async def test_stop_unsubscribes_all(self, service, event_bus):
        await service.start()
        await service.stop()
        assert event_bus.unsubscribe.call_count == 4

    @pytest.mark.asyncio
    async def test_start_skipped_when_disabled(self, event_bus, registry, discovery, usage_tracker):
        settings = MagicMock()
        settings.enabled = False
        svc = MarketplaceService(
            event_bus=event_bus, registry=registry, discovery=discovery,
            usage_tracker=usage_tracker, settings=settings,
        )
        await svc.start()
        event_bus.subscribe.assert_not_called()


class TestInstallUninstall:
    @pytest.mark.asyncio
    async def test_install_skill_delegates_to_runtime(self, service, registry, skill_runtime, event_bus):
        skill = MagicMock()
        skill.current_version = "1.0.0"
        registry.get_skill = AsyncMock(return_value=skill)
        await service.install_skill("s1", "u1")
        skill_runtime.install.assert_called_once_with("s1")
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "marketplace.skill.installed"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_uninstall_skill_delegates(self, service, skill_runtime, event_bus):
        await service.uninstall_skill("s1", "u1")
        skill_runtime.uninstall.assert_called_once_with("s1")
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "marketplace.skill.uninstalled"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_install_not_found_raises(self, service, registry):
        registry.get_skill = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.install_skill("bad-id", "u1")


class TestDelegation:
    @pytest.mark.asyncio
    async def test_publish_delegates_to_registry(self, service, registry):
        await service.publish("a1", "Author", {"name": "x"}, None)
        registry.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_delegates_to_discovery(self, service, discovery):
        await service.search(query="test")
        discovery.search.assert_called_once_with(query="test")

    @pytest.mark.asyncio
    async def test_submit_rating_delegates(self, service, registry):
        await service.submit_rating("s1", "u1", 5, "Great")
        registry.submit_rating.assert_called_once_with("s1", "u1", 5, "Great")

    @pytest.mark.asyncio
    async def test_check_updates_delegates(self, service, registry):
        await service.check_updates({"skill-a": "1.0.0"})
        registry.check_updates.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_recommendations_delegates(self, service, discovery):
        await service.get_recommendations("u1")
        discovery.get_recommendations.assert_called_once_with("u1")
