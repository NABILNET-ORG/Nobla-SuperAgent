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
