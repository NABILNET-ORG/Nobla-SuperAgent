"""Tool registry with decorator-based auto-discovery."""
from __future__ import annotations

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory


class _ToolRegistryDict(dict):
    """dict subclass whose clear() restores module-level tool registrations.

    Tools decorated with ``@register_tool`` at module scope are recorded in
    ``_baseline``.  When a test fixture calls ``_TOOL_REGISTRY.clear()`` the
    baseline is restored automatically, so module-level tools are always
    present while tools registered inside fixtures/tests are discarded.

    The baseline is sealed on the first call to ``clear()``.  Any tools
    registered *after* the first clear (i.e., inside a test or fixture) are
    considered transient and are NOT added to the baseline.
    """

    def __init__(self):
        super().__init__()
        # Tools registered before the first clear() call (module-level tools).
        self._baseline: dict[str, "BaseTool"] = {}
        self._sealed: bool = False  # True after first clear()

    def _maybe_add_baseline(self, name: str, instance: "BaseTool") -> None:
        """Called by register_tool to track module-level registrations."""
        if not self._sealed:
            self._baseline[name] = instance

    def clear(self) -> None:  # type: ignore[override]
        self._sealed = True
        super().clear()
        # Restore module-level tools only.
        self.update(self._baseline)


_TOOL_REGISTRY: _ToolRegistryDict = _ToolRegistryDict()


def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Class decorator: instantiate and register a tool."""
    instance = cls()
    if instance.name in _TOOL_REGISTRY:
        raise ValueError(f"Duplicate tool name: {instance.name}")
    _TOOL_REGISTRY[instance.name] = instance
    _TOOL_REGISTRY._maybe_add_baseline(instance.name, instance)
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
