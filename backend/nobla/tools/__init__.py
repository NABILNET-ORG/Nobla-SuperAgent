"""Nobla tool platform — registry, executor, and auto-discovered tools."""
from nobla.tools.registry import ToolRegistry

tool_registry = ToolRegistry()

__all__ = ["tool_registry"]
