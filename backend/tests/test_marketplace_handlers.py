"""Tests for Phase 5B.2 marketplace REST handlers."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nobla.gateway.marketplace_handlers import marketplace_router
from nobla.marketplace.discovery import SearchResults
from nobla.marketplace.models import (
    MarketplaceSkill,
    PackageType,
    SkillRating,
    SkillVersion,
    TrustTier,
    UpdateNotification,
    VerificationStatus,
)
from nobla.skills.models import SkillCategory, SkillSource

from datetime import datetime, timezone


def _make_skill(**overrides) -> MarketplaceSkill:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="skill-1",
        name="test-skill",
        display_name="Test Skill",
        description="A test skill",
        author_id="a1",
        author_name="Author",
        category=SkillCategory.UTILITIES,
        tags=["test"],
        source_format=SkillSource.NOBLA,
        package_type=PackageType.ARCHIVE,
        source_url=None,
        current_version="1.0.0",
        versions=[],
        trust_tier=TrustTier.COMMUNITY,
        verification_status=VerificationStatus.NONE,
        security_scan_passed=True,
        install_count=10,
        active_users=5,
        avg_rating=4.0,
        rating_count=3,
        success_rate=0.95,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return MarketplaceSkill(**defaults)


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.search = AsyncMock(return_value=SearchResults(items=[], total=0, page=1, page_size=20))
    svc.get_skill = AsyncMock(return_value=_make_skill())
    svc.get_versions = AsyncMock(return_value=[])
    svc.get_ratings = AsyncMock(return_value=[])
    svc.publish = AsyncMock(return_value=_make_skill())
    svc.publish_version = AsyncMock(return_value=SkillVersion(
        version="1.1.0", changelog="fix", package_hash="abc",
        min_nobla_version=None, published_at=datetime.now(timezone.utc), scan_passed=True,
    ))
    svc.submit_rating = AsyncMock(return_value=SkillRating(
        id="r1", skill_id="s1", user_id="u1", stars=5, review=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))
    svc.install_skill = AsyncMock()
    svc.uninstall_skill = AsyncMock()
    svc.check_updates = AsyncMock(return_value=[])
    svc.get_recommendations = AsyncMock(return_value={
        "based_on_patterns": [], "similar_to_installed": []
    })
    svc.get_categories = AsyncMock(return_value={"utilities": 3})
    svc.unpublish = AsyncMock()
    svc.request_verification = AsyncMock()
    svc.admin_review = AsyncMock()
    return svc


@pytest.fixture
def client(service):
    app = FastAPI()
    app.state.marketplace_service = service
    app.include_router(marketplace_router)
    return TestClient(app)


class TestSearchRoute:
    def test_search_returns_200(self, client):
        resp = client.get("/api/marketplace/search")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_search_with_params(self, client, service):
        skill = _make_skill()
        service.search = AsyncMock(
            return_value=SearchResults(items=[skill], total=1, page=1, page_size=20)
        )
        resp = client.get("/api/marketplace/search?query=test&category=utilities")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestSkillDetailRoute:
    def test_get_skill_detail(self, client):
        resp = client.get("/api/marketplace/skills/skill-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-skill"

    def test_skill_not_found(self, client, service):
        service.get_skill = AsyncMock(return_value=None)
        resp = client.get("/api/marketplace/skills/bad-id")
        assert resp.status_code == 404


class TestVersionsRoute:
    def test_get_versions(self, client):
        resp = client.get("/api/marketplace/skills/skill-1/versions")
        assert resp.status_code == 200


class TestRatingsRoute:
    def test_get_ratings(self, client):
        resp = client.get("/api/marketplace/skills/skill-1/ratings")
        assert resp.status_code == 200

    def test_rate_skill(self, client):
        resp = client.post(
            "/api/marketplace/skills/skill-1/rate",
            json={"user_id": "u1", "stars": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["stars"] == 5


class TestPublishRoute:
    def test_publish_with_manifest(self, client):
        resp = client.post("/api/marketplace/publish", json={
            "author_id": "a1",
            "author_name": "Author",
            "manifest": {"name": "x", "version": "1.0.0", "description": "test"},
        })
        assert resp.status_code == 200

    def test_publish_version(self, client):
        resp = client.post("/api/marketplace/skills/skill-1/versions", json={
            "manifest": {"name": "x", "version": "1.1.0", "description": "test"},
        })
        assert resp.status_code == 200


class TestInstallRoutes:
    def test_install_skill(self, client):
        resp = client.post(
            "/api/marketplace/skills/skill-1/install",
            json={"user_id": "u1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "installed"

    def test_uninstall_skill(self, client):
        resp = client.delete("/api/marketplace/skills/skill-1/install?user_id=u1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "uninstalled"


class TestUpdatesRoute:
    def test_check_updates(self, client):
        resp = client.get("/api/marketplace/updates")
        assert resp.status_code == 200


class TestRecommendationsRoute:
    def test_get_recommendations(self, client):
        resp = client.get("/api/marketplace/recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert "based_on_patterns" in data
        assert "similar_to_installed" in data


class TestCategoriesRoute:
    def test_list_categories(self, client):
        resp = client.get("/api/marketplace/categories")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestUnpublishRoute:
    def test_unpublish(self, client):
        resp = client.delete("/api/marketplace/skills/skill-1")
        assert resp.status_code == 200


class TestVerificationRoutes:
    def test_request_verification(self, client):
        resp = client.post("/api/marketplace/skills/skill-1/request-verification")
        assert resp.status_code == 200

    def test_admin_review(self, client):
        resp = client.post("/api/marketplace/admin/review/skill-1", json={
            "approved": True, "reason": None,
        })
        assert resp.status_code == 200
