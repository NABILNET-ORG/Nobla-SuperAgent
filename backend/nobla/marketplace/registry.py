"""Phase 5B.2 MarketplaceRegistry — CRUD, publish pipeline, verification, ratings."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog

from nobla.events.models import NoblaEvent
from nobla.marketplace.models import (
    MarketplaceSkill,
    PackageType,
    PackageValidation,
    SkillRating,
    SkillVersion,
    TrustTier,
    UpdateNotification,
    VerificationStatus,
)
from nobla.marketplace.packager import SkillPackager
from nobla.skills.models import SkillCategory, SkillSource

logger = structlog.get_logger(__name__)

_SOURCE_MAP = {
    "nobla": SkillSource.NOBLA,
    "mcp": SkillSource.MCP,
    "openclaw": SkillSource.OPENCLAW,
    "claude": SkillSource.CLAUDE,
    "langchain": SkillSource.LANGCHAIN,
}

_CATEGORY_MAP = {c.value: c for c in SkillCategory}


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


class MarketplaceRegistry:
    def __init__(
        self,
        event_bus,
        packager: SkillPackager,
        security_scanner,
        max_skills_per_author: int = 50,
    ) -> None:
        self._event_bus = event_bus
        self._packager = packager
        self._security_scanner = security_scanner
        self._max_skills_per_author = max_skills_per_author
        self._skills: dict[str, MarketplaceSkill] = {}
        self._name_index: dict[str, str] = {}
        self._ratings: dict[str, list[SkillRating]] = {}

    async def publish(
        self,
        author_id: str,
        author_name: str,
        manifest: dict,
        archive_data: bytes | None,
    ) -> MarketplaceSkill:
        validation = self._packager.validate_manifest(manifest)
        if not validation.valid:
            raise ValueError(f"Invalid manifest: {validation.issues}")

        name = manifest["name"]
        if name in self._name_index:
            raise ValueError(f"Skill '{name}' already exists")

        author_count = sum(
            1 for s in self._skills.values() if s.author_id == author_id
        )
        if author_count >= self._max_skills_per_author:
            raise ValueError(
                f"Author has reached the limit of {self._max_skills_per_author} skills"
            )

        scan_data = archive_data or json.dumps(manifest).encode()
        scan_result = await self._security_scanner.scan(scan_data)
        if not scan_result.passed:
            raise ValueError(f"security scan failed: {scan_result.issues}")

        now = datetime.now(timezone.utc)
        package_hash = self._packager.compute_hash(scan_data)
        source_str = manifest.get("source", "nobla")
        has_archive = archive_data is not None
        version = SkillVersion(
            version=manifest["version"],
            changelog=manifest.get("changelog", "Initial release"),
            package_hash=package_hash,
            min_nobla_version=manifest.get("min_nobla_version"),
            published_at=now,
            scan_passed=True,
        )
        skill = MarketplaceSkill(
            id=str(uuid.uuid4()),
            name=name,
            display_name=manifest.get("display_name", name),
            description=manifest["description"],
            author_id=author_id,
            author_name=author_name,
            category=_CATEGORY_MAP.get(
                manifest.get("category", "utilities"), SkillCategory.UTILITIES
            ),
            tags=manifest.get("tags", []),
            source_format=_SOURCE_MAP.get(source_str, SkillSource.NOBLA),
            package_type=PackageType.ARCHIVE if has_archive else PackageType.POINTER,
            source_url=manifest.get("source_url"),
            current_version=manifest["version"],
            versions=[version],
            trust_tier=TrustTier.COMMUNITY,
            verification_status=VerificationStatus.NONE,
            security_scan_passed=True,
            install_count=0,
            active_users=0,
            avg_rating=0.0,
            rating_count=0,
            success_rate=0.0,
            created_at=now,
            updated_at=now,
        )

        self._skills[skill.id] = skill
        self._name_index[name] = skill.id
        self._ratings[skill.id] = []

        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.skill.published",
                source="marketplace.registry",
                payload={"skill_id": skill.id, "name": name},
            )
        )
        logger.info("skill_published", skill_id=skill.id, name=name)
        return skill

    async def publish_version(
        self,
        skill_id: str,
        manifest: dict,
        archive_data: bytes | None,
    ) -> SkillVersion:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")

        validation = self._packager.validate_manifest(manifest)
        if not validation.valid:
            raise ValueError(f"Invalid manifest: {validation.issues}")

        new_ver = manifest["version"]
        if _parse_version_tuple(new_ver) <= _parse_version_tuple(skill.current_version):
            raise ValueError(
                f"New version {new_ver} must be greater than current {skill.current_version}"
            )

        scan_data = archive_data or json.dumps(manifest).encode()
        scan_result = await self._security_scanner.scan(scan_data)
        if not scan_result.passed:
            raise ValueError(f"security scan failed: {scan_result.issues}")

        now = datetime.now(timezone.utc)
        version = SkillVersion(
            version=new_ver,
            changelog=manifest.get("changelog", ""),
            package_hash=self._packager.compute_hash(scan_data),
            min_nobla_version=manifest.get("min_nobla_version"),
            published_at=now,
            scan_passed=True,
        )
        skill.versions.append(version)
        skill.current_version = new_ver
        skill.updated_at = now

        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.skill.updated",
                source="marketplace.registry",
                payload={"skill_id": skill_id, "new_version": new_ver},
            )
        )
        logger.info("skill_version_published", skill_id=skill_id, version=new_ver)
        return version

    async def get_skill(self, skill_id: str) -> MarketplaceSkill | None:
        return self._skills.get(skill_id)

    async def get_all_skills(self) -> list[MarketplaceSkill]:
        return list(self._skills.values())

    async def unpublish(self, skill_id: str) -> None:
        skill = self._skills.pop(skill_id, None)
        if skill:
            self._name_index.pop(skill.name, None)
            self._ratings.pop(skill_id, None)

    async def request_verification(self, skill_id: str) -> None:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        skill.verification_status = VerificationStatus.PENDING
        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.verification.requested",
                source="marketplace.registry",
                payload={"skill_id": skill_id},
            )
        )

    async def admin_review(
        self, skill_id: str, approved: bool, reason: str | None
    ) -> None:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        if approved:
            skill.trust_tier = TrustTier.VERIFIED
            skill.verification_status = VerificationStatus.APPROVED
            event_type = "marketplace.verification.approved"
        else:
            skill.verification_status = VerificationStatus.REJECTED
            event_type = "marketplace.verification.rejected"
        await self._event_bus.emit(
            NoblaEvent(
                event_type=event_type,
                source="marketplace.registry",
                payload={"skill_id": skill_id, "reason": reason},
            )
        )

    async def submit_rating(
        self, skill_id: str, user_id: str, stars: int, review: str | None
    ) -> SkillRating:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")

        now = datetime.now(timezone.utc)
        ratings = self._ratings.setdefault(skill_id, [])
        existing = next((r for r in ratings if r.user_id == user_id), None)
        if existing:
            existing.stars = stars
            existing.review = review
            existing.updated_at = now
            rating = existing
        else:
            rating = SkillRating(
                id=str(uuid.uuid4()),
                skill_id=skill_id,
                user_id=user_id,
                stars=stars,
                review=review,
                created_at=now,
                updated_at=now,
            )
            ratings.append(rating)

        skill.rating_count = len(ratings)
        skill.avg_rating = sum(r.stars for r in ratings) / len(ratings)

        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.skill.rated",
                source="marketplace.registry",
                payload={"skill_id": skill_id, "user_id": user_id, "stars": stars},
            )
        )
        return rating

    async def get_ratings(self, skill_id: str) -> list[SkillRating]:
        return self._ratings.get(skill_id, [])

    async def check_updates(
        self, installed: dict[str, str]
    ) -> list[UpdateNotification]:
        updates: list[UpdateNotification] = []
        for name, installed_ver in installed.items():
            skill_id = self._name_index.get(name)
            if skill_id is None:
                continue
            skill = self._skills[skill_id]
            if _parse_version_tuple(skill.current_version) > _parse_version_tuple(
                installed_ver
            ):
                latest_v = skill.versions[-1]
                updates.append(
                    UpdateNotification(
                        skill_id=skill.id,
                        skill_name=name,
                        installed_version=installed_ver,
                        latest_version=skill.current_version,
                        changelog=latest_v.changelog,
                        published_at=latest_v.published_at,
                    )
                )
        return updates

    async def get_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for skill in self._skills.values():
            cat = skill.category.value if hasattr(skill.category, "value") else str(skill.category)
            counts[cat] = counts.get(cat, 0) + 1
        return counts
