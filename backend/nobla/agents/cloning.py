"""Agent cloning — create agent variants from config templates (Phase 6)."""

from __future__ import annotations

from nobla.agents.models import AgentConfig


def clone_agent(original: AgentConfig, **overrides) -> AgentConfig:
    """Create a new AgentConfig by copying original and applying overrides.

    Example: clone_agent(researcher_config, name="fast-researcher", llm_tier="cheap")
    """
    return original.model_copy(update=overrides)
