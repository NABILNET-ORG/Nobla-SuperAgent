"""BaseAgent ABC — the contract all agents implement (Phase 6)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from nobla.agents.models import (
    AgentConfig,
    AgentMessage,
    AgentStatus,
    AgentTask,
    MessageType,
    TaskStatus,
)

if TYPE_CHECKING:
    from nobla.agents.workspace import AgentWorkspace
    from nobla.events.bus import NoblaEventBus
    from nobla.brain.router import LLMRouter
    from nobla.tools.models import ToolResult


class BaseAgent(ABC):
    """Abstract base for all Nobla agents.

    Identity fields (name, description, role) delegate to self.config
    to avoid duplication. Dependencies (workspace, event_bus, router)
    are injected by AgentExecutor at spawn time.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.status: AgentStatus = AgentStatus.IDLE
        self.instance_id: str | None = None
        # Injected by executor at spawn time
        self.workspace: AgentWorkspace | None = None
        self.event_bus: NoblaEventBus | None = None
        self.router: LLMRouter | None = None

    # ── Identity (delegates to config) ──

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def description(self) -> str:
        return self.config.description

    @property
    def role(self) -> str:
        return self.config.role

    # ── Core abstract method ──

    @abstractmethod
    async def handle_task(self, task: AgentTask) -> AgentTask:
        """Process an assigned task. Return updated task with artifacts/status."""
        ...

    def get_capabilities(self) -> dict:
        """Return a capabilities dict for discovery. Override to customise."""
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "allowed_tools": list(self.config.allowed_tools),
            "llm_tier": self.config.llm_tier,
            "max_concurrent_tasks": self.config.max_concurrent_tasks,
        }

    # ── Lifecycle hooks ──

    async def on_start(self) -> None:
        """Called when agent instance starts. Override for setup."""

    async def on_stop(self) -> None:
        """Called when agent instance shuts down. Override for cleanup."""

    # ── Convenience methods ──

    async def think(self, prompt: str) -> str:
        """Send prompt to LLM router with agent's tier preference."""
        if self.router is None:
            raise RuntimeError("Agent has no LLM router (not spawned?)")
        return await self.router.route(prompt, tier=self.config.llm_tier)

    async def use_tool(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a tool through workspace's scoped executor."""
        if self.workspace is None:
            raise RuntimeError("Agent has no workspace (not spawned?)")
        return await self.workspace.execute_tool(tool_name, params)

    async def delegate(
        self, instruction: str, target: str | None = None,
    ) -> AgentTask:
        """Request orchestrator to assign a sub-task to another agent.

        Emits agent.task.delegate event; orchestrator picks it up.
        """
        if self.event_bus is None:
            raise RuntimeError("Agent has no event bus (not spawned?)")
        from nobla.events.models import NoblaEvent

        task = AgentTask(
            workflow_id="",  # orchestrator fills this
            assigner=self.instance_id or self.name,
            assignee=target or "",
            instruction=instruction,
        )
        await self.event_bus.emit(NoblaEvent(
            event_type="agent.task.delegate",
            source=f"agent.{self.instance_id}",
            payload={
                "task": task.model_dump(),
                "preferred_target": target,
            },
            user_id=None,
            priority=1,
        ))
        return task

    async def report(
        self, task: AgentTask, artifacts: list[dict],
    ) -> None:
        """Report task completion with artifacts back to orchestrator."""
        if self.event_bus is None:
            raise RuntimeError("Agent has no event bus (not spawned?)")
        from nobla.events.models import NoblaEvent

        task.artifacts = artifacts
        task.status = TaskStatus.COMPLETED
        await self.event_bus.emit(NoblaEvent(
            event_type="agent.a2a.task.result",
            source=f"agent.{self.instance_id}",
            payload={"task": task.model_dump()},
            user_id=None,
            priority=1,
        ))
