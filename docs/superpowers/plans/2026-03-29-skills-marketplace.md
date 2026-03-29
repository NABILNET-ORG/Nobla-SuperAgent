# Phase 5B.2: Universal Skills Marketplace Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a marketplace for discovering, publishing, versioning, rating, and installing skills — supporting both `.nobla` archive packages and manifest-pointers (MCP, OpenClaw, etc.).

**Architecture:** Six backend modules (`models`, `packager`, `registry`, `discovery`, `stats`, `service`) orchestrated by `MarketplaceService`, with 15 REST routes. Flutter adds a marketplace sub-screen under the Tools tab with search, recommendations, skill detail, and ratings.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, structlog, pytest. Flutter 3.x, Riverpod, GoRouter, flutter_test. Existing: SkillRuntime, SkillSecurityScanner, NoblaEventBus, ChromaDB (for semantic search).

**Spec:** `docs/superpowers/specs/2026-03-29-skills-marketplace-design.md`

---

## File Map

### Backend — New Files

| File | Responsibility | Est. Lines |
|------|---------------|------------|
| `backend/nobla/marketplace/__init__.py` | Package exports | ~10 |
| `backend/nobla/marketplace/models.py` | MarketplaceSkill, SkillVersion, SkillRating, enums | ~220 |
| `backend/nobla/marketplace/packager.py` | Archive pack/unpack, manifest validate, SHA-256 hash | ~200 |
| `backend/nobla/marketplace/registry.py` | CRUD, publish pipeline, verification, ratings | ~300 |
| `backend/nobla/marketplace/discovery.py` | Keyword + semantic search, recommendations | ~250 |
| `backend/nobla/marketplace/stats.py` | UsageTracker — event listeners, stat aggregation | ~150 |
| `backend/nobla/marketplace/service.py` | MarketplaceService orchestrator, install/uninstall | ~200 |
| `backend/nobla/gateway/marketplace_handlers.py` | REST API (15 routes) + Pydantic schemas | ~300 |
| `backend/tests/test_marketplace_models.py` | Model + enum tests | ~180 |
| `backend/tests/test_marketplace_packager.py` | Packager tests | ~200 |
| `backend/tests/test_marketplace_registry.py` | Registry tests | ~280 |
| `backend/tests/test_marketplace_discovery.py` | Discovery tests | ~220 |
| `backend/tests/test_marketplace_stats.py` | UsageTracker tests | ~150 |
| `backend/tests/test_marketplace_service.py` | Service integration tests | ~180 |
| `backend/tests/test_marketplace_handlers.py` | REST handler tests | ~250 |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/nobla/config/settings.py` | Add `MarketplaceSettings` + `marketplace` field on `Settings` |
| `backend/nobla/gateway/lifespan.py` | Wire MarketplaceService (after learning, before multi-agent) |
| `backend/nobla/tools/executor.py` | Add `skill_id` to event payload for SkillToolBridge tools |

### Flutter — New Files

| File | Responsibility | Est. Lines |
|------|---------------|------------|
| `app/lib/features/marketplace/models/marketplace_models.dart` | Dart models + enums | ~280 |
| `app/lib/features/marketplace/providers/marketplace_providers.dart` | Riverpod providers | ~150 |
| `app/lib/features/marketplace/screens/marketplace_screen.dart` | Search + grid + recommendations | ~260 |
| `app/lib/features/marketplace/screens/skill_detail_screen.dart` | Detail with versions + ratings | ~260 |
| `app/lib/features/marketplace/widgets/skill_card.dart` | Grid card with stats | ~130 |
| `app/lib/features/marketplace/widgets/rating_widget.dart` | Star display + submit | ~110 |
| `app/lib/features/marketplace/widgets/version_list_widget.dart` | Expandable version list | ~90 |
| `app/test/features/marketplace/marketplace_models_test.dart` | Model tests | ~180 |
| `app/test/features/marketplace/screens_test.dart` | Screen tests | ~150 |
| `app/test/features/marketplace/widgets_test.dart` | Widget tests | ~200 |

### Flutter — Modified Files

| File | Change |
|------|--------|
| `app/lib/core/routing/app_router.dart` | Add `/home/tools/marketplace` and `/home/tools/marketplace/:id` routes |

---

## Task 1: Models + Enums + Settings

**Files:**
- Create: `backend/nobla/marketplace/__init__.py`
- Create: `backend/nobla/marketplace/models.py`
- Modify: `backend/nobla/config/settings.py`
- Test: `backend/tests/test_marketplace_models.py`

- [ ] **Step 1: Create package init**

```python
# backend/nobla/marketplace/__init__.py
"""Universal Skills Marketplace — discovery, publishing, versioning, ratings."""
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_marketplace_models.py`:

```python
"""Tests for Phase 5B.2 marketplace models and enums."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from nobla.marketplace.models import (
    PackageType,
    TrustTier,
    VerificationStatus,
    SkillVersion,
    MarketplaceSkill,
    SkillRating,
    UpdateNotification,
    PackageValidation,
)
from nobla.skills.models import SkillCategory, SkillSource


class TestEnums:
    def test_package_type_values(self):
        assert PackageType.ARCHIVE == "archive"
        assert PackageType.POINTER == "pointer"

    def test_trust_tier_values(self):
        assert TrustTier.COMMUNITY == "community"
        assert TrustTier.VERIFIED == "verified"
        assert TrustTier.OFFICIAL == "official"

    def test_verification_status_values(self):
        assert VerificationStatus.NONE == "none"
        assert VerificationStatus.PENDING == "pending"
        assert VerificationStatus.APPROVED == "approved"
        assert VerificationStatus.REJECTED == "rejected"


class TestSkillVersion:
    def test_create_version(self):
        v = SkillVersion(
            version="1.2.3",
            changelog="Added feature X",
            package_hash="abc123",
            min_nobla_version=None,
            published_at=datetime.now(timezone.utc),
            scan_passed=True,
        )
        assert v.version == "1.2.3"
        assert v.scan_passed is True


class TestMarketplaceSkill:
    def test_create_skill(self):
        s = MarketplaceSkill(
            id=str(uuid.uuid4()),
            name="github-mcp",
            display_name="GitHub MCP",
            description="GitHub integration via MCP",
            author_id="author-1",
            author_name="Nobla Team",
            category=SkillCategory.PRODUCTIVITY,
            tags=["github", "git"],
            source_format=SkillSource.MCP,
            package_type=PackageType.POINTER,
            source_url="npx @modelcontextprotocol/server-github",
            current_version="1.0.0",
            versions=[],
            trust_tier=TrustTier.COMMUNITY,
            verification_status=VerificationStatus.NONE,
            security_scan_passed=True,
            install_count=0,
            active_users=0,
            avg_rating=0.0,
            rating_count=0,
            success_rate=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert s.name == "github-mcp"
        assert s.package_type == PackageType.POINTER

    def test_create_archive_skill(self):
        s = MarketplaceSkill(
            id=str(uuid.uuid4()),
            name="my-skill",
            display_name="My Skill",
            description="A custom skill",
            author_id="a1", author_name="Author",
            category=SkillCategory.UTILITIES,
            tags=["utility"],
            source_format=SkillSource.NOBLA,
            package_type=PackageType.ARCHIVE,
            source_url=None,
            current_version="0.1.0",
            versions=[], trust_tier=TrustTier.COMMUNITY,
            verification_status=VerificationStatus.NONE,
            security_scan_passed=True,
            install_count=0, active_users=0,
            avg_rating=0.0, rating_count=0, success_rate=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert s.package_type == PackageType.ARCHIVE
        assert s.source_url is None


class TestSkillRating:
    def test_create_rating(self):
        r = SkillRating(
            id=str(uuid.uuid4()),
            skill_id="skill-1",
            user_id="user-1",
            stars=4,
            review="Great tool!",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert r.stars == 4
        assert r.review == "Great tool!"

    def test_rating_without_review(self):
        r = SkillRating(
            id="r1", skill_id="s1", user_id="u1",
            stars=5, review=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert r.review is None


class TestUpdateNotification:
    def test_create_notification(self):
        n = UpdateNotification(
            skill_id="s1",
            skill_name="github-mcp",
            installed_version="1.0.0",
            latest_version="1.1.0",
            changelog="Bug fixes",
            published_at=datetime.now(timezone.utc),
        )
        assert n.installed_version == "1.0.0"
        assert n.latest_version == "1.1.0"


class TestPackageValidation:
    def test_valid_result(self):
        v = PackageValidation(valid=True, issues=[])
        assert v.valid is True

    def test_invalid_result(self):
        v = PackageValidation(valid=False, issues=["Missing name field"])
        assert not v.valid
        assert len(v.issues) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement models.py**

Create `backend/nobla/marketplace/models.py` with:
- Enums: `PackageType`, `TrustTier`, `VerificationStatus` (all `str, Enum`)
- Dataclasses: `SkillVersion`, `MarketplaceSkill`, `SkillRating`, `UpdateNotification`, `PackageValidation`
- Reuse `SkillCategory` and `SkillSource` from `nobla.skills.models`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_marketplace_models.py -v`
Expected: all PASS

- [ ] **Step 6: Add MarketplaceSettings to config**

Modify `backend/nobla/config/settings.py`:
```python
class MarketplaceSettings(BaseModel):
    enabled: bool = True
    max_skills_per_author: int = 50
    max_archive_size_mb: int = 10
    storage_dir: str = "data/marketplace"
```
Add `marketplace: MarketplaceSettings = MarketplaceSettings()` field on `Settings`.

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/marketplace/__init__.py backend/nobla/marketplace/models.py backend/nobla/config/settings.py backend/tests/test_marketplace_models.py
git commit -m "feat(5b2): add marketplace models, enums, MarketplaceSettings"
```

---

## Task 2: SkillPackager

**Files:**
- Create: `backend/nobla/marketplace/packager.py`
- Test: `backend/tests/test_marketplace_packager.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_marketplace_packager.py`:

```python
"""Tests for Phase 5B.2 SkillPackager — archive/manifest validation, hashing."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nobla.marketplace.packager import SkillPackager


