"""Tool registry with decorator-based auto-discovery."""
from __future__ import annotations

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory

_TOOL_REGISTRY: dict[str, BaseTool] = {}


def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Class decorator: instantiate and register a tool."""
    instance = cls()
    if instance.name in _TOOL_REGISTRY:
        raise ValueError(f"Duplicate tool name: {instance.name}")
    _TOOL_REGISTRY[instance.name] = instance
    return cls


class ToolRegistry:
    """Central access point for discovering and retrieving tools."""

    def get(self, name: str) -> BaseTool | None:
        return _TOOL_REGISTRY.get(name)

    def list_all(self) -> list[BaseTool]:
        return list(_TOOL_REGISTRY.values())

    def list_by_category(self, category: ToolCategory) -> list[BaseTool]:
        return [t for t in _TOOL_REGISTRY.values() if t.category == category]

    def list_available(self, tier: Tier) -> list[BaseTool]:
        """Tools the user can access at their current tier."""
        return [t for t in _TOOL_REGISTRY.values() if t.tier <= tier]

    def get_manifest(self, tier: Tier) -> list[dict]:
        """Tool descriptions for LLM function-calling and Flutter UI."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "requires_approval": t.requires_approval,
            }
            for t in self.list_available(tier)
        ]
