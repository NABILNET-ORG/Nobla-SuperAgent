"""Skill-to-tool bridge — wraps NoblaSkill as BaseTool for ToolRegistry.

Spec reference: Phase 5-Foundation §4.3 — BaseTool Bridge.

Skills are external — they don't subclass BaseTool directly. SkillToolBridge
wraps any NoblaSkill into a proper BaseTool subclass so it can register into
the existing ToolRegistry and flow through the standard executor pipeline
(permissions, approval, sandbox, audit).
"""

from __future__ import annotations

from nobla.security.permissions import Tier
from nobla.skills.models import NoblaSkill, SkillManifest
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


class SkillToolBridge(BaseTool):
    """Wraps a NoblaSkill as a BaseTool for ToolRegistry integration.

    Maps manifest fields to BaseTool class attributes so the executor
    pipeline (PermissionChecker, ApprovalManager, AuditLogger) treats
    skills identically to built-in tools.
    """

    def __init__(self, skill: NoblaSkill) -> None:
        self._skill = skill
        m = skill.manifest
        self.name = m.name
        self.description = m.description
        self.category = m.category.to_tool_category()
        self.tier = m.tier
        self.requires_approval = m.requires_approval
        self._manifest = m

    @property
    def manifest(self) -> SkillManifest:
        """Access the original skill manifest."""
        return self._manifest

    @property
    def skill(self) -> NoblaSkill:
        """Access the wrapped skill instance."""
        return self._skill

    async def execute(self, params: ToolParams) -> ToolResult:
        """Delegate execution to the wrapped skill."""
        try:
            result_data = await self._skill.execute(params.args)
            return ToolResult(
                success=True,
                data=result_data,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
            )

    async def validate(self, params: ToolParams) -> None:
        """Delegate validation to the wrapped skill."""
        await self._skill.validate(params.args)

    def describe_action(self, params: ToolParams) -> str:
        """Delegate to skill's describe_action."""
        return self._skill.describe_action(params.args)

    def get_params_summary(self, params: ToolParams) -> dict:
        """Delegate to skill's get_params_summary."""
        return self._skill.get_params_summary(params.args)