@pytest.fixture
def packager():
    return SkillPackager()


def _create_archive(manifest: dict, skill_code: str = "pass") -> bytes:
    """Create a .nobla zip archive in memory and return bytes."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nobla-skill.json", json.dumps(manifest))
        zf.writestr("skill.py", skill_code)
    return buf.getvalue()


def _valid_manifest():
    return {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "category": "utilities",
    }


class TestValidateManifest:
    def test_valid_manifest(self, packager):
        result = packager.validate_manifest(_valid_manifest())
        assert result.valid is True
        assert result.issues == []

    def test_missing_name(self, packager):
        m = _valid_manifest()
        del m["name"]
        result = packager.validate_manifest(m)
        assert result.valid is False
        assert any("name" in i.lower() for i in result.issues)

    def test_missing_version(self, packager):
        m = _valid_manifest()
        del m["version"]
        result = packager.validate_manifest(m)
        assert result.valid is False

    def test_missing_description(self, packager):
        m = _valid_manifest()
        del m["description"]
        result = packager.validate_manifest(m)
        assert result.valid is False

    def test_invalid_semver(self, packager):
        m = _valid_manifest()
        m["version"] = "not-a-version"
        result = packager.validate_manifest(m)
        assert result.valid is False
        assert any("version" in i.lower() or "semver" in i.lower() for i in result.issues)

    def test_valid_semver_variants(self, packager):
        for v in ["0.1.0", "1.0.0", "10.20.30"]:
            m = _valid_manifest()
            m["version"] = v
            assert packager.validate_manifest(m).valid is True


class TestValidateArchive:
    def test_valid_archive(self, packager):
        data = _create_archive(_valid_manifest())
        result = packager.validate_archive(data)
        assert result.valid is True

    def test_invalid_zip(self, packager):
        result = packager.validate_archive(b"not a zip file")
        assert result.valid is False
        assert any("zip" in i.lower() or "archive" in i.lower() for i in result.issues)

    def test_missing_manifest_in_archive(self, packager):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("skill.py", "pass")
        result = packager.validate_archive(buf.getvalue())
        assert result.valid is False
        assert any("manifest" in i.lower() or "nobla-skill.json" in i.lower() for i in result.issues)

    def test_invalid_manifest_in_archive(self, packager):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("nobla-skill.json", "not json")
        result = packager.validate_archive(buf.getvalue())
        assert result.valid is False


class TestExtractManifest:
    def test_extracts_manifest(self, packager):
        manifest = _valid_manifest()
        data = _create_archive(manifest)
        result = packager.extract_manifest(data)
        assert result["name"] == "test-skill"
        assert result["version"] == "1.0.0"


class TestComputeHash:
    def test_hash_is_sha256_hex(self, packager):
        h = packager.compute_hash(b"hello world")
        assert len(h) == 64  # SHA-256 hex

    def test_same_input_same_hash(self, packager):
        h1 = packager.compute_hash(b"data")
        h2 = packager.compute_hash(b"data")
        assert h1 == h2

    def test_different_input_different_hash(self, packager):
        h1 = packager.compute_hash(b"data1")
        h2 = packager.compute_hash(b"data2")
        assert h1 != h2


class TestArchiveSize:
    def test_oversized_archive_rejected(self, packager):
        packager.max_archive_size_mb = 0.001  # ~1KB limit
        data = _create_archive(_valid_manifest(), skill_code="x" * 10000)
        result = packager.validate_archive(data)
        assert result.valid is False
        assert any("size" in i.lower() for i in result.issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_packager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SkillPackager**

Create `backend/nobla/marketplace/packager.py`:
- `SkillPackager.__init__(self, max_archive_size_mb=10)` — stores limit
- `validate_manifest(manifest: dict) -> PackageValidation` — checks required fields (name, version, description), validates SemVer with regex `r"^\d+\.\d+\.\d+$"`
- `validate_archive(data: bytes) -> PackageValidation` — checks is valid zip, size limit, contains `nobla-skill.json`, manifest is valid JSON, delegates to `validate_manifest()`
- `extract_manifest(data: bytes) -> dict` — unzip, read and parse `nobla-skill.json`
- `compute_hash(data: bytes) -> str` — `hashlib.sha256(data).hexdigest()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_marketplace_packager.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/marketplace/packager.py backend/tests/test_marketplace_packager.py
git commit -m "feat(5b2): add SkillPackager with archive/manifest validation"
```

---

## Task 3: MarketplaceRegistry

**Files:**
- Create: `backend/nobla/marketplace/registry.py`
- Test: `backend/tests/test_marketplace_registry.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_marketplace_registry.py`:

```python
"""Tests for Phase 5B.2 MarketplaceRegistry — CRUD, publish, verify, rate."""

from __future__ import annotations

import json
import uuid
import zipfile
import io
from datetime import datetime, timezone
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MarketplaceRegistry**

Create `backend/nobla/marketplace/registry.py`:
- In-memory stores: `_skills: dict[str, MarketplaceSkill]`, `_ratings: dict[str, list[SkillRating]]`, `_name_index: dict[str, str]` (name → skill_id)
- `publish()` — validate manifest (via packager), check name uniqueness, check author limit, scan, create MarketplaceSkill + SkillVersion, store, emit event
- `publish_version()` — validate, check version > current, scan, append version, update current_version, emit
- `get_skill()`, `get_all_skills()`, `unpublish()`
- `request_verification()`, `admin_review()`
- `submit_rating()` — upsert by (skill_id, user_id), recalculate avg_rating + rating_count
- `get_ratings()`
- `check_updates()` — compare installed versions against current_version

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_marketplace_registry.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/marketplace/registry.py backend/tests/test_marketplace_registry.py
git commit -m "feat(5b2): add MarketplaceRegistry with publish pipeline, ratings, versioning"
```

---

## Task 4: SkillDiscovery

**Files:**
- Create: `backend/nobla/marketplace/discovery.py`
- Test: `backend/tests/test_marketplace_discovery.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_marketplace_discovery.py` with tests for:
- `search(query="github")` — keyword match on name/description
- `search(category=SkillCategory.PRODUCTIVITY)` — filter by category
- `search(trust_tier=TrustTier.VERIFIED)` — filter by tier
- `search(tags=["git"])` — filter by tags
- `search(sort_by="install_count")` — sort ordering
- `search(page=2, page_size=1)` — pagination
- `search()` with no filters — returns all skills
- `get_pattern_recommendations(user_id)` — returns skills matching user patterns (mock PatternDetector)
- `get_similar_recommendations(user_id)` — returns skills similar to installed (mock SkillRuntime)
- `get_recommendations(user_id)` — returns both track types

Tests should populate the registry with 3-5 skills via `registry.publish()` to have data to search.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_discovery.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SkillDiscovery**

Create `backend/nobla/marketplace/discovery.py`:
- `SkillDiscovery.__init__(self, registry, pattern_detector=None, skill_runtime=None)`
- `search()` — get all skills from registry, apply filters (category, tags, trust_tier, source_format), keyword search (case-insensitive substring match on name + description + tags), sort, paginate, return `SearchResults`
- `get_pattern_recommendations(user_id)` — if pattern_detector is None return []. Get user's patterns, extract tool_sequences, find skills with matching category/tags. Return top 5.
- `get_similar_recommendations(user_id)` — if skill_runtime is None return []. Get installed skills, for each find marketplace skills in same category (exclude installed). Return top 5 by install_count.
- `get_recommendations(user_id)` — return dict with both tracks

Note: ChromaDB semantic search is deferred — keyword search is the initial implementation. The ChromaDB integration can be added later without changing the API.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_marketplace_discovery.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/marketplace/discovery.py backend/tests/test_marketplace_discovery.py
git commit -m "feat(5b2): add SkillDiscovery with keyword search and recommendations"
```

---

## Task 5: UsageTracker

**Files:**
- Create: `backend/nobla/marketplace/stats.py`
- Test: `backend/tests/test_marketplace_stats.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_marketplace_stats.py` with tests for:
- `on_skill_installed(event)` — increments install_count and active_users on the skill
- `on_skill_uninstalled(event)` — decrements active_users (not below 0)
- `on_tool_executed(event)` — increments success count when payload has matching skill_id
- `on_tool_failed(event)` — increments failure count
- `get_stats(skill_id)` — returns dict with install_count, active_users, success_rate
- Success rate calculation: successes / (successes + failures), 0.0 if no data
- Events without `skill_id` in payload are ignored

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_stats.py -v`
Expected: FAIL

- [ ] **Step 3: Implement UsageTracker**

Create `backend/nobla/marketplace/stats.py`:
- `UsageTracker.__init__(self, event_bus, registry)` — stores refs, `_exec_counts: dict[str, dict]` (`{skill_id: {"success": n, "failure": n}}`)
- Event handlers filter by `event.payload.get("skill_id")` — ignore if None
- `on_skill_installed` / `on_skill_uninstalled` — update skill's install_count/active_users on the registry object
- `on_tool_executed` / `on_tool_failed` — update `_exec_counts`, recalculate `success_rate` on the skill
- `get_stats(skill_id)` — return computed stats

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_marketplace_stats.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/marketplace/stats.py backend/tests/test_marketplace_stats.py
git commit -m "feat(5b2): add UsageTracker with event-driven skill stats"
```

---

## Task 6: MarketplaceService + Gateway Wiring

**Files:**
- Create: `backend/nobla/marketplace/service.py`
- Create: `backend/nobla/gateway/marketplace_handlers.py`
- Create: `backend/tests/test_marketplace_service.py`
- Create: `backend/tests/test_marketplace_handlers.py`
- Modify: `backend/nobla/gateway/lifespan.py`
- Modify: `backend/nobla/tools/executor.py`

- [ ] **Step 1: Write failing tests for MarketplaceService**

Create `backend/tests/test_marketplace_service.py` with tests for:
- `start()` subscribes to events (tool.executed, tool.failed, skill.installed, skill.uninstalled)
- `stop()` unsubscribes (stores (event_type, handler) tuples)
- `start()` skipped when disabled
- `install_skill()` delegates to skill_runtime.install(), emits `marketplace.skill.installed`
- `uninstall_skill()` delegates to skill_runtime.uninstall(), emits `marketplace.skill.uninstalled`
- Delegation: publish → registry, search → discovery, submit_rating → registry, check_updates → registry

- [ ] **Step 2: Write failing tests for handlers**

Create `backend/tests/test_marketplace_handlers.py` with FastAPI TestClient tests for:
- GET `/api/marketplace/search` returns 200
- GET `/api/marketplace/skills/{id}` returns skill detail
- POST `/api/marketplace/publish` with JSON body returns 200
- POST `/api/marketplace/skills/{id}/rate` with stars returns 200
- POST `/api/marketplace/skills/{id}/install` returns 200
- DELETE `/api/marketplace/skills/{id}/install` returns 200
- GET `/api/marketplace/updates` returns list
- GET `/api/marketplace/recommendations` returns dict
- GET `/api/marketplace/categories` returns category list
- DELETE `/api/marketplace/skills/{id}` (unpublish) returns 200
- POST `/api/marketplace/admin/review/{id}` returns 200

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_marketplace_service.py tests/test_marketplace_handlers.py -v`
Expected: FAIL

- [ ] **Step 4: Implement MarketplaceService**

Create `backend/nobla/marketplace/service.py`:
- Orchestrator with start/stop (subscriptions stored as `(event_type, handler)` tuples, unsubscribe via `event_bus.unsubscribe(event_type, handler)`)
- `install_skill()` — get skill from registry, resolve source (archive path or manifest), call `skill_runtime.install()`, emit `marketplace.skill.installed`
- `uninstall_skill()` — call `skill_runtime.uninstall()`, emit `marketplace.skill.uninstalled`
- Delegates all other operations to registry/discovery/stats

- [ ] **Step 5: Implement REST handlers**

Create `backend/nobla/gateway/marketplace_handlers.py`:
- FastAPI `APIRouter(prefix="/api/marketplace")`
- 15 routes matching spec Section 9
- Get service from `request.app.state.marketplace_service`

- [ ] **Step 6: Add skill_id to ToolExecutor event payload**

Modify `backend/nobla/tools/executor.py` — in the `_emit_tool_event` method, add:
```python
"skill_id": getattr(tool, 'skill_id', None),
```
to the payload dict. The `SkillToolBridge` already has a reference to the manifest; add a `skill_id` property that returns `self._manifest.id`.

- [ ] **Step 7: Wire into gateway lifespan**

Modify `backend/nobla/gateway/lifespan.py` — insert marketplace service block after the learning service block and before the multi-agent system block. Follow the pattern shown in spec Section 11.1. Add cleanup `if marketplace_service: await marketplace_service.stop()` before learning_service cleanup.

- [ ] **Step 8: Run all marketplace tests**

Run: `cd backend && python -m pytest tests/test_marketplace_*.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add backend/nobla/marketplace/service.py backend/nobla/gateway/marketplace_handlers.py backend/tests/test_marketplace_service.py backend/tests/test_marketplace_handlers.py backend/nobla/gateway/lifespan.py backend/nobla/tools/executor.py
git commit -m "feat(5b2): add MarketplaceService, REST API (15 routes), gateway wiring"
```

---

## Task 7: Flutter Models + Providers

**Files:**
- Create: `app/lib/features/marketplace/models/marketplace_models.dart`
- Create: `app/lib/features/marketplace/providers/marketplace_providers.dart`
- Test: `app/test/features/marketplace/marketplace_models_test.dart`

- [ ] **Step 1: Write failing tests**

Create `app/test/features/marketplace/marketplace_models_test.dart` with tests for:
- Enum value counts (PackageType 2, TrustTier 3, VerificationStatus 4)
- `MarketplaceSkill.fromJson` round-trip (all fields including tags list, nested versions)
- `SkillVersion.fromJson` with changelog and scan_passed
- `SkillRating.fromJson` with and without review
- `UpdateNotification.fromJson` with version comparison
- `SearchResults.fromJson` with items list and pagination fields

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/marketplace/marketplace_models_test.dart`
Expected: FAIL

- [ ] **Step 3: Implement Dart models**

Create `app/lib/features/marketplace/models/marketplace_models.dart`:
- Enums: `PackageType`, `TrustTier`, `VerificationStatus`
- Classes with `fromJson`/`toJson`: `SkillVersion`, `MarketplaceSkill`, `SkillRating`, `UpdateNotification`, `SearchResults`
- Follow existing pattern from learning_models.dart

- [ ] **Step 4: Implement providers**

Create `app/lib/features/marketplace/providers/marketplace_providers.dart`:
- `marketplaceSearchProvider` — FutureProvider.family (placeholder returning empty)
- `skillDetailProvider` — FutureProvider.family
- `skillRatingsProvider` — FutureProvider.family
- `updateListProvider` — FutureProvider
- `recommendationsProvider` — FutureProvider
- `categoryListProvider` — FutureProvider

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/marketplace/marketplace_models_test.dart`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/marketplace/ app/test/features/marketplace/marketplace_models_test.dart
git commit -m "feat(5b2): add Flutter marketplace models, providers, and model tests"
```

---

## Task 8: Flutter Widgets

**Files:**
- Create: `app/lib/features/marketplace/widgets/skill_card.dart`
- Create: `app/lib/features/marketplace/widgets/rating_widget.dart`
- Create: `app/lib/features/marketplace/widgets/version_list_widget.dart`
- Test: `app/test/features/marketplace/widgets_test.dart`

- [ ] **Step 1: Write failing tests**

Create `app/test/features/marketplace/widgets_test.dart` with tests for:
- `SkillCard` shows skill name, author, rating stars, install count, trust badge
- `SkillCard` Install button calls callback
- `SkillCard` shows "Installed" when already installed
- `RatingWidget` shows 5 stars
- `RatingWidget` tap on star calls onRate with correct value
- `RatingWidget` displays existing average rating
- `VersionListWidget` shows version numbers
- `VersionListWidget` expandable shows changelog

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/marketplace/widgets_test.dart`
Expected: FAIL

- [ ] **Step 3: Implement widgets**

- `skill_card.dart` — `SkillCard(skill, isInstalled, onInstall, onTap)`: Card with name, author, stars row, install count, TrustTier badge (colored Chip: green=verified, blue=official, grey=community), Install/Installed button
- `rating_widget.dart` — `RatingWidget(currentRating, onRate)`: Row of 5 tappable star icons, filled up to currentRating
- `version_list_widget.dart` — `VersionListWidget(versions)`: ListView of ExpansionTiles, each showing version number + date, expanding to changelog

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && flutter test test/features/marketplace/widgets_test.dart`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/marketplace/widgets/ app/test/features/marketplace/widgets_test.dart
git commit -m "feat(5b2): add Flutter marketplace widgets — skill card, rating, version list"
```

---

## Task 9: Flutter Screens + Router

**Files:**
- Create: `app/lib/features/marketplace/screens/marketplace_screen.dart`
- Create: `app/lib/features/marketplace/screens/skill_detail_screen.dart`
- Modify: `app/lib/core/routing/app_router.dart`
- Test: `app/test/features/marketplace/screens_test.dart`

- [ ] **Step 1: Write failing tests**

Create `app/test/features/marketplace/screens_test.dart` with tests for:
- `MarketplaceScreen` shows search bar
- `MarketplaceScreen` shows category filter chips
- `MarketplaceScreen` shows "No skills found" when empty
- `SkillDetailScreen` shows skill name and description
- `SkillDetailScreen` shows Install button
- `SkillDetailScreen` shows Versions and Ratings sections

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/marketplace/screens_test.dart`
Expected: FAIL

- [ ] **Step 3: Implement screens**

- `marketplace_screen.dart` — `MarketplaceScreen` ConsumerWidget: SearchBar at top, FilterChip row for categories, GridView.builder of SkillCards from marketplaceSearchProvider, two horizontal recommendation rows at top
- `skill_detail_screen.dart` — `SkillDetailScreen(skillId)` ConsumerWidget: header with name/author/badge/install, description + tags, stats row (4 cards), VersionListWidget, RatingWidget + reviews list

- [ ] **Step 4: Add routes to app_router.dart**

Add imports and two GoRoutes inside ShellRoute:
```dart
GoRoute(
  path: '/home/tools/marketplace',
  builder: (context, state) => const MarketplaceScreen(),
),
GoRoute(
  path: '/home/tools/marketplace/:id',
  builder: (context, state) => SkillDetailScreen(
    skillId: state.pathParameters['id']!,
  ),
),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/marketplace/`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/marketplace/screens/ app/lib/core/routing/app_router.dart app/test/features/marketplace/screens_test.dart
git commit -m "feat(5b2): add Flutter marketplace screens + router wiring"
```

---

## Task 10: Integration Verification + CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run all backend marketplace tests**

Run: `cd backend && python -m pytest tests/test_marketplace_*.py -v`
Expected: all PASS (~150-180 tests)

- [ ] **Step 2: Run all Flutter marketplace tests**

Run: `cd app && flutter test test/features/marketplace/`
Expected: all PASS (~50-70 tests)

- [ ] **Step 3: Run full backend test suite (regression check)**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/test_chat_flow.py --ignore=tests/test_consolidation.py --ignore=tests/test_extraction.py --ignore=tests/test_orchestrator.py --ignore=tests/test_routes.py --ignore=tests/test_security_integration.py --ignore=tests/test_websocket.py`
Expected: all existing tests + new marketplace tests PASS

- [ ] **Step 4: Run full Flutter test suite**

Run: `cd app && flutter test`
Expected: all existing tests + new marketplace tests PASS

- [ ] **Step 5: Verify line counts**

Run: `find backend/nobla/marketplace -name "*.py" -exec wc -l {} + | sort -rn`
Expected: all files < 750 lines

- [ ] **Step 6: Update CLAUDE.md**

Add Phase 5B.2 to Completed Phases, update test counts, add `marketplace/` to Project Structure, add Phase 5B.2 to sub-phases table.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 5B.2 Skills Marketplace completion"
```
