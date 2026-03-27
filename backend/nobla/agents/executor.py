"""AgentExecutor — spawns and manages agent instances (Phase 6).

Transactional spawn: if workspace creation or on_start() fails,
the instance is rolled back. Kill switch integration via kill()
and kill_all().
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig, AgentStatus, WorkspaceConfig
from nobla.agents.workspace import AgentWorkspace
from nobla.events.models import NoblaEvent
from nobla.security.permissions import Tier

if TYPE_CHECKING:
    from nobla.agents.registry import AgentRegistry
    from nobla.events.bus import NoblaEventBus
    from nobla.brain.router import LLMRouter
    from nobla.memory.orchestrator import MemoryOrchestrator
    from nobla.tools.executor import ToolExecutor
    from nobla.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class AgentExecutor:
    """Spawns and manages running agent instances."""

    def __init__(
        self,
        registry: AgentRegistry,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        event_bus: NoblaEventBus,
        router: LLMRouter,
        memory_orchestrator: MemoryOrchestrator | None = None,
        max_concurrent_agents: int = 10,
    ) -> None:
        self._registry = registry
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._event_bus = event_bus
        self._router = router
        self._memory = memory_orchestrator
        self._max_concurrent = max_concurrent_agents
        self._instances: dict[str, BaseAgent] = {}

    async def spawn(
        self,
        agent_name: str,
        user_tier: Tier,
        config_overrides: dict | None = None,
        parent_id: str | None = None,
        user_id: str | None = None,
    ) -> BaseAgent:
        # Check concurrency limit
        if len(self._instances) >= self._max_concurrent:
            raise RuntimeError(
                f"Max concurrent agents ({self._max_concurrent}) reached"
            )

        # Look up agent type
        entry = self._registry.get(agent_name)
        if entry is None:
            raise ValueError(f"Agent '{agent_name}' not registered")
        agent_cls, config = entry

        # Apply overrides
        if config_overrides:
            config = config.model_copy(update=config_overrides)

        # Tier validation
        if config.tier > user_tier:
            raise PermissionError(
                f"Agent tier {config.tier.name} exceeds user tier {user_tier.name}"
            )

        # Create instance
        instance_id = str(uuid.uuid4())
        agent = agent_cls(config=config)
        agent.instance_id = instance_id
        agent.event_bus = self._event_bus
        agent.router = self._router

        # Create workspace
        ws_config = WorkspaceConfig(
            isolation=config.default_isolation,
            tool_whitelist=config.allowed_tools,
            resource_limits=config.resource_limits,
        )
        agent.workspace = AgentWorkspace(
            instance_id=instance_id,
            config=ws_config,
            tool_executor=self._tool_executor,
            user_id=user_id or "system",
            agent_tier=config.tier,
            event_bus=self._event_bus,
            memory_orchestrator=self._memory,
        )

        # Start agent
        try:
            await agent.on_start()
        except Exception as e:
            logger.error("agent_start_failed", agent=agent_name, error=str(e))
            await self._event_bus.emit(NoblaEvent(
                event_type="agent.spawn_failed",
                source="agent.executor",
                payload={"agent_name": agent_name, "error": str(e)},
            ))
            raise

        self._instances[instance_id] = agent
        await self._event_bus.emit(NoblaEvent(
            event_type="agent.spawned",
            source="agent.executor",
            payload={
                "instance_id": instance_id,
                "agent_name": agent_name,
                "parent_id": parent_id,
                "tier": config.tier.value,
            },
        ))
        logger.info("agent_spawned", instance_id=instance_id, agent=agent_name)
        return agent

    async def stop(self, instance_id: str, reason: str = "requested") -> None:
        agent = self._instances.get(instance_id)
        if agent is None:
            return
        agent.status = AgentStatus.STOPPED
        try:
            await agent.on_stop()
        except Exception as e:
            logger.warning("agent_stop_hook_error", instance=instance_id, error=str(e))
        if agent.workspace:
            await agent.workspace.cleanup()
        del self._instances[instance_id]
        await self._event_bus.emit(NoblaEvent(
            event_type="agent.stopped",
            source="agent.executor",
            payload={"instance_id": instance_id, "reason": reason},
        ))
        logger.info("agent_stopped", instance_id=instance_id, reason=reason)

    async def kill(self, instance_id: str) -> None:
        agent = self._instances.pop(instance_id, None)
        if agent is None:
            return
        agent.status = AgentStatus.STOPPED
        logger.warning("agent_killed", instance_id=instance_id)

    async def kill_all(self) -> None:
        for instance_id in list(self._instances.keys()):
            await self.kill(instance_id)
        logger.warning("all_agents_killed", count=len(self._instances))

    async def stop_all(self) -> None:
        for instance_id in list(self._instances.keys()):
            await self.stop(instance_id, reason="shutdown")

    def get(self, instance_id: str) -> BaseAgent | None:
        return self._instances.get(instance_id)

    def list_running(self) -> list[dict]:
        return [
            {
                "instance_id": iid,
                "name": agent.name,
                "status": agent.status.value,
            }
            for iid, agent in self._instances.items()
        ]
