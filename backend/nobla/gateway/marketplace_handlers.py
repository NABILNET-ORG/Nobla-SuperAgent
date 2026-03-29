"""Phase 5B.2 REST API for Skills Marketplace — 15 routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

marketplace_router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _get_service(request: Request):
    svc = getattr(request.app.state, "marketplace_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Marketplace service not available")
    return svc


# --- Pydantic request/response schemas ---

class PublishRequest(BaseModel):
    author_id: str
    author_name: str
    manifest: dict
    archive_data: Optional[str] = None  # base64-encoded for archive, None for pointer

class RateRequest(BaseModel):
    user_id: str
    stars: int
    review: Optional[str] = None

class InstallRequest(BaseModel):
    user_id: str

class UninstallRequest(BaseModel):
    user_id: str

class UpdateCheckRequest(BaseModel):
    installed: dict[str, str]

class VersionPublishRequest(BaseModel):
    manifest: dict
    archive_data: Optional[str] = None

class AdminReviewRequest(BaseModel):
    approved: bool
    reason: Optional[str] = None


# --- Routes ---

@marketplace_router.get("/search")
async def search_skills(
    request: Request,
    query: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    trust_tier: Optional[str] = None,
    source_format: Optional[str] = None,
    sort_by: str = "relevance",
    page: int = 1,
    page_size: int = 20,
):
    svc = _get_service(request)
    from nobla.marketplace.models import TrustTier
    from nobla.skills.models import SkillCategory, SkillSource

    kwargs: dict = {"sort_by": sort_by, "page": page, "page_size": page_size}
    if query:
        kwargs["query"] = query
    if category:
        try:
            kwargs["category"] = SkillCategory(category)
        except ValueError:
            raise HTTPException(400, f"Invalid category: {category}")
    if tags:
        kwargs["tags"] = [t.strip() for t in tags.split(",")]
    if trust_tier:
        try:
            kwargs["trust_tier"] = TrustTier(trust_tier)
        except ValueError:
            raise HTTPException(400, f"Invalid trust tier: {trust_tier}")
    if source_format:
        try:
            kwargs["source_format"] = SkillSource(source_format)
        except ValueError:
            raise HTTPException(400, f"Invalid source format: {source_format}")

    results = await svc.search(**kwargs)
    return {
        "items": [_skill_to_dict(s) for s in results.items],
        "total": results.total,
        "page": results.page,
        "page_size": results.page_size,
    }


@marketplace_router.get("/skills/{skill_id}")
async def get_skill_detail(request: Request, skill_id: str):
    svc = _get_service(request)
    skill = await svc.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return _skill_to_dict(skill)


@marketplace_router.get("/skills/{skill_id}/versions")
async def get_skill_versions(request: Request, skill_id: str):
    svc = _get_service(request)
    versions = await svc.get_versions(skill_id)
    return [
        {
            "version": v.version,
            "changelog": v.changelog,
            "package_hash": v.package_hash,
            "min_nobla_version": v.min_nobla_version,
            "published_at": v.published_at.isoformat(),
            "scan_passed": v.scan_passed,
        }
        for v in versions
    ]


@marketplace_router.get("/skills/{skill_id}/ratings")
async def get_skill_ratings(request: Request, skill_id: str):
    svc = _get_service(request)
    ratings = await svc.get_ratings(skill_id)
    return [
        {
            "id": r.id,
            "skill_id": r.skill_id,
            "user_id": r.user_id,
            "stars": r.stars,
            "review": r.review,
            "created_at": r.created_at.isoformat(),
        }
        for r in ratings
    ]


@marketplace_router.post("/publish")
async def publish_skill(request: Request, body: PublishRequest):
    svc = _get_service(request)
    import base64
    archive_bytes = None
    if body.archive_data:
        archive_bytes = base64.b64decode(body.archive_data)
    try:
        skill = await svc.publish(
            body.author_id, body.author_name, body.manifest, archive_bytes
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _skill_to_dict(skill)


@marketplace_router.post("/skills/{skill_id}/versions")
async def publish_version(request: Request, skill_id: str, body: VersionPublishRequest):
    svc = _get_service(request)
    import base64
    archive_bytes = None
    if body.archive_data:
        archive_bytes = base64.b64decode(body.archive_data)
    try:
        version = await svc.publish_version(skill_id, body.manifest, archive_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"version": version.version, "published_at": version.published_at.isoformat()}


@marketplace_router.post("/skills/{skill_id}/rate")
async def rate_skill(request: Request, skill_id: str, body: RateRequest):
    svc = _get_service(request)
    try:
        rating = await svc.submit_rating(skill_id, body.user_id, body.stars, body.review)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": rating.id, "stars": rating.stars}


@marketplace_router.post("/skills/{skill_id}/install")
async def install_skill(request: Request, skill_id: str, body: InstallRequest):
    svc = _get_service(request)
    try:
        await svc.install_skill(skill_id, body.user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "installed"}


@marketplace_router.delete("/skills/{skill_id}/install")
async def uninstall_skill(request: Request, skill_id: str, user_id: str = "default"):
    svc = _get_service(request)
    await svc.uninstall_skill(skill_id, user_id)
    return {"status": "uninstalled"}


@marketplace_router.get("/updates")
async def check_updates(request: Request):
    svc = _get_service(request)
    updates = await svc.check_updates({})
    return [
        {
            "skill_id": u.skill_id,
            "skill_name": u.skill_name,
            "installed_version": u.installed_version,
            "latest_version": u.latest_version,
            "changelog": u.changelog,
        }
        for u in updates
    ]


@marketplace_router.get("/recommendations")
async def get_recommendations(request: Request, user_id: str = "default"):
    svc = _get_service(request)
    recs = await svc.get_recommendations(user_id)
    return {
        k: [_skill_to_dict(s) for s in v]
        for k, v in recs.items()
    }


@marketplace_router.get("/categories")
async def list_categories(request: Request):
    svc = _get_service(request)
    cats = await svc.get_categories()
    return [{"category": k, "count": v} for k, v in cats.items()]


@marketplace_router.delete("/skills/{skill_id}")
async def unpublish_skill(request: Request, skill_id: str):
    svc = _get_service(request)
    await svc.unpublish(skill_id)
    return {"status": "unpublished"}


@marketplace_router.post("/skills/{skill_id}/request-verification")
async def request_verification(request: Request, skill_id: str):
    svc = _get_service(request)
    try:
        await svc.request_verification(skill_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "pending"}


@marketplace_router.post("/admin/review/{skill_id}")
async def admin_review(request: Request, skill_id: str, body: AdminReviewRequest):
    svc = _get_service(request)
    try:
        await svc.admin_review(skill_id, body.approved, body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "approved" if body.approved else "rejected"}


def _skill_to_dict(s) -> dict:
    cat = s.category.value if hasattr(s.category, "value") else str(s.category)
    src = s.source_format.value if hasattr(s.source_format, "value") else str(s.source_format)
    return {
        "id": s.id,
        "name": s.name,
        "display_name": s.display_name,
        "description": s.description,
        "author_id": s.author_id,
        "author_name": s.author_name,
        "category": cat,
        "tags": s.tags,
        "source_format": src,
        "package_type": s.package_type.value,
        "source_url": s.source_url,
        "current_version": s.current_version,
        "trust_tier": s.trust_tier.value,
        "verification_status": s.verification_status.value,
        "security_scan_passed": s.security_scan_passed,
        "install_count": s.install_count,
        "active_users": s.active_users,
        "avg_rating": s.avg_rating,
        "rating_count": s.rating_count,
        "success_rate": s.success_rate,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }
