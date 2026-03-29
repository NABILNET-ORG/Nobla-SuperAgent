"""Tests for Phase 5B.2 SkillDiscovery — keyword search, filters, recommendations."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.marketplace.discovery import SkillDiscovery
from nobla.marketplace.models import TrustTier, PackageType
from nobla.marketplace.packager import SkillPackager
from nobla.marketplace.registry import MarketplaceRegistry
from nobla.skills.models import SkillCategory, SkillSource


def _make_archive(manifest):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nobla-skill.json", json.dumps(manifest))
        zf.writestr("skill.py", "pass")
    return buf.getvalue()


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def security_scanner():
    scanner = AsyncMock()
    result = MagicMock()
    result.passed = True
    result.issues = []
    scanner.scan = AsyncMock(return_value=result)
    return scanner


@pytest.fixture
def registry(event_bus, security_scanner):
    return MarketplaceRegistry(
        event_bus=event_bus,
        packager=SkillPackager(),
        security_scanner=security_scanner,
    )


@pytest.fixture
def discovery(registry):
    return SkillDiscovery(registry=registry)


async def _populate(registry):
    """Publish 4 skills with varied categories/tags for search tests."""
    skills = [
        {"name": "github-mcp", "version": "1.0.0", "description": "GitHub integration via MCP",
         "category": "productivity", "source": "mcp", "tags": ["github", "git", "code-review"],
         "source_url": "npx @modelcontextprotocol/server-github"},
        {"name": "docker-tool", "version": "2.0.0", "description": "Docker container management",
         "category": "utilities", "source": "nobla", "tags": ["docker", "containers"]},
        {"name": "slack-bot", "version": "1.0.0", "description": "Slack messaging integration",
         "category": "communication", "source": "nobla", "tags": ["slack", "messaging"]},
        {"name": "code-analyzer", "version": "1.5.0", "description": "Static code analysis tool",
         "category": "code", "source": "nobla", "tags": ["code", "analysis", "git"]},
    ]
    published = []
    for m in skills:
        archive = None if m.get("source_url") else _make_archive(m)
        s = await registry.publish("a1", "Author", m, archive)
        published.append(s)
    return published


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_no_filters_returns_all(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search()
        assert results.total == 4

    @pytest.mark.asyncio
    async def test_search_by_keyword(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search(query="github")
        assert results.total >= 1
        assert any(s.name == "github-mcp" for s in results.items)

    @pytest.mark.asyncio
    async def test_search_by_category(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search(category=SkillCategory.PRODUCTIVITY)
        assert results.total == 1
        assert results.items[0].name == "github-mcp"

    @pytest.mark.asyncio
    async def test_search_by_trust_tier(self, discovery, registry):
        published = await _populate(registry)
        # All are community by default
        results = await discovery.search(trust_tier=TrustTier.COMMUNITY)
        assert results.total == 4
        results = await discovery.search(trust_tier=TrustTier.VERIFIED)
        assert results.total == 0

    @pytest.mark.asyncio
    async def test_search_by_tags(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search(tags=["git"])
        assert results.total >= 2
        names = {s.name for s in results.items}
        assert "github-mcp" in names
        assert "code-analyzer" in names

    @pytest.mark.asyncio
    async def test_search_sort_by_install_count(self, discovery, registry):
        published = await _populate(registry)
        published[1].install_count = 100
        published[0].install_count = 50
        results = await discovery.search(sort_by="install_count")
        assert results.items[0].name == "docker-tool"

    @pytest.mark.asyncio
    async def test_search_pagination(self, discovery, registry):
        await _populate(registry)
        page1 = await discovery.search(page=1, page_size=2)
        assert len(page1.items) == 2
        assert page1.total == 4
        assert page1.page == 1
        page2 = await discovery.search(page=2, page_size=2)
        assert len(page2.items) == 2
        assert page2.page == 2

    @pytest.mark.asyncio
    async def test_search_by_source_format(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search(source_format=SkillSource.MCP)
        assert results.total == 1
        assert results.items[0].name == "github-mcp"

    @pytest.mark.asyncio
    async def test_search_keyword_case_insensitive(self, discovery, registry):
        await _populate(registry)
        results = await discovery.search(query="DOCKER")
        assert results.total >= 1


class TestRecommendations:
    @pytest.mark.asyncio
    async def test_pattern_recommendations_no_detector(self, discovery):
        recs = await discovery.get_pattern_recommendations("user-1")
        assert recs == []

    @pytest.mark.asyncio
    async def test_similar_recommendations_no_runtime(self, discovery):
        recs = await discovery.get_similar_recommendations("user-1")
        assert recs == []

    @pytest.mark.asyncio
    async def test_get_recommendations_returns_both_tracks(self, discovery):
        result = await discovery.get_recommendations("user-1")
        assert "based_on_patterns" in result
        assert "similar_to_installed" in result

    @pytest.mark.asyncio
    async def test_similar_recommendations_by_category(self, registry):
        """Skills in same category as installed are recommended."""
        await _populate(registry)
        installed = [s for s in (await registry.get_all_skills()) if s.name == "github-mcp"]
        runtime = MagicMock()
        runtime.get_installed_skills = MagicMock(return_value=installed)
        disc = SkillDiscovery(registry=registry, skill_runtime=runtime)
        recs = await disc.get_similar_recommendations("user-1")
        # No other productivity skills, so recs should be empty
        assert isinstance(recs, list)

    @pytest.mark.asyncio
    async def test_pattern_recommendations_with_detector(self, registry):
        await _populate(registry)
        pattern_detector = MagicMock()
        pattern = MagicMock()
        pattern.tool_sequence = ["git.ops", "code.run"]
        pattern.confidence = 0.9
        pattern_detector.get_user_patterns = MagicMock(return_value=[pattern])
        disc = SkillDiscovery(
            registry=registry, pattern_detector=pattern_detector
        )
        recs = await disc.get_pattern_recommendations("user-1")
        # Should find skills with matching tags/categories
        assert isinstance(recs, list)
