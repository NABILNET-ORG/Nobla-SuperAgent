"""Phase 5B.2 UsageTracker — event-driven skill stat aggregation."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class UsageTracker:
    def __init__(self, event_bus, registry) -> None:
        self._event_bus = event_bus
        self._registry = registry
        self._exec_counts: dict[str, dict[str, int]] = {}

    async def on_skill_installed(self, event) -> None:
        skill_id = event.payload.get("skill_id")
        if not skill_id:
            return
        skill = await self._registry.get_skill(skill_id)
        if skill is None:
            return
        skill.install_count += 1
        skill.active_users += 1

    async def on_skill_uninstalled(self, event) -> None:
        skill_id = event.payload.get("skill_id")
        if not skill_id:
            return
        skill = await self._registry.get_skill(skill_id)
        if skill is None:
            return
        skill.active_users = max(0, skill.active_users - 1)

    async def on_tool_executed(self, event) -> None:
        skill_id = event.payload.get("skill_id")
        if not skill_id:
            return
        counts = self._exec_counts.setdefault(skill_id, {"success": 0, "failure": 0})
        counts["success"] += 1
        await self._update_success_rate(skill_id)

    async def on_tool_failed(self, event) -> None:
        skill_id = event.payload.get("skill_id")
        if not skill_id:
            return
        counts = self._exec_counts.setdefault(skill_id, {"success": 0, "failure": 0})
        counts["failure"] += 1
        await self._update_success_rate(skill_id)

    async def _update_success_rate(self, skill_id: str) -> None:
        skill = await self._registry.get_skill(skill_id)
        if skill is None:
            return
        counts = self._exec_counts.get(skill_id, {"success": 0, "failure": 0})
        total = counts["success"] + counts["failure"]
        skill.success_rate = counts["success"] / total if total > 0 else 0.0

    async def get_stats(self, skill_id: str) -> dict:
        counts = self._exec_counts.get(skill_id, {"success": 0, "failure": 0})
        total = counts["success"] + counts["failure"]
        return {
            "success_count": counts["success"],
            "failure_count": counts["failure"],
            "success_rate": counts["success"] / total if total > 0 else 0.0,
        }
