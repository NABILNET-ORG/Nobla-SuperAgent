"""Tests for Phase 5B.2 MarketplaceRegistry — CRUD, publish, verify, rate."""

from __future__ import annotations

import json
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.marketplace.registry import MarketplaceRegistry
from nobla.marketplace.packager import SkillPackager
from nobla.marketplace.models import (
    TrustTier,
    VerificationStatus,
    PackageType,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def security_scanner():
    scanner = AsyncMock()
    scan_result = MagicMock()
    scan_result.passed = True
    scan_result.issues = []
    scanner.scan = AsyncMock(return_value=scan_result)
    return scanner


@pytest.fixture
def packager():
    return SkillPackager()


@pytest.fixture
def registry(event_bus, packager, security_scanner):
    return MarketplaceRegistry(
        event_bus=event_bus,
        packager=packager,
        security_scanner=security_scanner,
    )


def _valid_manifest():
    return {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "category": "utilities",
        "source": "nobla",
    }


def _make_archive(manifest=None):
    m = manifest or _valid_manifest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nobla-skill.json", json.dumps(m))
        zf.writestr("skill.py", "class MySkill: pass")
    return buf.getvalue()


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_archive_skill(self, registry):
        skill = await registry.publish(
            author_id="a1", author_name="Author",
            manifest=_valid_manifest(),
            archive_data=_make_archive(),
        )
        assert skill.name == "test-skill"
        assert skill.trust_tier == TrustTier.COMMUNITY
        assert skill.security_scan_passed is True
        assert skill.package_type == PackageType.ARCHIVE
        assert len(skill.versions) == 1

    @pytest.mark.asyncio
    async def test_publish_pointer_skill(self, registry):
        manifest = {
            "name": "github-mcp",
            "version": "1.0.0",
            "description": "GitHub via MCP",
            "category": "productivity",
            "source": "mcp",
            "source_url": "npx @modelcontextprotocol/server-github",
        }
        skill = await registry.publish(
            author_id="a1", author_name="Author",
            manifest=manifest, archive_data=None,
        )
        assert skill.package_type == PackageType.POINTER
        assert skill.source_url == "npx @modelcontextprotocol/server-github"

    @pytest.mark.asyncio
    async def test_publish_emits_event(self, registry, event_bus):
        await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "marketplace.skill.published"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_scan_failure_rejects(self, registry, security_scanner):
        scan_result = MagicMock()
        scan_result.passed = False
        scan_result.issues = ["dangerous pattern"]
        security_scanner.scan = AsyncMock(return_value=scan_result)
        with pytest.raises(ValueError, match="security"):
            await registry.publish("a1", "Author", _valid_manifest(), _make_archive())

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, registry):
        await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        with pytest.raises(ValueError, match="exists"):
            await registry.publish("a1", "Author", _valid_manifest(), _make_archive())

    @pytest.mark.asyncio
    async def test_max_skills_per_author(self, registry):
        registry._max_skills_per_author = 2
        for i in range(2):
            m = _valid_manifest()
            m["name"] = f"skill-{i}"
            await registry.publish("a1", "Author", m, _make_archive(m))
        m3 = _valid_manifest()
        m3["name"] = "skill-2"
        with pytest.raises(ValueError, match="limit"):
            await registry.publish("a1", "Author", m3, _make_archive(m3))


class TestVersionPublish:
    @pytest.mark.asyncio
    async def test_publish_new_version(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        new_manifest = _valid_manifest()
        new_manifest["version"] = "1.1.0"
        version = await registry.publish_version(skill.id, new_manifest, _make_archive(new_manifest))
        assert version.version == "1.1.0"
        updated = await registry.get_skill(skill.id)
        assert updated.current_version == "1.1.0"
        assert len(updated.versions) == 2

    @pytest.mark.asyncio
    async def test_version_must_be_greater(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        old_manifest = _valid_manifest()
        old_manifest["version"] = "0.9.0"
        with pytest.raises(ValueError, match="greater"):
            await registry.publish_version(skill.id, old_manifest, _make_archive(old_manifest))

    @pytest.mark.asyncio
    async def test_version_emits_update_event(self, registry, event_bus):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        event_bus.emit.reset_mock()
        new_m = _valid_manifest()
        new_m["version"] = "1.1.0"
        await registry.publish_version(skill.id, new_m, _make_archive(new_m))
        types = [c[0][0].event_type for c in event_bus.emit.call_args_list]
        assert "marketplace.skill.updated" in types


class TestVerification:
    @pytest.mark.asyncio
    async def test_request_verification(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.request_verification(skill.id)
        updated = await registry.get_skill(skill.id)
        assert updated.verification_status == VerificationStatus.PENDING

    @pytest.mark.asyncio
    async def test_admin_approve(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.request_verification(skill.id)
        await registry.admin_review(skill.id, approved=True, reason=None)
        updated = await registry.get_skill(skill.id)
        assert updated.trust_tier == TrustTier.VERIFIED
        assert updated.verification_status == VerificationStatus.APPROVED

    @pytest.mark.asyncio
    async def test_admin_reject(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.request_verification(skill.id)
        await registry.admin_review(skill.id, approved=False, reason="Incomplete docs")
        updated = await registry.get_skill(skill.id)
        assert updated.trust_tier == TrustTier.COMMUNITY
        assert updated.verification_status == VerificationStatus.REJECTED


class TestRatings:
    @pytest.mark.asyncio
    async def test_submit_rating(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        rating = await registry.submit_rating(skill.id, "user-1", 4, "Good!")
        assert rating.stars == 4
        updated = await registry.get_skill(skill.id)
        assert updated.avg_rating == 4.0
        assert updated.rating_count == 1

    @pytest.mark.asyncio
    async def test_upsert_rating(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.submit_rating(skill.id, "user-1", 3, None)
        await registry.submit_rating(skill.id, "user-1", 5, "Changed my mind")
        updated = await registry.get_skill(skill.id)
        assert updated.avg_rating == 5.0
        assert updated.rating_count == 1  # upsert, not duplicate

    @pytest.mark.asyncio
    async def test_multiple_ratings_average(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.submit_rating(skill.id, "u1", 4, None)
        await registry.submit_rating(skill.id, "u2", 2, None)
        updated = await registry.get_skill(skill.id)
        assert updated.avg_rating == pytest.approx(3.0)
        assert updated.rating_count == 2

    @pytest.mark.asyncio
    async def test_rating_emits_event(self, registry, event_bus):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        event_bus.emit.reset_mock()
        await registry.submit_rating(skill.id, "u1", 5, None)
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "marketplace.skill.rated"]
        assert len(calls) == 1


class TestCheckUpdates:
    @pytest.mark.asyncio
    async def test_finds_available_update(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        new_m = _valid_manifest()
        new_m["version"] = "1.1.0"
        await registry.publish_version(skill.id, new_m, _make_archive(new_m))
        updates = await registry.check_updates({"test-skill": "1.0.0"})
        assert len(updates) == 1
        assert updates[0].latest_version == "1.1.0"

    @pytest.mark.asyncio
    async def test_no_update_when_current(self, registry):
        await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        updates = await registry.check_updates({"test-skill": "1.0.0"})
        assert len(updates) == 0


class TestUnpublish:
    @pytest.mark.asyncio
    async def test_unpublish_removes_skill(self, registry):
        skill = await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        await registry.unpublish(skill.id)
        result = await registry.get_skill(skill.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_skills(self, registry):
        await registry.publish("a1", "Author", _valid_manifest(), _make_archive())
        all_skills = await registry.get_all_skills()
        assert len(all_skills) == 1
