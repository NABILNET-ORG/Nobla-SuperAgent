"""Phase 5B.2 MarketplaceService — orchestrator, install/uninstall, wiring."""

from __future__ import annotations

import structlog

from nobla.events.models import NoblaEvent
from nobla.marketplace.discovery import SearchResults, SkillDiscovery
from nobla.marketplace.models import (
    MarketplaceSkill,
    SkillRating,
    UpdateNotification,
)
from nobla.marketplace.registry import MarketplaceRegistry
from nobla.marketplace.stats import UsageTracker

logger = structlog.get_logger(__name__)


class MarketplaceService:
    def __init__(
        self,
        event_bus,
        registry: MarketplaceRegistry,
        discovery: SkillDiscovery,
        usage_tracker: UsageTracker,
        skill_runtime=None,
        settings=None,
    ) -> None:
        self._event_bus = event_bus
        self._registry = registry
        self._discovery = discovery
        self._usage_tracker = usage_tracker
        self._skill_runtime = skill_runtime
        self._settings = settings
        self._subscriptions: list[tuple[str, object]] = []
        self._started = False

    async def start(self) -> None:
        if self._settings and not self._settings.enabled:
            logger.info("marketplace_service_disabled")
            return

        subs = [
            ("tool.executed", self._usage_tracker.on_tool_executed),
            ("tool.failed", self._usage_tracker.on_tool_failed),
            ("skill.installed", self._usage_tracker.on_skill_installed),
            ("skill.uninstalled", self._usage_tracker.on_skill_uninstalled),
        ]
        for event_type, handler in subs:
            self._event_bus.subscribe(event_type, handler)
            self._subscriptions.append((event_type, handler))

        self._started = True
        logger.info("marketplace_service_started")

    async def stop(self) -> None:
        for event_type, handler in self._subscriptions:
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        self._started = False
        logger.info("marketplace_service_stopped")

    async def publish(
        self, author_id: str, author_name: str, manifest: dict,
        archive_data: bytes | None,
    ) -> MarketplaceSkill:
        return await self._registry.publish(
            author_id, author_name, manifest, archive_data
        )

    async def search(self, **kwargs) -> SearchResults:
        return await self._discovery.search(**kwargs)

    async def get_skill(self, skill_id: str) -> MarketplaceSkill | None:
        return await self._registry.get_skill(skill_id)

    async def get_versions(self, skill_id: str) -> list:
        skill = await self._registry.get_skill(skill_id)
        return skill.versions if skill else []

    async def install_skill(self, skill_id: str, user_id: str) -> None:
        skill = await self._registry.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        if self._skill_runtime:
            await self._skill_runtime.install(skill_id)
        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.skill.installed",
                source="marketplace.service",
                payload={
                    "skill_id": skill_id,
                    "user_id": user_id,
                    "version": skill.current_version,
                },
            )
        )

    async def uninstall_skill(self, skill_id: str, user_id: str) -> None:
        if self._skill_runtime:
            await self._skill_runtime.uninstall(skill_id)
        await self._event_bus.emit(
            NoblaEvent(
                event_type="marketplace.skill.uninstalled",
                source="marketplace.service",
                payload={"skill_id": skill_id, "user_id": user_id},
            )
        )

    async def upgrade_skill(self, skill_id: str, version: str) -> None:
        if self._skill_runtime:
            await self._skill_runtime.upgrade(skill_id)

    async def submit_rating(
        self, skill_id: str, user_id: str, stars: int, review: str | None
    ) -> SkillRating:
        return await self._registry.submit_rating(skill_id, user_id, stars, review)

    async def get_ratings(self, skill_id: str) -> list[SkillRating]:
        return await self._registry.get_ratings(skill_id)

    async def check_updates(
        self, installed: dict[str, str]
    ) -> list[UpdateNotification]:
        return await self._registry.check_updates(installed)

    async def get_recommendations(self, user_id: str) -> dict:
        return await self._discovery.get_recommendations(user_id)

    async def get_categories(self) -> dict[str, int]:
        return await self._registry.get_categories()

    async def request_verification(self, skill_id: str) -> None:
        await self._registry.request_verification(skill_id)

    async def admin_review(
        self, skill_id: str, approved: bool, reason: str | None
    ) -> None:
        await self._registry.admin_review(skill_id, approved, reason)

    async def publish_version(
        self, skill_id: str, manifest: dict, archive_data: bytes | None
    ):
        return await self._registry.publish_version(skill_id, manifest, archive_data)

    async def unpublish(self, skill_id: str) -> None:
        await self._registry.unpublish(skill_id)
