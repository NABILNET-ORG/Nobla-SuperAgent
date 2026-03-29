"""Phase 5B.2 SkillDiscovery — keyword search, filters, recommendations."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from nobla.marketplace.models import MarketplaceSkill, TrustTier
from nobla.marketplace.registry import MarketplaceRegistry
from nobla.skills.models import SkillCategory, SkillSource

logger = structlog.get_logger(__name__)


@dataclass
class SearchResults:
    items: list[MarketplaceSkill]
    total: int
    page: int
    page_size: int


class SkillDiscovery:
    def __init__(
        self,
        registry: MarketplaceRegistry,
        pattern_detector=None,
        skill_runtime=None,
    ) -> None:
        self._registry = registry
        self._pattern_detector = pattern_detector
        self._skill_runtime = skill_runtime

    async def search(
        self,
        query: str | None = None,
        category: SkillCategory | None = None,
        tags: list[str] | None = None,
        trust_tier: TrustTier | None = None,
        source_format: SkillSource | None = None,
        sort_by: str = "relevance",
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResults:
        all_skills = await self._registry.get_all_skills()
        filtered = all_skills

        if category is not None:
            filtered = [s for s in filtered if s.category == category]

        if trust_tier is not None:
            filtered = [s for s in filtered if s.trust_tier == trust_tier]

        if source_format is not None:
            filtered = [s for s in filtered if s.source_format == source_format]

        if tags:
            tag_set = set(t.lower() for t in tags)
            filtered = [
                s for s in filtered
                if tag_set & set(t.lower() for t in s.tags)
            ]

        if query:
            q = query.lower()
            filtered = [
                s for s in filtered
                if q in s.name.lower()
                or q in s.description.lower()
                or any(q in t.lower() for t in s.tags)
            ]

        if sort_by == "install_count":
            filtered.sort(key=lambda s: s.install_count, reverse=True)
        elif sort_by == "avg_rating":
            filtered.sort(key=lambda s: s.avg_rating, reverse=True)
        elif sort_by == "created_at":
            filtered.sort(key=lambda s: s.created_at, reverse=True)

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]

        return SearchResults(
            items=page_items, total=total, page=page, page_size=page_size
        )

    async def get_pattern_recommendations(
        self, user_id: str
    ) -> list[MarketplaceSkill]:
        if self._pattern_detector is None:
            return []
        patterns = self._pattern_detector.get_user_patterns(user_id)
        if not patterns:
            return []

        all_skills = await self._registry.get_all_skills()
        tool_keywords: set[str] = set()
        for p in patterns:
            for tool_name in getattr(p, "tool_sequence", []):
                parts = tool_name.replace(".", " ").replace("_", " ").split()
                tool_keywords.update(w.lower() for w in parts)

        scored: list[tuple[float, MarketplaceSkill]] = []
        for skill in all_skills:
            skill_words = set()
            skill_words.update(t.lower() for t in skill.tags)
            cat_val = skill.category.value if hasattr(skill.category, "value") else str(skill.category)
            skill_words.add(cat_val.lower())
            overlap = len(tool_keywords & skill_words)
            if overlap > 0:
                confidence = max(
                    (getattr(p, "confidence", 0.5) for p in patterns), default=0.5
                )
                scored.append((overlap * confidence, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:5]]

    async def get_similar_recommendations(
        self, user_id: str
    ) -> list[MarketplaceSkill]:
        if self._skill_runtime is None:
            return []
        installed = self._skill_runtime.get_installed_skills()
        if not installed:
            return []

        installed_ids = {s.id for s in installed}
        installed_categories = {
            s.category for s in installed if hasattr(s, "category")
        }

        all_skills = await self._registry.get_all_skills()
        candidates = [
            s for s in all_skills
            if s.id not in installed_ids and s.category in installed_categories
        ]
        candidates.sort(key=lambda s: s.install_count, reverse=True)
        return candidates[:5]

    async def get_recommendations(
        self, user_id: str
    ) -> dict[str, list[MarketplaceSkill]]:
        return {
            "based_on_patterns": await self.get_pattern_recommendations(user_id),
            "similar_to_installed": await self.get_similar_recommendations(user_id),
        }
