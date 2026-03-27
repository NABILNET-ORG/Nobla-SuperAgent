"""Skill data models — manifest, runtime interface, enums.

Spec reference: Phase 5-Foundation §4.3 — Skill Runtime & Universal Adapter.

Skills are external — they don't subclass BaseTool directly. The SkillToolBridge
(bridge.py) wraps any NoblaSkill into a proper BaseTool subclass so it can
register into the existing ToolRegistry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory


class SkillSource(str, Enum):
    """Origin format of an imported skill."""

    NOBLA = "nobla"
    MCP = "mcp"
    OPENCLAW = "openclaw"
    CLAUDE = "claude"
    LANGCHAIN = "langchain"


class SkillCategory(str, Enum):
    """Extends ToolCategory for marketplace skills.

    Existing ToolCategory values map 1:1. New categories are marketplace-only.
    For categories that don't exist in ToolCategory, to_tool_category()
    returns ToolCategory.SKILL (a catch-all).
    """

    # Existing ToolCategory mappings (same values)
    VISION = "vision"
    INPUT = "input"
    FILE_SYSTEM = "file_system"
    APP_CONTROL = "app_control"
    CODE = "code"
    GIT = "git"
    SSH = "ssh"
    CLIPBOARD = "clipboard"
    SEARCH = "search"
    # New marketplace categories
    PRODUCTIVITY = "productivity"
    MEDIA = "media"
    FINANCE = "finance"
    AUTOMATION = "automation"
    COMMUNICATION = "communication"
    RESEARCH = "research"
    UTILITIES = "utilities"

    def to_tool_category(self) -> ToolCategory:
        """Map to ToolCategory. Marketplace-only categories → SKILL catch-all."""
        try:
            return ToolCategory(self.value)
        except ValueError:
            return ToolCategory.SKILL


@dataclass(slots=True)
class SkillManifest:
    """Normalized metadata for any imported skill.

    Attributes:
        id: Unique identifier, e.g. "nobla://image-gen" or "mcp://github".
        name: Human-readable skill name.
        description: What the skill does.
        version: Semantic version string.
        source: Origin format (NOBLA, MCP, OPENCLAW, etc.).
        author: Skill author.
        category: Skill category (maps to ToolCategory).
        tier: Permission tier required to execute.
        requires_approval: Whether user approval is needed per execution.
        enabled: ALWAYS False by default — no exceptions.
        capabilities: List of capability strings.
        dependencies: Required packages or services.
        config_schema: Optional JSON schema for skill configuration.
        original_format: Raw source manifest preserved for debugging.
    """

    id: str
    name: str
    description: str
    version: str
    source: SkillSource
    author: str
    category: SkillCategory
    tier: Tier = Tier.STANDARD
    requires_approval: bool = True
    enabled: bool = False  # ALWAYS false by default — no exceptions
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None
    original_format: dict[str, Any] = field(default_factory=dict)


class NoblaSkill(ABC):
    """Abstract interface for all skills. Mirrors BaseTool's execute contract.

    Skills are wrapped by SkillToolBridge to register into ToolRegistry and
    flow through the standard executor pipeline (permissions, approval,
    sandbox, audit).
    """

    manifest: SkillManifest

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the skill with given parameters.

        Returns a result dict compatible with ToolResult construction.
        """
        ...

    @abstractmethod
    async def validate(self, params: dict[str, Any]) -> None:
        """Validate parameters before execution. Raise ValueError if invalid."""
        ...

    def describe_action(self, params: dict[str, Any]) -> str:
        """Human-readable description of what this execution will do."""
        return f"Run skill: {self.manifest.name}"

    def get_params_summary(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sanitized parameter summary for UI/audit (strip secrets)."""
        return {k: v for k, v in params.items() if "secret" not in k.lower()}
