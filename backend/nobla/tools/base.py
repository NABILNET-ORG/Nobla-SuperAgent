"""Abstract base class for all Nobla tools."""
from __future__ import annotations

from abc import ABC, abstractmethod

from nobla.security.audit import sanitize_params
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


class BaseTool(ABC):
    """Base class for tools. Subclasses define metadata as class variables.

    Example::

        @register_tool
        class ScreenshotTool(BaseTool):
            name = "screenshot.capture"
            description = "Capture a screenshot"
            category = ToolCategory.VISION
            tier = Tier.STANDARD

            async def execute(self, params: ToolParams) -> ToolResult:
                ...
    """

    name: str
    description: str
    category: ToolCategory
    tier: Tier = Tier.STANDARD
    requires_approval: bool = False
    approval_timeout: int = 30

    @abstractmethod
    async def execute(self, params: ToolParams) -> ToolResult:
        """Run the tool. Called only after permission + approval pass."""
        ...

    async def validate(self, params: ToolParams) -> None:
        """Optional pre-execution validation. Raise ValueError on bad input."""

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        return self.description

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display. Redacts sensitive fields."""
        return sanitize_params(params.args)

    def needs_approval(self, params: ToolParams) -> bool:
        """Whether this action needs user approval. Override for conditional logic."""
        return self.requires_approval
