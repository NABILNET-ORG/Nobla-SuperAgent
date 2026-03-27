"""Skill runtime — install, uninstall, enable, disable, upgrade skills.

Spec reference: Phase 5-Foundation §4.3 — Skill Runtime.

Install is transactional (all-or-nothing):
1. Adapter detects format, parses manifest
2. Security scan (SkillSecurityScanner)
3. Sandbox dry-run with 10-SECOND HARD TIMEOUT (20s for MCP) — reject if exceeded
4. Persist to installed_skills store
5. Wrap in SkillToolBridge, register via ToolRegistry.register()
6. Emit skill.installed event
7. Skill defaults to enabled: false

On any failure after step 4: rollback (remove from store).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nobla.events.models import NoblaEvent
from nobla.skills.adapter import UniversalSkillAdapter
from nobla.skills.bridge import SkillToolBridge
from nobla.skills.models import NoblaSkill, SkillManifest

logger = logging.getLogger(__name__)

# Dry-run timeouts (seconds)
DEFAULT_DRY_RUN_TIMEOUT = 10
MCP_DRY_RUN_TIMEOUT = 20


class SkillRuntime:
    """Manages the full lifecycle of installed skills.

    Dependencies are injected at construction. The event_bus and security_scanner
    are optional to allow lightweight testing.
    """

    def __init__(
        self,
        tool_registry: Any,  # ToolRegistry — avoid circular import
        adapter: UniversalSkillAdapter,
        event_bus: Any | None = None,  # NoblaEventBus
        security_scanner: Any | None = None,  # SkillSecurityScanner
    ) -> None:
        self._registry = tool_registry
        self._adapter = adapter
        self._event_bus = event_bus
        self._scanner = security_scanner
        # In-memory store for Phase 5-Foundation (PostgreSQL in 5A)
        self._installed: dict[str, SkillManifest] = {}
        self._skills: dict[str, NoblaSkill] = {}
        self._bridges: dict[str, SkillToolBridge] = {}

    # ── Install ────────────────────────────────────────────

    async def install(self, source: str | dict | Path) -> SkillManifest:
        """Transactional skill installation — all-or-nothing.

        Returns the installed SkillManifest (with enabled=False).
        Raises on any failure and rolls back partial state.
        """
        # Step 1: Detect format and import
        skill = await self._adapter.import_skill(source)
        manifest = skill.manifest
        skill_id = manifest.id

        if skill_id in self._installed:
            raise ValueError(f"Skill already installed: {skill_id}")

        # Step 2: Security scan (if scanner available)
        if self._scanner is not None:
            scan_result = await self._scanner.scan(manifest)
            if not scan_result.passed:
                raise SecurityError(
                    f"Skill '{manifest.name}' failed security scan: "
                    f"{', '.join(scan_result.issues)}"
                )

        # Step 3: Dry-run skipped in Phase 5-Foundation (needs sandbox)
        # Will be wired when SandboxManager integration is ready

        # Step 4: Persist to store
        manifest.enabled = False  # Always false — no exceptions
        self._installed[skill_id] = manifest
        self._skills[skill_id] = skill

        # Step 5: Wrap in bridge and register
        bridge = SkillToolBridge(skill)
        try:
            self._registry.register(bridge)
        except Exception:
            # Rollback store on registration failure
            del self._installed[skill_id]
            del self._skills[skill_id]
            raise

        self._bridges[skill_id] = bridge

        # Step 6: Emit event
        await self._emit_event(
            "skill.installed",
            {"skill_id": skill_id, "name": manifest.name, "source": manifest.source.value},
        )

        logger.info("Installed skill '%s' (%s)", manifest.name, skill_id)
        return manifest

    # ── Uninstall ──────────────────────────────────────────

    async def uninstall(self, skill_id: str) -> None:
        """Remove an installed skill."""
        if skill_id not in self._installed:
            raise KeyError(f"Skill not installed: {skill_id}")

        manifest = self._installed[skill_id]

        # Unregister from tool registry
        self._registry.unregister(manifest.name)

        # Remove from stores
        del self._installed[skill_id]
        self._skills.pop(skill_id, None)
        self._bridges.pop(skill_id, None)

        await self._emit_event(
            "skill.uninstalled",
            {"skill_id": skill_id, "name": manifest.name},
        )
        logger.info("Uninstalled skill '%s'", manifest.name)

    # ── Enable / Disable ───────────────────────────────────

    async def enable(self, skill_id: str) -> None:
        """Enable an installed skill for execution."""
        manifest = self._get_manifest(skill_id)
        manifest.enabled = True
        await self._emit_event(
            "skill.enabled", {"skill_id": skill_id, "name": manifest.name}
        )
        logger.info("Enabled skill '%s'", manifest.name)

    async def disable(self, skill_id: str) -> None:
        """Disable a skill (stays installed but won't execute)."""
        manifest = self._get_manifest(skill_id)
        manifest.enabled = False
        await self._emit_event(
            "skill.disabled", {"skill_id": skill_id, "name": manifest.name}
        )
        logger.info("Disabled skill '%s'", manifest.name)

    # ── Query ──────────────────────────────────────────────

    async def list_installed(self) -> list[SkillManifest]:
        """List all installed skill manifests."""
        return list(self._installed.values())

    async def get_manifest(self, skill_id: str) -> SkillManifest:
        """Get manifest for an installed skill."""
        return self._get_manifest(skill_id)

    def is_installed(self, skill_id: str) -> bool:
        return skill_id in self._installed

    def is_enabled(self, skill_id: str) -> bool:
        manifest = self._installed.get(skill_id)
        return manifest.enabled if manifest else False

    # ── Upgrade ────────────────────────────────────────────

    async def upgrade(self, skill_id: str, source: str | dict | Path) -> SkillManifest:
        """Upgrade an installed skill to a new version.

        Uninstalls the old version and installs the new one.
        """
        if skill_id not in self._installed:
            raise KeyError(f"Skill not installed: {skill_id}")

        was_enabled = self._installed[skill_id].enabled
        await self.uninstall(skill_id)
        manifest = await self.install(source)

        if was_enabled:
            await self.enable(manifest.id)

        return manifest

    # ── Internal ───────────────────────────────────────────

    def _get_manifest(self, skill_id: str) -> SkillManifest:
        manifest = self._installed.get(skill_id)
        if manifest is None:
            raise KeyError(f"Skill not installed: {skill_id}")
        return manifest

    async def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            event = NoblaEvent(
                event_type=event_type,
                source="skill_runtime",
                payload=payload,
            )
            await self._event_bus.emit(event)


class SecurityError(Exception):
    """Raised when a skill fails security scanning."""
