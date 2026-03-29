"""Phase 5B.2 marketplace data models and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PackageType(str, Enum):
    ARCHIVE = "archive"
    POINTER = "pointer"


class TrustTier(str, Enum):
    COMMUNITY = "community"
    VERIFIED = "verified"
    OFFICIAL = "official"


class VerificationStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class PackageValidation:
    valid: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class SkillVersion:
    version: str
    changelog: str
    package_hash: str
    min_nobla_version: str | None
    published_at: datetime
    scan_passed: bool


@dataclass
class SkillRating:
    id: str
    skill_id: str
    user_id: str
    stars: int
    review: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UpdateNotification:
    skill_id: str
    skill_name: str
    installed_version: str
    latest_version: str
    changelog: str
    published_at: datetime


@dataclass
class MarketplaceSkill:
    id: str
    name: str
    display_name: str
    description: str
    author_id: str
    author_name: str
    category: object  # SkillCategory
    tags: list[str]
    source_format: object  # SkillSource
    package_type: PackageType
    source_url: str | None
    current_version: str
    versions: list[SkillVersion]
    trust_tier: TrustTier
    verification_status: VerificationStatus
    security_scan_passed: bool
    install_count: int
    active_users: int
    avg_rating: float
    rating_count: int
    success_rate: float
    created_at: datetime
    updated_at: datetime
