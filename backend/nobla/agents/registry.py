"""Agent registry — stateless facade for agent type management (Phase 6).

Mirrors ToolRegistry pattern: no constructor dependencies.
Lifecycle events are the executor's responsibility.
"""

from __future__ import annotations

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig


class AgentRegistry:
    """Central access point for discovering and retrieving agent types."""

    def __init__(self) -> None:
        self._agents: dict[str, tuple[type[BaseAgent], AgentConfig]] = {}

    def register(
        self,
        agent_cls: type[BaseAgent],
        config: AgentConfig,
        allow_overwrite: bool = False,
    ) -> None:
        if config.name in self._agents and not allow_overwrite:
            raise ValueError(
                f"Agent '{config.name}' already registered. "
                "Pass allow_overwrite=True to replace."
            )
        self._agents[config.name] = (agent_cls, config)

    def unregister(self, name: str) -> bool:
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    def get(self, name: str) -> tuple[type[BaseAgent], AgentConfig] | None:
        return self._agents.get(name)

    def list_all(self) -> list[AgentConfig]:
        return [config for _, config in self._agents.values()]

    def list_by_role(self, keyword: str) -> list[AgentConfig]:
        kw = keyword.lower()
        return [
            config
            for _, config in self._agents.values()
            if kw in config.role.lower() or kw in config.description.lower()
        ]

    def get_manifest(self) -> list[dict]:
        return [
            {
                "name": config.name,
                "description": config.description,
                "tier": config.tier.value,
                "allowed_tools": config.allowed_tools,
            }
            for _, config in self._agents.values()
        ]
