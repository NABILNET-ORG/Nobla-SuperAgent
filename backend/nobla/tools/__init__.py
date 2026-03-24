"""Nobla tool platform — registry, executor, and auto-discovered tools."""
from nobla.tools.registry import ToolRegistry

from nobla.tools import vision  # noqa: F401 — triggers @register_tool

tool_registry = ToolRegistry()

__all__ = ["tool_registry"]
