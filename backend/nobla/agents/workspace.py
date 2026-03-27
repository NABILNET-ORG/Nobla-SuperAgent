"""AgentWorkspace — scoped execution environment per agent (Phase 6).

Created by AgentExecutor at spawn time. Provides tool execution
with whitelist enforcement, scoped memory, artifact collection,
and resource tracking. Builds a synthetic ConnectionState for
the ToolExecutor pipeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nobla.agents.models import IsolationLevel, ResourceLimits, WorkspaceConfig
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolParams

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus
    from nobla.memory.orchestrator import MemoryOrchestrator
    from nobla.tools.executor import ToolExecutor
    from nobla.tools.models import ToolResult


class AgentWorkspace:
    """Isolated sandbox for a running agent instance."""

    def __init__(
        self,
        instance_id: str,
        config: WorkspaceConfig,
        tool_executor: ToolExecutor,
        user_id: str,
        agent_tier: Tier,
        event_bus: NoblaEventBus | None = None,
        memory_orchestrator: MemoryOrchestrator | None = None,
    ) -> None:
        self._instance_id = instance_id
        self._config = config
        self._tool_executor = tool_executor
        self._event_bus = event_bus
        self._memory = memory_orchestrator
        self._tool_whitelist: set[str] = set(config.tool_whitelist)
        self._limits = config.resource_limits
        self._artifacts: list[dict] = []
        self._start_time = time.monotonic()

        # Usage counters
        self._tool_calls = 0
        self._llm_tokens = 0
        self._memory_writes = 0

        # Synthetic connection for ToolExecutor pipeline
        self._connection_state = ConnectionState(
            connection_id=f"agent:{instance_id}",
            user_id=user_id,
            tier=agent_tier,
        )

    # ── Tool execution ──

    def available_tools(self) -> list[str]:
        return list(self._tool_whitelist)

    async def execute_tool(self, tool_name: str, params: dict) -> ToolResult:
        if tool_name not in self._tool_whitelist:
            raise PermissionError(
                f"Tool '{tool_name}' not in whitelist for agent {self._instance_id}"
            )
        if not self.within_limits():
            raise RuntimeError(
                f"Agent {self._instance_id} exceeded resource limit"
            )

        tool_params = ToolParams(
            args=params,
            connection_state=self._connection_state,
            context={"agent_instance_id": self._instance_id},
        )
        result = await self._tool_executor.execute(tool_name, tool_params)
        self._tool_calls += 1

        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent

            await self._event_bus.emit(NoblaEvent(
                event_type="agent.tool.used",
                source=f"agent.{self._instance_id}",
                payload={
                    "tool_name": tool_name,
                    "success": result.success,
                },
                user_id=self._connection_state.user_id,
            ))
        return result

    # ── Memory (scoped) ──

    async def store(self, key: str, value: Any, layer: str = "episodic") -> None:
        if self._memory is None:
            return
        scoped_key = f"agent:{self._instance_id}:{key}"
        await self._memory.store(scoped_key, value, layer=layer)
        self._memory_writes += 1

    async def recall(self, query: str, layer: str | None = None) -> list[dict]:
        if self._memory is None:
            return []
        results = await self._memory.recall(
            query, scope=f"agent:{self._instance_id}", layer=layer,
        )
        if self._config.isolation in (
            IsolationLevel.SHARED_READ, IsolationLevel.SHARED_READWRITE,
        ):
            for pool in self._config.shared_pools:
                results.extend(
                    await self._memory.recall(query, scope=pool, layer=layer)
                )
        return results

    async def store_shared(self, pool: str, key: str, value: Any) -> None:
        if self._config.isolation != IsolationLevel.SHARED_READWRITE:
            raise PermissionError(
                "store_shared requires SHARED_READWRITE isolation"
            )
        if self._memory is None:
            return
        scoped_key = f"{pool}:{key}"
        await self._memory.store(scoped_key, value, layer="episodic")
        self._memory_writes += 1

    # ── Artifacts ──

    def add_artifact(self, artifact: dict) -> None:
        self._artifacts.append(artifact)

    def get_artifacts(self) -> list[dict]:
        return list(self._artifacts)

    # ── Resource tracking ──

    def usage(self) -> dict:
        return {
            "tool_calls": self._tool_calls,
            "llm_tokens": self._llm_tokens,
            "memory_writes": self._memory_writes,
            "elapsed_seconds": time.monotonic() - self._start_time,
        }

    def within_limits(self) -> bool:
        if self._tool_calls >= self._limits.max_tool_calls:
            return False
        if self._llm_tokens >= self._limits.max_llm_tokens:
            return False
        if self._memory_writes >= self._limits.max_memory_writes:
            return False
        if (time.monotonic() - self._start_time) >= self._limits.max_runtime_seconds:
            return False
        return True

    def track_llm_tokens(self, count: int) -> None:
        self._llm_tokens += count

    # ── Cleanup ──

    async def cleanup(self) -> None:
        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent

            await self._event_bus.emit(NoblaEvent(
                event_type="agent.workspace.cleaned",
                source=f"agent.{self._instance_id}",
                payload={"isolation": self._config.isolation.value},
            ))
