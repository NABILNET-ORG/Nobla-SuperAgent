"""SkillGenerator — creates workflow macros from patterns, promotes to skills.

Phase 5B.1: macro creation, security-gated skill promotion, publishable lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from nobla.events.models import NoblaEvent
from nobla.learning.models import (
    MacroParameter,
    MacroTier,
    PatternCandidate,
    WorkflowMacro,
)

logger = structlog.get_logger(__name__)


class SkillGenerator:
    """Converts confirmed PatternCandidates into WorkflowMacros and promotes them to skills."""

    def __init__(
        self,
        event_bus: Any,
        workflow_service: Any,
        skill_runtime: Any,
        security_scanner: Any,
        llm_router: Any,
    ) -> None:
        self._event_bus = event_bus
        self._workflow_service = workflow_service
        self._skill_runtime = skill_runtime
        self._security_scanner = security_scanner
        self._llm_router = llm_router
        # keyed by macro.id
        self._macros: dict[str, WorkflowMacro] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_macro(self, pattern: PatternCandidate) -> WorkflowMacro:
        """Create a WorkflowMacro from a confirmed PatternCandidate.

        Extracts variable parameters, creates a backing workflow via the
        workflow_service, and emits a `learning.macro.created` event.
        """
        parameters = self._extract_parameters(pattern.variable_params)

        workflow_id: str = await self._workflow_service.create_from_steps(
            pattern.tool_sequence
        )

        name = pattern.description or f"Macro: {' → '.join(pattern.tool_sequence)}"
        description = f"Auto-generated from pattern: {pattern.description}"

        macro = WorkflowMacro(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            pattern_id=pattern.id,
            workflow_id=workflow_id,
            skill_id=None,
            parameters=parameters,
            tier=MacroTier.MACRO,
            usage_count=0,
            user_id=pattern.user_id,
            created_at=datetime.now(timezone.utc),
            promoted_at=None,
        )

        self._macros[macro.id] = macro

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.macro.created",
                source="learning.generator",
                payload={
                    "macro_id": macro.id,
                    "pattern_id": pattern.id,
                    "user_id": pattern.user_id,
                    "workflow_id": workflow_id,
                },
                user_id=pattern.user_id,
            )
        )

        logger.info(
            "macro.created",
            macro_id=macro.id,
            pattern_id=pattern.id,
            user_id=pattern.user_id,
        )

        return macro

    async def promote_to_skill(self, macro_id: str) -> WorkflowMacro | None:
        """Promote a MACRO-tier WorkflowMacro to SKILL tier.

        Generates skill code via the LLM router, runs a security scan, and
        installs the skill via the skill_runtime. Returns None if the scan fails.
        """
        macro = self._macros.get(macro_id)
        if macro is None:
            logger.warning("promote_to_skill: macro not found", macro_id=macro_id)
            return None

        # Generate skill code via LLM (mock-friendly)
        llm_response = await self._llm_router.route(
            f"Generate a reusable skill function for: {macro.description}"
        )
        skill_code: str = getattr(llm_response, "content", "")

        # Security gate
        scan_result = await self._security_scanner.scan(skill_code)
        if not scan_result.passed:
            logger.warning(
                "promote_to_skill: security scan failed",
                macro_id=macro_id,
                issues=scan_result.issues,
            )
            return None

        # Install the skill
        manifest = await self._skill_runtime.install(skill_code)

        macro.tier = MacroTier.SKILL
        macro.skill_id = manifest.id
        macro.promoted_at = datetime.now(timezone.utc)

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.skill.promoted",
                source="learning.generator",
                payload={
                    "macro_id": macro_id,
                    "skill_id": manifest.id,
                    "user_id": macro.user_id,
                },
                user_id=macro.user_id,
            )
        )

        logger.info(
            "skill.promoted",
            macro_id=macro_id,
            skill_id=manifest.id,
            user_id=macro.user_id,
        )

        return macro

    async def mark_publishable(
        self, macro_id: str, metadata: dict[str, Any]
    ) -> WorkflowMacro:
        """Advance a SKILL-tier macro to PUBLISHABLE and emit an event.

        Args:
            macro_id: ID of the macro to publish.
            metadata: Arbitrary publish metadata (e.g. tags, description overrides).

        Returns:
            The updated WorkflowMacro.
        """
        macro = self._macros[macro_id]
        macro.tier = MacroTier.PUBLISHABLE

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.skill.publishable",
                source="learning.generator",
                payload={
                    "macro_id": macro_id,
                    "skill_id": macro.skill_id,
                    "user_id": macro.user_id,
                    "metadata": metadata,
                },
                user_id=macro.user_id,
            )
        )

        logger.info(
            "skill.publishable",
            macro_id=macro_id,
            skill_id=macro.skill_id,
            user_id=macro.user_id,
        )

        return macro

    async def get_macros(
        self,
        user_id: str,
        tier: MacroTier | None = None,
    ) -> list[WorkflowMacro]:
        """Return macros for a user, optionally filtered by tier."""
        results = [m for m in self._macros.values() if m.user_id == user_id]
        if tier is not None:
            results = [m for m in results if m.tier == tier]
        return results

    async def delete_macro(self, macro_id: str) -> None:
        """Remove a macro from the store."""
        self._macros.pop(macro_id, None)
        logger.info("macro.deleted", macro_id=macro_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_parameters(
        self, variable_params: dict[str, list[Any]]
    ) -> list[MacroParameter]:
        """Convert variable_params into MacroParameter objects."""
        parameters: list[MacroParameter] = []
        for name, values in variable_params.items():
            # Infer a simple type label from the first value
            first = values[0] if values else None
            type_label = type(first).__name__ if first is not None else "str"
            default = first

            parameters.append(
                MacroParameter(
                    name=name,
                    description=f"Parameter '{name}' extracted from pattern occurrences",
                    type=type_label,
                    default=default,
                    examples=list(values),
                )
            )
        return parameters
