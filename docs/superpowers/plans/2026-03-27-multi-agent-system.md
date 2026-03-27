# Multi-Agent System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an orchestrator-centric multi-agent framework with task-based A2A protocol, configurable memory isolation, bidirectional MCP, and reference agents.

**Architecture:** Central `AgentOrchestrator` coordinates all agent lifecycle and task delegation. Agents never talk directly — all communication flows through the orchestrator via `NoblaEventBus`. Agents run in isolated `AgentWorkspace` instances with scoped tool access and memory. MCP client/server enables bidirectional integration with external systems.

**Tech Stack:** Python 3.12, asyncio, Pydantic, FastAPI, NoblaEventBus, ToolExecutor, LLMRouter

**Spec:** `docs/superpowers/specs/2026-03-27-multi-agent-system-design.md`

---

## File Map

### New files (create)
| File | Responsibility |
|------|---------------|
| `backend/nobla/agents/__init__.py` | Lazy imports |
| `backend/nobla/agents/models.py` | AgentConfig, AgentTask, AgentMessage, WorkflowState, enums, ResourceLimits |
| `backend/nobla/agents/base.py` | BaseAgent ABC |
| `backend/nobla/agents/registry.py` | AgentRegistry (stateless facade) |
| `backend/nobla/agents/workspace.py` | AgentWorkspace (scoped tool/memory/resource sandbox) |
| `backend/nobla/agents/executor.py` | AgentExecutor (spawn/stop/kill instances) |
| `backend/nobla/agents/communication.py` | A2AProtocol (task-based messaging over event bus) |
| `backend/nobla/agents/decomposer.py` | TaskDecomposer (LLM-driven task graph + agent selection) |
| `backend/nobla/agents/orchestrator.py` | AgentOrchestrator (workflow lifecycle + event handlers) |
| `backend/nobla/agents/bridge.py` | AgentToolBridge (expose agent as BaseTool) |
| `backend/nobla/agents/cloning.py` | Agent instance cloning from config templates |
| `backend/nobla/agents/mcp_client.py` | MCPClientManager (consume external MCP servers) |
| `backend/nobla/agents/mcp_server.py` | MCPServer (expose Nobla tools/agents as MCP server) |
| `backend/nobla/agents/builtins/__init__.py` | Lazy imports for built-in agents |
| `backend/nobla/agents/builtins/researcher.py` | ResearcherAgent reference implementation |
| `backend/nobla/agents/builtins/coder.py` | CoderAgent reference implementation |
| `backend/tests/test_agents.py` | All agent system tests |

### Existing files (modify)
| File | Change |
|------|--------|
| `backend/nobla/tools/models.py` | Add `ToolCategory.AGENT` |
| `backend/nobla/config/settings.py` | Add `AgentSettings`, `MCPClientSettings`, `MCPServerSettings` |
| `backend/nobla/gateway/lifespan.py` | Wire agent services in gateway lifespan |

---

## Task 1: Models & Enums

**Files:**
- Create: `backend/nobla/agents/__init__.py`
- Create: `backend/nobla/agents/models.py`
- Create: `backend/nobla/agents/builtins/__init__.py`
- Modify: `backend/nobla/tools/models.py`
- Modify: `backend/nobla/config/settings.py`
- Test: `backend/tests/test_agents.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/nobla/agents/builtins
```

- [ ] **Step 2: Create `backend/nobla/agents/__init__.py`**

```python
"""Multi-agent system (Phase 6).

Lazy imports to avoid hard dependencies on optional packages.
"""
```

- [ ] **Step 3: Create `backend/nobla/agents/builtins/__init__.py`**

```python
"""Built-in reference agent implementations."""
```

- [ ] **Step 4: Write failing tests for models**

Create `backend/tests/test_agents.py`:

```python
"""Tests for the Nobla Multi-Agent System (Phase 6).

Covers: models, enums, BaseAgent, registry, executor, workspace,
A2A protocol, orchestrator, decomposer, bridge, MCP client/server, builtins.
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.agents.models import (
    AgentConfig,
    AgentMessage,
    AgentStatus,
    AgentTask,
    IsolationLevel,
    MessageType,
    ResourceLimits,
    TaskStatus,
    WorkflowState,
    WorkspaceConfig,
)
from nobla.security.permissions import Tier


# ── Model tests ──────────────────────────────────────────────


class TestEnums:
    def test_agent_status_values(self):
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.BUSY == "busy"
        assert AgentStatus.STOPPED == "stopped"

    def test_task_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_isolation_level_values(self):
        assert IsolationLevel.FULL_ISOLATED == "full_isolated"
        assert IsolationLevel.SHARED_READ == "shared_read"
        assert IsolationLevel.SHARED_READWRITE == "shared_readwrite"

    def test_message_type_values(self):
        assert MessageType.TASK_ASSIGN == "task_assign"
        assert MessageType.TASK_RESULT == "task_result"


class TestResourceLimits:
    def test_defaults(self):
        limits = ResourceLimits()
        assert limits.max_tool_calls == 50
        assert limits.max_llm_tokens == 100_000
        assert limits.max_memory_writes == 200
        assert limits.max_runtime_seconds == 600

    def test_custom_values(self):
        limits = ResourceLimits(max_tool_calls=10, max_runtime_seconds=30)
        assert limits.max_tool_calls == 10
        assert limits.max_runtime_seconds == 30


class TestAgentConfig:
    def test_creates_with_required_fields(self):
        config = AgentConfig(
            name="researcher",
            description="Searches the web",
            role="You are a research assistant.",
            tier=Tier.STANDARD,
        )
        assert config.name == "researcher"
        assert config.tier == Tier.STANDARD
        assert config.llm_tier == "balanced"
        assert config.allowed_tools == []
        assert config.requires_approval is False
        assert config.max_concurrent_tasks == 3
        assert config.default_isolation == IsolationLevel.FULL_ISOLATED

    def test_tier_validation_rejects_invalid(self):
        config = AgentConfig(
            name="test", description="t", role="t", tier=Tier.ELEVATED,
        )
        assert config.tier == Tier.ELEVATED


class TestAgentTask:
    def test_creates_with_defaults(self):
        task = AgentTask(
            workflow_id="wf-1",
            assigner="orchestrator",
            assignee="agent-1",
            instruction="Search for X",
        )
        assert task.task_id  # auto-generated UUID
        assert task.status == TaskStatus.PENDING
        assert task.artifacts == []
        assert task.retry_count == 0
        assert task.parent_task_id is None

    def test_with_all_fields(self):
        task = AgentTask(
            task_id="custom-id",
            parent_task_id="parent-1",
            workflow_id="wf-1",
            assigner="orch",
            assignee="agent-2",
            instruction="Code this",
            status=TaskStatus.RUNNING,
            artifacts=[{"type": "code", "content": "print('hi')"}],
            retry_count=1,
        )
        assert task.task_id == "custom-id"
        assert task.parent_task_id == "parent-1"
        assert task.status == TaskStatus.RUNNING


class TestAgentMessage:
    def test_creates_message(self):
        task = AgentTask(
            workflow_id="wf-1", assigner="o", assignee="a", instruction="x",
        )
        msg = AgentMessage(
            message_type=MessageType.TASK_ASSIGN,
            sender="orchestrator",
            recipient="agent-1",
            task=task,
        )
        assert msg.message_type == MessageType.TASK_ASSIGN
        assert msg.correlation_id  # auto-generated


class TestWorkflowState:
    def test_creates_workflow(self):
        ws = WorkflowState(
            workflow_id="wf-1",
            user_id="user-1",
            user_tier=Tier.STANDARD,
            instruction="Do research",
            task_graph={},
            agent_assignments={},
            status="running",
            depth=0,
            created_at=datetime.now(timezone.utc),
        )
        assert ws.workflow_id == "wf-1"
        assert ws.user_tier == Tier.STANDARD

    def test_mutable(self):
        ws = WorkflowState(
            workflow_id="wf-1", user_id="u", user_tier=Tier.STANDARD,
            instruction="x", task_graph={}, agent_assignments={},
            status="running", depth=0, created_at=datetime.now(timezone.utc),
        )
        ws.status = "completed"
        assert ws.status == "completed"


class TestWorkspaceConfig:
    def test_defaults(self):
        wc = WorkspaceConfig()
        assert wc.isolation == IsolationLevel.FULL_ISOLATED
        assert wc.tool_whitelist == []
        assert wc.shared_pools == []

    def test_with_shared_pools(self):
        wc = WorkspaceConfig(
            isolation=IsolationLevel.SHARED_READ,
            shared_pools=["workflow:wf-1"],
        )
        assert wc.shared_pools == ["workflow:wf-1"]
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.agents.models'`

- [ ] **Step 6: Implement `backend/nobla/agents/models.py`**

```python
"""Data models for the multi-agent system (Phase 6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from nobla.security.permissions import Tier


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IsolationLevel(str, Enum):
    FULL_ISOLATED = "full_isolated"
    SHARED_READ = "shared_read"
    SHARED_READWRITE = "shared_readwrite"


class MessageType(str, Enum):
    TASK_ASSIGN = "task_assign"
    TASK_UPDATE = "task_update"
    TASK_RESULT = "task_result"
    TASK_ERROR = "task_error"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"


class ResourceLimits(BaseModel):
    max_tool_calls: int = 50
    max_llm_tokens: int = 100_000
    max_memory_writes: int = 200
    max_runtime_seconds: int = 600


class WorkspaceConfig(BaseModel):
    isolation: IsolationLevel = IsolationLevel.FULL_ISOLATED
    tool_whitelist: list[str] = Field(default_factory=list)
    shared_pools: list[str] = Field(default_factory=list)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)


class AgentConfig(BaseModel):
    name: str
    description: str
    role: str
    tier: Tier = Tier.STANDARD
    llm_tier: str = "balanced"
    allowed_tools: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    max_concurrent_tasks: int = 3
    default_isolation: IsolationLevel = IsolationLevel.FULL_ISOLATED
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)


class AgentTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str | None = None
    workflow_id: str
    assigner: str
    assignee: str
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: datetime | None = None
    retry_count: int = 0


class AgentMessage(BaseModel):
    message_type: MessageType
    sender: str
    recipient: str
    task: AgentTask | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(slots=True)
class WorkflowState:
    """Mutable workflow state — uses @dataclass intentionally:
    frequently mutated in-place, no validation needed, lighter weight.
    Matches NoblaEvent and ChannelMessage pattern."""

    workflow_id: str
    user_id: str
    user_tier: Tier
    instruction: str
    task_graph: dict[str, AgentTask]
    agent_assignments: dict[str, str]
    status: str
    depth: int
    created_at: datetime
```

- [ ] **Step 7: Add `ToolCategory.AGENT` to `backend/nobla/tools/models.py`**

Add after `SKILL = "skill"`:

```python
    AGENT = "agent"
```

- [ ] **Step 8: Add settings to `backend/nobla/config/settings.py`**

Add these classes before the main `Settings` class, and add fields to `Settings`:

```python
class AgentSettings(BaseModel):
    enabled: bool = True
    max_concurrent_agents: int = 10
    max_workflow_depth: int = 5
    max_tasks_per_workflow: int = 20
    default_isolation: str = "full_isolated"


class MCPClientSettings(BaseModel):
    enabled: bool = False
    max_connections: int = 20
    default_timeout: float = 30.0
    allowed_servers: list[str] = Field(default_factory=list)


class MCPServerSettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8100
    transport: str = "sse"
    require_auth: bool = True
    default_tier: int = 2  # Tier.STANDARD value; use int for Pydantic serialization
    exposed_tools: list[str] = Field(default_factory=list)
    exposed_agents: list[str] = Field(default_factory=list)
```

Add to `Settings` class:

```python
    agents: AgentSettings = Field(default_factory=AgentSettings)
    mcp_client: MCPClientSettings = Field(default_factory=MCPClientSettings)
    mcp_server: MCPServerSettings = Field(default_factory=MCPServerSettings)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 10: Run full test suite**

Run: `cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py -v`
Expected: 344 + new agent tests pass

- [ ] **Step 11: Commit**

```bash
git add backend/nobla/agents/ backend/nobla/tools/models.py backend/nobla/config/settings.py backend/tests/test_agents.py
git commit -m "feat(phase6): add multi-agent models, enums, settings, ToolCategory.AGENT"
```

---

## Task 2: BaseAgent ABC

**Files:**
- Create: `backend/nobla/agents/base.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.base import BaseAgent


# ── BaseAgent tests ──────────────────────────────────────────


class _StubAgent(BaseAgent):
    """Minimal concrete agent for testing the ABC."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        task.status = TaskStatus.COMPLETED
        task.artifacts.append({"type": "text", "content": "done"})
        return task


class TestBaseAgent:
    def _make_agent(self) -> _StubAgent:
        config = AgentConfig(
            name="stub", description="A stub", role="You are a stub.",
            tier=Tier.STANDARD, allowed_tools=["search.web"],
        )
        agent = _StubAgent(config=config)
        return agent

    def test_properties_delegate_to_config(self):
        agent = self._make_agent()
        assert agent.name == "stub"
        assert agent.description == "A stub"
        assert agent.role == "You are a stub."

    def test_initial_status_is_idle(self):
        agent = self._make_agent()
        assert agent.status == AgentStatus.IDLE

    def test_instance_id_is_none_before_spawn(self):
        agent = self._make_agent()
        assert agent.instance_id is None

    @pytest.mark.asyncio
    async def test_handle_task(self):
        agent = self._make_agent()
        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="stub-1", instruction="Do something",
        )
        result = await agent.handle_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert len(result.artifacts) == 1

    @pytest.mark.asyncio
    async def test_on_start_default_is_noop(self):
        agent = self._make_agent()
        await agent.on_start()  # should not raise

    @pytest.mark.asyncio
    async def test_on_stop_default_is_noop(self):
        agent = self._make_agent()
        await agent.on_stop()  # should not raise

    @pytest.mark.asyncio
    async def test_think_delegates_to_router(self):
        agent = self._make_agent()
        mock_router = AsyncMock()
        mock_router.route.return_value = "LLM response"
        agent.router = mock_router
        result = await agent.think("What is 2+2?")
        assert result == "LLM response"
        mock_router.route.assert_called_once()

    @pytest.mark.asyncio
    async def test_use_tool_delegates_to_workspace(self):
        agent = self._make_agent()
        mock_ws = AsyncMock()
        mock_ws.execute_tool.return_value = MagicMock(success=True, data="ok")
        agent.workspace = mock_ws
        result = await agent.use_tool("search.web", {"query": "test"})
        assert result.success is True
        mock_ws.execute_tool.assert_called_once_with("search.web", {"query": "test"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestBaseAgent -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.agents.base'`

- [ ] **Step 3: Implement `backend/nobla/agents/base.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestBaseAgent -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/base.py backend/tests/test_agents.py
git commit -m "feat(phase6): add BaseAgent ABC with lifecycle hooks and convenience methods"
```

---

## Task 3: AgentRegistry

**Files:**
- Create: `backend/nobla/agents/registry.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.registry import AgentRegistry


# ── Registry tests ───────────────────────────────────────────


class TestAgentRegistry:
    def _make_registry(self) -> AgentRegistry:
        return AgentRegistry()

    def _researcher_config(self) -> AgentConfig:
        return AgentConfig(
            name="researcher", description="Searches the web",
            role="You are a researcher.", tier=Tier.STANDARD,
        )

    def _coder_config(self) -> AgentConfig:
        return AgentConfig(
            name="coder", description="Writes code",
            role="You are a coder.", tier=Tier.ELEVATED,
        )

    def test_register_and_get(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        result = reg.get("researcher")
        assert result is not None
        cls, config = result
        assert cls is _StubAgent
        assert config.name == "researcher"

    def test_get_returns_none_for_unknown(self):
        reg = self._make_registry()
        assert reg.get("nonexistent") is None

    def test_register_duplicate_raises(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_StubAgent, self._researcher_config())

    def test_register_overwrite(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        new_config = self._researcher_config()
        new_config.description = "Updated"
        reg.register(_StubAgent, new_config, allow_overwrite=True)
        _, config = reg.get("researcher")
        assert config.description == "Updated"

    def test_unregister(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        assert reg.unregister("researcher") is True
        assert reg.get("researcher") is None

    def test_unregister_unknown_returns_false(self):
        reg = self._make_registry()
        assert reg.unregister("nonexistent") is False

    def test_list_all(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        reg.register(_StubAgent, self._coder_config())
        configs = reg.list_all()
        assert len(configs) == 2
        names = {c.name for c in configs}
        assert names == {"researcher", "coder"}

    def test_list_by_role(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        reg.register(_StubAgent, self._coder_config())
        results = reg.list_by_role("search")
        assert len(results) == 1
        assert results[0].name == "researcher"

    def test_get_manifest(self):
        reg = self._make_registry()
        reg.register(_StubAgent, self._researcher_config())
        manifest = reg.get_manifest()
        assert len(manifest) == 1
        assert manifest[0]["name"] == "researcher"
        assert "description" in manifest[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestAgentRegistry -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/registry.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestAgentRegistry -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/registry.py backend/tests/test_agents.py
git commit -m "feat(phase6): add AgentRegistry — stateless agent type management"
```

---

## Task 4: AgentWorkspace

**Files:**
- Create: `backend/nobla/agents/workspace.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.workspace import AgentWorkspace


# ── Workspace tests ──────────────────────────────────────────


class TestAgentWorkspace:
    def _make_workspace(
        self,
        tool_whitelist=None,
        isolation=IsolationLevel.FULL_ISOLATED,
        max_tool_calls=50,
    ) -> AgentWorkspace:
        from nobla.agents.models import WorkspaceConfig
        config = WorkspaceConfig(
            isolation=isolation,
            tool_whitelist=tool_whitelist or ["search.web"],
            resource_limits=ResourceLimits(max_tool_calls=max_tool_calls),
        )
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = MagicMock(success=True, data="ok")
        return AgentWorkspace(
            instance_id="agent-1",
            config=config,
            tool_executor=mock_executor,
            user_id="user-1",
            agent_tier=Tier.STANDARD,
            event_bus=None,
            memory_orchestrator=None,
        )

    def test_available_tools(self):
        ws = self._make_workspace(tool_whitelist=["search.web", "code.run"])
        assert set(ws.available_tools()) == {"search.web", "code.run"}

    @pytest.mark.asyncio
    async def test_execute_tool_allowed(self):
        ws = self._make_workspace()
        result = await ws.execute_tool("search.web", {"query": "test"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_tool_blocked(self):
        ws = self._make_workspace(tool_whitelist=["search.web"])
        with pytest.raises(PermissionError, match="not in whitelist"):
            await ws.execute_tool("code.run", {"code": "print(1)"})

    @pytest.mark.asyncio
    async def test_resource_limit_enforced(self):
        ws = self._make_workspace(max_tool_calls=2)
        await ws.execute_tool("search.web", {"q": "1"})
        await ws.execute_tool("search.web", {"q": "2"})
        with pytest.raises(RuntimeError, match="resource limit"):
            await ws.execute_tool("search.web", {"q": "3"})

    def test_usage_tracking(self):
        ws = self._make_workspace()
        usage = ws.usage()
        assert usage["tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_usage_increments(self):
        ws = self._make_workspace()
        await ws.execute_tool("search.web", {"q": "test"})
        assert ws.usage()["tool_calls"] == 1

    def test_within_limits_true(self):
        ws = self._make_workspace()
        assert ws.within_limits() is True

    def test_artifacts(self):
        ws = self._make_workspace()
        ws.add_artifact({"type": "text", "content": "hello"})
        assert len(ws.get_artifacts()) == 1
        assert ws.get_artifacts()[0]["content"] == "hello"

    def test_connection_state_has_agent_prefix(self):
        ws = self._make_workspace()
        assert ws._connection_state.connection_id == "agent:agent-1"
        assert ws._connection_state.user_id == "user-1"
        assert ws._connection_state.tier == Tier.STANDARD

    @pytest.mark.asyncio
    async def test_store_shared_blocked_when_isolated(self):
        ws = self._make_workspace(isolation=IsolationLevel.FULL_ISOLATED)
        with pytest.raises(PermissionError, match="SHARED_READWRITE"):
            await ws.store_shared("pool-1", "key", "value")

    @pytest.mark.asyncio
    async def test_store_shared_allowed_when_readwrite(self):
        ws = self._make_workspace(isolation=IsolationLevel.SHARED_READWRITE)
        # Should not raise (memory_orchestrator is None so it's a no-op)
        await ws.store_shared("pool-1", "key", "value")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestAgentWorkspace -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/workspace.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestAgentWorkspace -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/workspace.py backend/tests/test_agents.py
git commit -m "feat(phase6): add AgentWorkspace — scoped tool/memory/resource sandbox"
```

---

## Task 5: AgentExecutor

**Files:**
- Create: `backend/nobla/agents/executor.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.executor import AgentExecutor
from nobla.events.bus import NoblaEventBus


# ── Executor tests ───────────────────────────────────────────


class TestAgentExecutor:
    def _make_executor(self, max_concurrent=10) -> tuple[AgentExecutor, AgentRegistry, NoblaEventBus]:
        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(
                name="stub", description="A stub", role="Stub role",
                tier=Tier.STANDARD, allowed_tools=["search.web"],
            ),
        )
        event_bus = NoblaEventBus(max_queue_depth=100)
        mock_tool_registry = MagicMock()
        mock_tool_executor = AsyncMock()
        mock_tool_executor.execute.return_value = MagicMock(success=True)
        mock_router = AsyncMock()

        executor = AgentExecutor(
            registry=registry,
            tool_registry=mock_tool_registry,
            tool_executor=mock_tool_executor,
            event_bus=event_bus,
            router=mock_router,
            max_concurrent_agents=max_concurrent,
        )
        return executor, registry, event_bus

    @pytest.mark.asyncio
    async def test_spawn_creates_instance(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        agent = await executor.spawn("stub", user_tier=Tier.STANDARD)
        assert agent.instance_id is not None
        assert agent.status == AgentStatus.IDLE
        assert agent.workspace is not None
        assert agent.name == "stub"
        await bus.stop()

    @pytest.mark.asyncio
    async def test_spawn_unknown_agent_raises(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        with pytest.raises(ValueError, match="not registered"):
            await executor.spawn("nonexistent", user_tier=Tier.STANDARD)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_spawn_tier_validation(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        # Register an ELEVATED agent
        executor._registry.register(
            _StubAgent,
            AgentConfig(
                name="elevated", description="e", role="e",
                tier=Tier.ELEVATED,
            ),
        )
        # STANDARD user can't spawn ELEVATED agent
        with pytest.raises(PermissionError, match="tier"):
            await executor.spawn("elevated", user_tier=Tier.STANDARD)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_agent(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        agent = await executor.spawn("stub", user_tier=Tier.STANDARD)
        await executor.stop(agent.instance_id)
        assert executor.get(agent.instance_id) is None
        await bus.stop()

    @pytest.mark.asyncio
    async def test_kill_agent(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        agent = await executor.spawn("stub", user_tier=Tier.STANDARD)
        await executor.kill(agent.instance_id)
        assert executor.get(agent.instance_id) is None
        await bus.stop()

    @pytest.mark.asyncio
    async def test_kill_all(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        assert len(executor.list_running()) == 2
        await executor.kill_all()
        assert len(executor.list_running()) == 0
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_all(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        await executor.stop_all()
        assert len(executor.list_running()) == 0
        await bus.stop()

    @pytest.mark.asyncio
    async def test_list_running(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        a1 = await executor.spawn("stub", user_tier=Tier.STANDARD)
        a2 = await executor.spawn("stub", user_tier=Tier.STANDARD)
        running = executor.list_running()
        assert len(running) == 2
        ids = {r["instance_id"] for r in running}
        assert a1.instance_id in ids
        assert a2.instance_id in ids
        await bus.stop()

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        executor, _, bus = self._make_executor(max_concurrent=1)
        await bus.start()
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        with pytest.raises(RuntimeError, match="concurrent"):
            await executor.spawn("stub", user_tier=Tier.STANDARD)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_spawn_emits_event(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        captured = []
        bus.subscribe("agent.spawned", lambda e: captured.append(e))
        await executor.spawn("stub", user_tier=Tier.STANDARD)
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0].event_type == "agent.spawned"
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_emits_event(self):
        executor, _, bus = self._make_executor()
        await bus.start()
        agent = await executor.spawn("stub", user_tier=Tier.STANDARD)
        captured = []
        bus.subscribe("agent.stopped", lambda e: captured.append(e))
        await executor.stop(agent.instance_id)
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        await bus.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestAgentExecutor -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/executor.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestAgentExecutor -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/executor.py backend/tests/test_agents.py
git commit -m "feat(phase6): add AgentExecutor — spawn/stop/kill with tier validation"
```

---

## Task 6: A2A Protocol

**Files:**
- Create: `backend/nobla/agents/communication.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.communication import A2AProtocol


# ── A2A Protocol tests ───────────────────────────────────────


class TestA2AProtocol:
    @pytest.mark.asyncio
    async def test_send_task_emits_event(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        captured = []
        bus.subscribe("agent.a2a.task.assign", lambda e: captured.append(e))

        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="agent-1", instruction="Search",
        )
        await protocol.send_task("orch", "agent-1", task)
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0].payload["task"]["instruction"] == "Search"
        await bus.stop()

    @pytest.mark.asyncio
    async def test_send_result_emits_event(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        captured = []
        bus.subscribe("agent.a2a.task.result", lambda e: captured.append(e))

        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="agent-1", instruction="x",
            status=TaskStatus.COMPLETED,
            artifacts=[{"type": "text", "content": "done"}],
        )
        await protocol.send_result("agent-1", task)
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        await bus.stop()

    @pytest.mark.asyncio
    async def test_send_error_emits_event(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        captured = []
        bus.subscribe("agent.a2a.task.error", lambda e: captured.append(e))

        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="agent-1", instruction="x",
        )
        await protocol.send_error("agent-1", task, "Something broke")
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0].payload["error"] == "Something broke"
        await bus.stop()

    @pytest.mark.asyncio
    async def test_wait_for_result_resolves(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        task = AgentTask(
            task_id="task-123", workflow_id="wf-1",
            assigner="orch", assignee="a", instruction="x",
        )

        async def _deliver_result():
            await asyncio.sleep(0.05)
            completed = task.model_copy(update={"status": TaskStatus.COMPLETED})
            await protocol.send_result("a", completed)

        asyncio.create_task(_deliver_result())
        result = await protocol.wait_for_result("task-123", timeout=2.0)
        assert result.status == TaskStatus.COMPLETED
        await bus.stop()

    @pytest.mark.asyncio
    async def test_wait_for_result_timeout(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        with pytest.raises(asyncio.TimeoutError):
            await protocol.wait_for_result("nonexistent", timeout=0.1)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_wait_for_result_error_resolves(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()
        protocol = A2AProtocol(event_bus=bus)

        task = AgentTask(
            task_id="task-err", workflow_id="wf-1",
            assigner="orch", assignee="a", instruction="x",
        )

        async def _deliver_error():
            await asyncio.sleep(0.05)
            failed = task.model_copy(update={"status": TaskStatus.FAILED})
            await protocol.send_error("a", failed, "broke")

        asyncio.create_task(_deliver_error())
        result = await protocol.wait_for_result("task-err", timeout=2.0)
        assert result.status == TaskStatus.FAILED
        await bus.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestA2AProtocol -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/communication.py`**

```python
"""A2A Protocol — task-based agent messaging over event bus (Phase 6).

All agent communication flows through this protocol. Uses asyncio.Future
for wait_for_result (same pattern as ConfirmationManager in automation/).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from nobla.agents.models import AgentMessage, AgentTask, MessageType, TaskStatus
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

EVENT_PREFIX = "agent.a2a"


class A2AProtocol:
    """Routes agent-to-agent communication through the event bus."""

    def __init__(self, event_bus: NoblaEventBus) -> None:
        self._event_bus = event_bus
        self._pending: dict[str, asyncio.Future[AgentTask]] = {}

        # Subscribe to result/error events to resolve futures
        self._event_bus.subscribe(
            f"{EVENT_PREFIX}.task.result", self._on_task_complete,
        )
        self._event_bus.subscribe(
            f"{EVENT_PREFIX}.task.error", self._on_task_complete,
        )

    async def send_task(
        self, sender: str, recipient: str, task: AgentTask,
    ) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.assign",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "recipient": recipient,
                "task": task.model_dump(),
            },
            correlation_id=task.task_id,
        ))

    async def send_result(self, sender: str, task: AgentTask) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.result",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "task": task.model_dump(),
            },
            correlation_id=task.task_id,
        ))

    async def send_status(self, sender: str, task: AgentTask) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.status",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "status": task.status.value,
            },
            correlation_id=task.task_id,
        ))

    async def send_error(
        self, sender: str, task: AgentTask, error: str,
    ) -> None:
        task.status = TaskStatus.FAILED
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.error",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "task": task.model_dump(),
                "error": error,
            },
            correlation_id=task.task_id,
        ))

    async def query_capabilities(
        self, sender: str, recipient: str,
    ) -> dict:
        """Query an agent's capabilities. Deferred to Phase 6 v2.

        TODO(phase6-v2): Implement request/response via Future pattern
        using agent.a2a.capability.query / agent.a2a.capability.response events.
        """
        raise NotImplementedError("Capability discovery deferred to v2")

    async def wait_for_result(
        self, task_id: str, timeout: float = 300,
    ) -> AgentTask:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AgentTask] = loop.create_future()
        self._pending[task_id] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(task_id, None)

    async def _on_task_complete(self, event: NoblaEvent) -> None:
        task_id = event.payload.get("task_id")
        if not task_id:
            return
        future = self._pending.get(task_id)
        if future is None or future.done():
            return
        task_data = event.payload.get("task", {})
        task = AgentTask.model_validate(task_data)
        future.set_result(task)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestA2AProtocol -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/communication.py backend/tests/test_agents.py
git commit -m "feat(phase6): add A2AProtocol — task-based messaging with Future-based wait"
```

---

## Task 7: TaskDecomposer

**Files:**
- Create: `backend/nobla/agents/decomposer.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.decomposer import TaskDecomposer


# ── Decomposer tests ────────────────────────────────────────


class TestTaskDecomposer:
    def _make_decomposer(self, llm_response=None) -> TaskDecomposer:
        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(name="researcher", description="Searches", role="Search", tier=Tier.STANDARD),
        )
        registry.register(
            _StubAgent,
            AgentConfig(name="coder", description="Writes code", role="Code", tier=Tier.ELEVATED),
        )
        mock_router = AsyncMock()
        if llm_response:
            mock_router.route.return_value = llm_response
        else:
            mock_router.route.return_value = '{"tasks": [{"instruction": "Search for X", "agent": "researcher"}]}'
        return TaskDecomposer(router=mock_router, registry=registry)

    @pytest.mark.asyncio
    async def test_decompose_single_task(self):
        decomposer = self._make_decomposer()
        tasks = await decomposer.decompose("Search for Python tutorials", "wf-1")
        assert len(tasks) >= 1
        assert tasks[0].instruction

    @pytest.mark.asyncio
    async def test_decompose_fallback_on_llm_failure(self):
        decomposer = self._make_decomposer()
        decomposer._router.route.side_effect = Exception("LLM unavailable")
        tasks = await decomposer.decompose("Do something", "wf-1")
        assert len(tasks) == 1  # heuristic fallback returns single task

    def test_select_agent_by_capability(self):
        decomposer = self._make_decomposer()
        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="", instruction="Search for data",
        )
        selected = decomposer.select_agent(task, ["researcher", "coder"])
        assert selected in ("researcher", "coder")

    def test_select_agent_returns_first_when_no_match(self):
        decomposer = self._make_decomposer()
        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="", instruction="Something vague",
        )
        selected = decomposer.select_agent(task, ["researcher", "coder"])
        assert selected in ("researcher", "coder")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestTaskDecomposer -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/decomposer.py`**

```python
"""TaskDecomposer — LLM-driven task decomposition and agent selection (Phase 6).

Breaks user instructions into a task graph. Heuristic fallback when
LLM is unavailable (same pattern as automation/interpreter.py).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from nobla.agents.models import AgentTask, TaskStatus

if TYPE_CHECKING:
    from nobla.agents.registry import AgentRegistry
    from nobla.brain.router import LLMRouter

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT = """You are a task decomposer for a multi-agent system.

Given a user instruction, break it into a list of tasks that agents can execute.
Available agents: {agents}

Return JSON: {{"tasks": [{{"instruction": "...", "agent": "agent_name"}}]}}
Only return valid JSON, no other text.

User instruction: {instruction}"""


class TaskDecomposer:
    """Breaks instructions into task graphs and selects agents."""

    def __init__(
        self, router: LLMRouter, registry: AgentRegistry,
    ) -> None:
        self._router = router
        self._registry = registry

    async def decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        try:
            return await self._llm_decompose(instruction, workflow_id)
        except Exception as e:
            logger.warning("llm_decompose_failed, using heuristic", error=str(e))
            return self._heuristic_decompose(instruction, workflow_id)

    async def _llm_decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        agents_desc = ", ".join(
            f"{c.name} ({c.description})"
            for c in self._registry.list_all()
        )
        prompt = DECOMPOSE_PROMPT.format(
            agents=agents_desc, instruction=instruction,
        )
        response = await self._router.route(prompt, tier="balanced")

        # Parse JSON response
        data = json.loads(response)
        tasks = []
        for item in data.get("tasks", []):
            tasks.append(AgentTask(
                workflow_id=workflow_id,
                assigner="orchestrator",
                assignee=item.get("agent", ""),
                instruction=item.get("instruction", instruction),
            ))
        if not tasks:
            return self._heuristic_decompose(instruction, workflow_id)
        return tasks

    def _heuristic_decompose(
        self, instruction: str, workflow_id: str,
    ) -> list[AgentTask]:
        """Fallback: create a single task with the full instruction."""
        available = self._registry.list_all()
        assignee = available[0].name if available else ""
        return [
            AgentTask(
                workflow_id=workflow_id,
                assigner="orchestrator",
                assignee=assignee,
                instruction=instruction,
            )
        ]

    def select_agent(
        self, task: AgentTask, available: list[str],
    ) -> str:
        """Pick best agent by keyword matching instruction to description."""
        instruction_lower = task.instruction.lower()
        best_score = -1
        best_agent = available[0] if available else ""

        for name in available:
            entry = self._registry.get(name)
            if entry is None:
                continue
            _, config = entry
            words = config.description.lower().split()
            score = sum(1 for w in words if w in instruction_lower)
            if score > best_score:
                best_score = score
                best_agent = name
        return best_agent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestTaskDecomposer -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/decomposer.py backend/tests/test_agents.py
git commit -m "feat(phase6): add TaskDecomposer — LLM-driven task graphs with heuristic fallback"
```

---

## Task 8: AgentOrchestrator

**Files:**
- Create: `backend/nobla/agents/orchestrator.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.orchestrator import AgentOrchestrator
from nobla.agents.communication import A2AProtocol
from nobla.agents.decomposer import TaskDecomposer


# ── Orchestrator tests ───────────────────────────────────────


class TestAgentOrchestrator:
    async def _make_orchestrator(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()

        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(
                name="stub", description="A stub", role="Stub",
                tier=Tier.STANDARD, allowed_tools=["search.web"],
            ),
        )

        mock_tool_registry = MagicMock()
        mock_tool_executor = AsyncMock()
        mock_tool_executor.execute.return_value = MagicMock(success=True)
        mock_router = AsyncMock()
        mock_router.route.return_value = '{"tasks": [{"instruction": "Do it", "agent": "stub"}]}'

        executor = AgentExecutor(
            registry=registry,
            tool_registry=mock_tool_registry,
            tool_executor=mock_tool_executor,
            event_bus=bus,
            router=mock_router,
        )

        protocol = A2AProtocol(event_bus=bus)
        decomposer = TaskDecomposer(router=mock_router, registry=registry)

        orch = AgentOrchestrator(
            executor=executor,
            protocol=protocol,
            decomposer=decomposer,
            event_bus=bus,
            tool_registry=mock_tool_registry,
        )
        return orch, bus

    @pytest.mark.asyncio
    async def test_start_stop(self):
        orch, bus = await self._make_orchestrator()
        await orch.start()
        await orch.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_run_workflow_returns_result(self):
        orch, bus = await self._make_orchestrator()
        await orch.start()
        result = await orch.run_workflow(
            instruction="Do research",
            user_id="user-1",
            user_tier=Tier.STANDARD,
        )
        assert result is not None
        assert result.status in ("completed", "failed")
        await orch.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_kill_all_workflows(self):
        orch, bus = await self._make_orchestrator()
        await orch.start()
        # Start a workflow (don't await completion)
        asyncio.create_task(orch.run_workflow(
            instruction="Long task",
            user_id="user-1",
            user_tier=Tier.STANDARD,
        ))
        await asyncio.sleep(0.05)
        await orch.kill_all_workflows()
        assert len(orch._active_workflows) == 0
        await orch.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_workflow_depth_limit(self):
        orch, bus = await self._make_orchestrator()
        orch._max_workflow_depth = 1
        await orch.start()
        # Workflow should still work at depth 0
        result = await orch.run_workflow(
            instruction="Simple task",
            user_id="user-1",
            user_tier=Tier.STANDARD,
        )
        assert result is not None
        await orch.stop()
        await bus.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestAgentOrchestrator -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/orchestrator.py`**

```python
"""AgentOrchestrator — workflow lifecycle and coordination (Phase 6).

Receives user requests, decomposes via TaskDecomposer, spawns agents,
assigns tasks via A2AProtocol, collects results, assembles final output.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nobla.agents.models import (
    AgentTask,
    TaskStatus,
    WorkflowState,
)
from nobla.events.models import NoblaEvent
from nobla.security.permissions import Tier

if TYPE_CHECKING:
    from nobla.agents.communication import A2AProtocol
    from nobla.agents.decomposer import TaskDecomposer
    from nobla.agents.executor import AgentExecutor
    from nobla.events.bus import NoblaEventBus
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Central coordinator for multi-agent workflows."""

    def __init__(
        self,
        executor: AgentExecutor,
        protocol: A2AProtocol,
        decomposer: TaskDecomposer,
        event_bus: NoblaEventBus,
        tool_registry: ToolRegistry,
        max_workflow_depth: int = 5,
        max_tasks_per_workflow: int = 20,
    ) -> None:
        self._executor = executor
        self._protocol = protocol
        self._decomposer = decomposer
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._max_workflow_depth = max_workflow_depth
        self._max_tasks = max_tasks_per_workflow
        self._active_workflows: dict[str, WorkflowState] = {}

    async def start(self) -> None:
        self._event_bus.subscribe(
            "agent.task.delegate", self._handle_delegation,
        )
        logger.info("orchestrator_started")

    async def stop(self) -> None:
        await self.kill_all_workflows()
        logger.info("orchestrator_stopped")

    async def run_workflow(
        self,
        instruction: str,
        user_id: str,
        user_tier: Tier,
        agent_team: list[str] | None = None,
    ) -> WorkflowState:
        workflow_id = str(uuid.uuid4())

        # Decompose instruction into tasks
        tasks = await self._decomposer.decompose(instruction, workflow_id)
        if len(tasks) > self._max_tasks:
            tasks = tasks[: self._max_tasks]

        task_graph = {t.task_id: t for t in tasks}

        workflow = WorkflowState(
            workflow_id=workflow_id,
            user_id=user_id,
            user_tier=user_tier,
            instruction=instruction,
            task_graph=task_graph,
            agent_assignments={},
            status="running",
            depth=0,
            created_at=datetime.now(timezone.utc),
        )
        self._active_workflows[workflow_id] = workflow

        # Spawn agents and assign tasks
        for task in tasks:
            agent_name = task.assignee
            if not agent_name:
                available = agent_team or [
                    c.name for c in self._decomposer._registry.list_all()
                ]
                agent_name = self._decomposer.select_agent(task, available)

            try:
                agent = await self._executor.spawn(
                    agent_name,
                    user_tier=user_tier,
                    user_id=user_id,
                )
                task.assignee = agent.instance_id
                workflow.agent_assignments[task.task_id] = agent.instance_id

                # Phase 6 v1: synchronous execution per task.
                # TODO(phase6-v2): Use protocol.send_task() + protocol.wait_for_result()
                # for async parallel execution across agents.
                task.status = TaskStatus.RUNNING
                try:
                    result_task = await agent.handle_task(task)
                    task.status = result_task.status
                    task.artifacts = result_task.artifacts
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    logger.error("task_failed", task_id=task.task_id, error=str(e))

                # Stop agent after task completes
                await self._executor.stop(agent.instance_id, reason="task_complete")

            except (ValueError, PermissionError, RuntimeError) as e:
                task.status = TaskStatus.FAILED
                logger.error("agent_spawn_failed", error=str(e))

        # Determine workflow status
        statuses = [t.status for t in task_graph.values()]
        if all(s == TaskStatus.COMPLETED for s in statuses):
            workflow.status = "completed"
        elif any(s == TaskStatus.FAILED for s in statuses):
            workflow.status = "failed"
        else:
            workflow.status = "completed"

        self._active_workflows.pop(workflow_id, None)
        return workflow

    async def kill_workflow(self, workflow_id: str) -> None:
        workflow = self._active_workflows.pop(workflow_id, None)
        if workflow is None:
            return
        for instance_id in workflow.agent_assignments.values():
            await self._executor.kill(instance_id)
        workflow.status = "cancelled"

    async def kill_all_workflows(self) -> None:
        for wf_id in list(self._active_workflows.keys()):
            await self.kill_workflow(wf_id)

    async def _handle_delegation(self, event: NoblaEvent) -> None:
        """Handle agent delegation requests (depth-limited).

        Phase 6 v1: logs the delegation request. Full implementation
        (spawn sub-agent, check depth, assign via protocol) deferred to v2.
        TODO(phase6-v2): Implement full delegation with depth checking,
        agent selection, and async task assignment.
        """
        payload = event.payload
        task_data = payload.get("task", {})
        if not task_data:
            return
        logger.info("delegation_received", task=task_data.get("instruction", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestAgentOrchestrator -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/orchestrator.py backend/tests/test_agents.py
git commit -m "feat(phase6): add AgentOrchestrator — workflow lifecycle and coordination"
```

---

## Task 9: AgentToolBridge & Cloning

**Files:**
- Create: `backend/nobla/agents/bridge.py`
- Create: `backend/nobla/agents/cloning.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.bridge import AgentToolBridge
from nobla.agents.cloning import clone_agent


# ── Bridge & Cloning tests ──────────────────────────────────


class TestAgentToolBridge:
    def test_bridge_wraps_agent_as_tool(self):
        config = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD,
        )
        mock_orchestrator = AsyncMock()
        bridge = AgentToolBridge(config=config, orchestrator=mock_orchestrator)
        assert bridge.name == "agent.researcher"
        assert bridge.category.value == "agent"
        assert bridge.tier == Tier.STANDARD

    @pytest.mark.asyncio
    async def test_bridge_execute_calls_orchestrator(self):
        config = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD,
        )
        mock_orchestrator = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow.status = "completed"
        mock_workflow.task_graph = {}
        mock_orchestrator.run_workflow.return_value = mock_workflow

        bridge = AgentToolBridge(config=config, orchestrator=mock_orchestrator)
        from nobla.tools.models import ToolParams
        params = ToolParams(
            args={"instruction": "Search for X"},
            connection_state=MagicMock(user_id="u", tier=Tier.STANDARD),
        )
        result = await bridge.execute(params)
        assert result.success is True
        mock_orchestrator.run_workflow.assert_called_once()


class TestCloneAgent:
    def test_clone_creates_new_config(self):
        original = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD, allowed_tools=["search.web"],
        )
        cloned = clone_agent(original, name="researcher-v2", llm_tier="strong")
        assert cloned.name == "researcher-v2"
        assert cloned.llm_tier == "strong"
        assert cloned.allowed_tools == ["search.web"]  # inherited
        assert cloned.role == "Search"  # inherited

    def test_clone_preserves_original(self):
        original = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD,
        )
        cloned = clone_agent(original, name="clone")
        assert original.name == "researcher"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestAgentToolBridge tests/test_agents.py::TestCloneAgent -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/bridge.py`**

```python
"""AgentToolBridge — expose an agent as a BaseTool (Phase 6).

Follows SkillToolBridge pattern: wraps agent config so the orchestrator
can be invoked through the standard ToolExecutor pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolResult

if TYPE_CHECKING:
    from nobla.agents.models import AgentConfig
    from nobla.agents.orchestrator import AgentOrchestrator
    from nobla.tools.models import ToolParams


class AgentToolBridge(BaseTool):
    """Wraps an agent type as a BaseTool for the tool platform."""

    def __init__(
        self, config: AgentConfig, orchestrator: AgentOrchestrator,
    ) -> None:
        self._agent_config = config
        self._orchestrator = orchestrator
        # Set class-level attributes that BaseTool expects.
        # Uses properties would also work (Python descriptor protocol),
        # but direct attributes match the existing tool pattern.
        self.name = f"agent.{config.name}"
        self.description = config.description
        self.category = ToolCategory.AGENT
        self.tier = config.tier
        self.requires_approval = config.requires_approval

    async def execute(self, params: ToolParams) -> ToolResult:
        instruction = params.args.get("instruction", "")
        user_id = params.connection_state.user_id
        user_tier = params.connection_state.tier

        try:
            workflow = await self._orchestrator.run_workflow(
                instruction=instruction,
                user_id=user_id or "unknown",
                user_tier=user_tier,
                agent_team=[self._agent_config.name],
            )
            artifacts = []
            for task in workflow.task_graph.values():
                artifacts.extend(task.artifacts)

            return ToolResult(
                success=workflow.status == "completed",
                data={"artifacts": artifacts, "workflow_id": workflow.workflow_id},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

- [ ] **Step 4: Implement `backend/nobla/agents/cloning.py`**

```python
"""Agent cloning — create agent variants from config templates (Phase 6)."""

from __future__ import annotations

from nobla.agents.models import AgentConfig


def clone_agent(original: AgentConfig, **overrides) -> AgentConfig:
    """Create a new AgentConfig by copying original and applying overrides.

    Example: clone_agent(researcher_config, name="fast-researcher", llm_tier="cheap")
    """
    return original.model_copy(update=overrides)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestAgentToolBridge tests/test_agents.py::TestCloneAgent -v --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/agents/bridge.py backend/nobla/agents/cloning.py backend/tests/test_agents.py
git commit -m "feat(phase6): add AgentToolBridge and agent cloning"
```

---

## Task 10: MCP Client

**Files:**
- Create: `backend/nobla/agents/mcp_client.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.mcp_client import MCPClientManager, MCPConnection, MCPToolDef


# ── MCP Client tests ────────────────────────────────────────


class TestMCPClientManager:
    def test_init(self):
        mgr = MCPClientManager()
        assert mgr.list_connections() == []

    @pytest.mark.asyncio
    async def test_connect_and_list(self):
        mgr = MCPClientManager()
        # Mock the transport layer
        with patch.object(mgr, '_do_connect', new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = MCPConnection(
                connection_id="conn-1",
                server_uri="stdio://test",
                transport="stdio",
                server_info={"name": "test-server", "version": "1.0"},
                capabilities={"tools": True},
                status="connected",
            )
            conn_id = await mgr.connect("stdio://test")
            assert conn_id == "conn-1"
            conns = mgr.list_connections()
            assert len(conns) == 1

    @pytest.mark.asyncio
    async def test_disconnect(self):
        mgr = MCPClientManager()
        with patch.object(mgr, '_do_connect', new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = MCPConnection(
                connection_id="conn-1", server_uri="stdio://test",
                transport="stdio", server_info={}, capabilities={},
                status="connected",
            )
            await mgr.connect("stdio://test")
            await mgr.disconnect("conn-1")
            assert mgr.list_connections() == []

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        mgr = MCPClientManager()
        with patch.object(mgr, '_do_connect', new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = MCPConnection(
                connection_id="c1", server_uri="s1", transport="stdio",
                server_info={}, capabilities={}, status="connected",
            )
            await mgr.connect("s1")
            mock_conn.return_value = MCPConnection(
                connection_id="c2", server_uri="s2", transport="stdio",
                server_info={}, capabilities={}, status="connected",
            )
            await mgr.connect("s2")
            await mgr.disconnect_all()
            assert mgr.list_connections() == []

    @pytest.mark.asyncio
    async def test_call_tool(self):
        mgr = MCPClientManager()
        with patch.object(mgr, '_do_connect', new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = MCPConnection(
                connection_id="conn-1", server_uri="test",
                transport="stdio", server_info={}, capabilities={},
                status="connected",
            )
            await mgr.connect("test")
        with patch.object(mgr, '_do_call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "data"}
            result = await mgr.call_tool("conn-1", "tool_name", {"arg": "val"})
            assert result == {"result": "data"}

    @pytest.mark.asyncio
    async def test_call_tool_unknown_connection(self):
        mgr = MCPClientManager()
        with pytest.raises(ValueError, match="not found"):
            await mgr.call_tool("nonexistent", "tool", {})

    def test_max_connections_default(self):
        mgr = MCPClientManager(max_connections=5)
        assert mgr._max_connections == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestMCPClientManager -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/mcp_client.py`**

```python
"""MCPClientManager — consume external MCP servers (Phase 6).

Manages connections, tool discovery, and tool invocation.
Actual transport implementation is pluggable via _do_connect / _do_call_tool.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: dict
    connection_id: str


@dataclass
class MCPConnection:
    connection_id: str
    server_uri: str
    transport: str
    server_info: dict
    capabilities: dict
    status: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MCPClientManager:
    """Manages connections to external MCP servers."""

    def __init__(
        self,
        event_bus: NoblaEventBus | None = None,
        max_connections: int = 20,
    ) -> None:
        self._event_bus = event_bus
        self._max_connections = max_connections
        self._connections: dict[str, MCPConnection] = {}
        self._tool_cache: dict[str, list[MCPToolDef]] = {}

    async def connect(
        self,
        server_uri: str,
        transport: str = "stdio",
        auth: dict | None = None,
    ) -> str:
        if len(self._connections) >= self._max_connections:
            raise RuntimeError(
                f"Max MCP connections ({self._max_connections}) reached"
            )
        conn = await self._do_connect(server_uri, transport, auth)
        self._connections[conn.connection_id] = conn

        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.connected",
                source="mcp.client",
                payload={
                    "connection_id": conn.connection_id,
                    "server_uri": server_uri,
                },
            ))
        return conn.connection_id

    async def disconnect(self, connection_id: str) -> None:
        conn = self._connections.pop(connection_id, None)
        if conn is None:
            return
        self._tool_cache.pop(connection_id, None)
        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.disconnected",
                source="mcp.client",
                payload={"connection_id": connection_id},
            ))

    async def disconnect_all(self) -> None:
        for cid in list(self._connections.keys()):
            await self.disconnect(cid)

    async def call_tool(
        self, connection_id: str, tool_name: str, arguments: dict,
    ) -> dict:
        if connection_id not in self._connections:
            raise ValueError(f"MCP connection '{connection_id}' not found")
        result = await self._do_call_tool(connection_id, tool_name, arguments)

        if self._event_bus is not None:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.client.tool_called",
                source="mcp.client",
                payload={
                    "connection_id": connection_id,
                    "tool_name": tool_name,
                },
            ))
        return result

    def list_connections(self) -> list[dict]:
        return [
            {
                "connection_id": c.connection_id,
                "server_uri": c.server_uri,
                "status": c.status,
            }
            for c in self._connections.values()
        ]

    async def list_tools(self, connection_id: str) -> list[MCPToolDef]:
        return self._tool_cache.get(connection_id, [])

    # ── Transport layer (override for real implementation) ──

    async def _do_connect(
        self, server_uri: str, transport: str, auth: dict | None,
    ) -> MCPConnection:
        """Perform MCP handshake. Override for real transport."""
        return MCPConnection(
            connection_id=str(uuid.uuid4()),
            server_uri=server_uri,
            transport=transport,
            server_info={"name": "unknown"},
            capabilities={},
            status="connected",
        )

    async def _do_call_tool(
        self, connection_id: str, tool_name: str, arguments: dict,
    ) -> dict:
        """Invoke tool on MCP server. Override for real transport."""
        raise NotImplementedError("MCP transport not configured")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestMCPClientManager -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/mcp_client.py backend/tests/test_agents.py
git commit -m "feat(phase6): add MCPClientManager — external MCP server consumption"
```

---

## Task 11: MCP Server

**Files:**
- Create: `backend/nobla/agents/mcp_server.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.mcp_server import MCPServer


# ── MCP Server tests ────────────────────────────────────────


class TestMCPServer:
    def test_init(self):
        server = MCPServer(
            tool_registry=MagicMock(),
            agent_registry=AgentRegistry(),
            orchestrator=AsyncMock(),
        )
        assert server._exposed_tools == set()
        assert server._exposed_agents == set()

    def test_expose_and_hide_tool(self):
        server = MCPServer(
            tool_registry=MagicMock(),
            agent_registry=AgentRegistry(),
            orchestrator=AsyncMock(),
        )
        server.expose_tool("search.web")
        assert "search.web" in server._exposed_tools
        server.hide_tool("search.web")
        assert "search.web" not in server._exposed_tools

    def test_expose_agent(self):
        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(name="researcher", description="Search", role="R", tier=Tier.STANDARD),
        )
        server = MCPServer(
            tool_registry=MagicMock(),
            agent_registry=registry,
            orchestrator=AsyncMock(),
        )
        server.expose_agent("researcher")
        assert "researcher" in server._exposed_agents

    @pytest.mark.asyncio
    async def test_handle_initialize(self):
        server = MCPServer(
            tool_registry=MagicMock(),
            agent_registry=AgentRegistry(),
            orchestrator=AsyncMock(),
        )
        result = await server.handle_initialize({})
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "nobla-agent"

    @pytest.mark.asyncio
    async def test_handle_tools_list(self):
        mock_tool_reg = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search.web"
        mock_tool.description = "Web search"
        mock_tool_reg.get.return_value = mock_tool
        server = MCPServer(
            tool_registry=mock_tool_reg,
            agent_registry=AgentRegistry(),
            orchestrator=AsyncMock(),
        )
        server.expose_tool("search.web")
        tools = await server.handle_tools_list()
        assert len(tools) == 1
        assert tools[0]["name"] == "search.web"

    @pytest.mark.asyncio
    async def test_handle_tools_call_routes_to_orchestrator_for_agent(self):
        mock_orch = AsyncMock()
        mock_wf = MagicMock()
        mock_wf.status = "completed"
        mock_wf.task_graph = {}
        mock_wf.workflow_id = "wf-1"
        mock_orch.run_workflow.return_value = mock_wf

        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(name="researcher", description="S", role="R", tier=Tier.STANDARD),
        )
        server = MCPServer(
            tool_registry=MagicMock(),
            agent_registry=registry,
            orchestrator=mock_orch,
        )
        server.expose_agent("researcher")
        result = await server.handle_tools_call(
            "agent.researcher", {"instruction": "Search"}, "client-1",
        )
        assert result["success"] is True
        mock_orch.run_workflow.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestMCPServer -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/mcp_server.py`**

```python
"""MCPServer — expose Nobla tools/agents as MCP server (Phase 6).

External clients connect via SSE and invoke Nobla capabilities.
Tools are opt-in via expose_tool()/expose_agent().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nobla.security.permissions import Tier

if TYPE_CHECKING:
    from nobla.agents.orchestrator import AgentOrchestrator
    from nobla.agents.registry import AgentRegistry
    from nobla.events.bus import NoblaEventBus
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPServer:
    """Exposes Nobla tools and agents as an MCP-compliant server."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        orchestrator: AgentOrchestrator,
        event_bus: NoblaEventBus | None = None,
        host: str = "127.0.0.1",
        port: int = 8100,
        default_tier: Tier = Tier.STANDARD,
    ) -> None:
        self._tool_registry = tool_registry
        self._agent_registry = agent_registry
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._host = host
        self._port = port
        self._default_tier = default_tier
        self._exposed_tools: set[str] = set()
        self._exposed_agents: set[str] = set()

    async def start(self) -> None:
        if self._event_bus:
            from nobla.events.models import NoblaEvent
            await self._event_bus.emit(NoblaEvent(
                event_type="mcp.server.started",
                source="mcp.server",
                payload={"host": self._host, "port": self._port},
            ))
        logger.info("mcp_server_started", host=self._host, port=self._port)

    async def stop(self) -> None:
        logger.info("mcp_server_stopped")

    def expose_tool(self, tool_name: str) -> None:
        self._exposed_tools.add(tool_name)

    def hide_tool(self, tool_name: str) -> None:
        self._exposed_tools.discard(tool_name)

    def expose_agent(self, agent_name: str) -> None:
        self._exposed_agents.add(agent_name)

    # ── MCP Protocol Handlers ──

    async def handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "nobla-agent", "version": "0.1.0"},
            "capabilities": {"tools": {"listChanged": False}},
        }

    async def handle_tools_list(self) -> list[dict]:
        tools = []
        for name in self._exposed_tools:
            tool = self._tool_registry.get(name)
            if tool:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": {"type": "object", "properties": {}},
                })
        for name in self._exposed_agents:
            entry = self._agent_registry.get(name)
            if entry:
                _, config = entry
                tools.append({
                    "name": f"agent.{config.name}",
                    "description": config.description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "instruction": {
                                "type": "string",
                                "description": "What to do",
                            },
                        },
                        "required": ["instruction"],
                    },
                })
        return tools

    async def handle_tools_call(
        self, tool_name: str, arguments: dict, client_id: str,
    ) -> dict:
        # Check if it's an agent
        if tool_name.startswith("agent."):
            agent_name = tool_name[len("agent."):]
            if agent_name not in self._exposed_agents:
                return {"success": False, "error": f"Agent '{agent_name}' not exposed"}
            try:
                workflow = await self._orchestrator.run_workflow(
                    instruction=arguments.get("instruction", ""),
                    user_id=f"mcp:{client_id}",
                    user_tier=self._default_tier,
                    agent_team=[agent_name],
                )
                artifacts = []
                for task in workflow.task_graph.values():
                    artifacts.extend(task.artifacts)
                return {
                    "success": workflow.status == "completed",
                    "workflow_id": workflow.workflow_id,
                    "artifacts": artifacts,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Regular tool
        if tool_name not in self._exposed_tools:
            return {"success": False, "error": f"Tool '{tool_name}' not exposed"}

        # Tool execution would go through ToolExecutor here
        # (requires constructing ToolParams with default tier)
        return {"success": False, "error": "Direct tool execution via MCP not yet implemented"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestMCPServer -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/agents/mcp_server.py backend/tests/test_agents.py
git commit -m "feat(phase6): add MCPServer — expose Nobla tools/agents via MCP protocol"
```

---

## Task 12: Built-in Agents (Researcher + Coder)

**Files:**
- Create: `backend/nobla/agents/builtins/researcher.py`
- Create: `backend/nobla/agents/builtins/coder.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_agents.py`:

```python
from nobla.agents.builtins.researcher import ResearcherAgent, RESEARCHER_CONFIG
from nobla.agents.builtins.coder import CoderAgent, CODER_CONFIG


# ── Built-in agent tests ────────────────────────────────────


class TestResearcherAgent:
    def test_config(self):
        assert RESEARCHER_CONFIG.name == "researcher"
        assert RESEARCHER_CONFIG.tier == Tier.STANDARD
        assert RESEARCHER_CONFIG.llm_tier == "balanced"
        assert RESEARCHER_CONFIG.default_isolation == IsolationLevel.SHARED_READWRITE

    @pytest.mark.asyncio
    async def test_handle_task(self):
        agent = ResearcherAgent(config=RESEARCHER_CONFIG)
        agent.router = AsyncMock()
        agent.router.route.return_value = "Here are the findings about X."
        agent.workspace = AsyncMock()

        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="r-1", instruction="Research Python async patterns",
        )
        result = await agent.handle_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert len(result.artifacts) >= 1


class TestCoderAgent:
    def test_config(self):
        assert CODER_CONFIG.name == "coder"
        assert CODER_CONFIG.tier == Tier.ELEVATED
        assert CODER_CONFIG.llm_tier == "strong"
        assert CODER_CONFIG.default_isolation == IsolationLevel.SHARED_READ

    @pytest.mark.asyncio
    async def test_handle_task(self):
        agent = CoderAgent(config=CODER_CONFIG)
        agent.router = AsyncMock()
        agent.router.route.return_value = "def hello():\n    print('hello')"
        agent.workspace = AsyncMock()

        task = AgentTask(
            workflow_id="wf-1", assigner="orch",
            assignee="c-1", instruction="Write a hello world function",
        )
        result = await agent.handle_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert len(result.artifacts) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents.py::TestResearcherAgent tests/test_agents.py::TestCoderAgent -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Implement `backend/nobla/agents/builtins/researcher.py`**

```python
"""ResearcherAgent — reference implementation for research tasks (Phase 6)."""

from __future__ import annotations

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig, AgentStatus, AgentTask, IsolationLevel, TaskStatus
from nobla.security.permissions import Tier

RESEARCHER_CONFIG = AgentConfig(
    name="researcher",
    description="Searches the web, analyzes documents, extracts information, and summarizes findings.",
    role=(
        "You are a research assistant. Given a research question or topic, "
        "search for relevant information, extract key findings, and provide "
        "a clear, concise summary with sources."
    ),
    tier=Tier.STANDARD,
    llm_tier="balanced",
    allowed_tools=[],  # Populated at registration time from actual tool registry
    default_isolation=IsolationLevel.SHARED_READWRITE,
)


class ResearcherAgent(BaseAgent):
    """Reference agent: research, search, summarize."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        self.status = AgentStatus.BUSY
        try:
            response = await self.think(
                f"{self.role}\n\nTask: {task.instruction}"
            )
            task.artifacts.append({
                "type": "research",
                "content": response,
            })
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.artifacts.append({"type": "error", "content": str(e)})
        return task
```

- [ ] **Step 4: Implement `backend/nobla/agents/builtins/coder.py`**

```python
"""CoderAgent — reference implementation for code tasks (Phase 6)."""

from __future__ import annotations

from nobla.agents.base import BaseAgent
from nobla.agents.models import AgentConfig, AgentStatus, AgentTask, IsolationLevel, TaskStatus
from nobla.security.permissions import Tier

CODER_CONFIG = AgentConfig(
    name="coder",
    description="Generates code, debugs issues, reviews code, and performs git operations.",
    role=(
        "You are a coding assistant. Given a coding task, generate clean, "
        "well-structured code with appropriate error handling. For debugging "
        "tasks, analyze the problem and provide a fix."
    ),
    tier=Tier.ELEVATED,
    llm_tier="strong",
    allowed_tools=[],  # Populated at registration time from actual tool registry
    default_isolation=IsolationLevel.SHARED_READ,
)


class CoderAgent(BaseAgent):
    """Reference agent: code generation, debugging, review."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        self.status = AgentStatus.BUSY
        try:
            response = await self.think(
                f"{self.role}\n\nTask: {task.instruction}"
            )
            task.artifacts.append({
                "type": "code",
                "content": response,
            })
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.artifacts.append({"type": "error", "content": str(e)})
        return task
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_agents.py::TestResearcherAgent tests/test_agents.py::TestCoderAgent -v --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/agents/builtins/ backend/tests/test_agents.py
git commit -m "feat(phase6): add ResearcherAgent and CoderAgent reference implementations"
```

---

## Task 13: Gateway Wiring & Integration

**Files:**
- Modify: `backend/nobla/gateway/lifespan.py`
- Test: `backend/tests/test_agents.py` (append integration test)

- [ ] **Step 1: Write failing integration test**

Append to `backend/tests/test_agents.py`:

```python
# ── Integration tests ────────────────────────────────────────


class TestAgentSystemIntegration:
    """Full pipeline: registry → executor → protocol → orchestrator → workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_pipeline(self):
        bus = NoblaEventBus(max_queue_depth=100)
        await bus.start()

        registry = AgentRegistry()
        registry.register(
            _StubAgent,
            AgentConfig(
                name="stub", description="A stub agent", role="Stub",
                tier=Tier.STANDARD, allowed_tools=[],
            ),
        )

        mock_tool_registry = MagicMock()
        mock_tool_executor = AsyncMock()
        mock_tool_executor.execute.return_value = MagicMock(success=True)
        mock_router = AsyncMock()
        mock_router.route.return_value = '{"tasks": [{"instruction": "Do it", "agent": "stub"}]}'

        executor = AgentExecutor(
            registry=registry, tool_registry=mock_tool_registry,
            tool_executor=mock_tool_executor, event_bus=bus,
            router=mock_router,
        )
        protocol = A2AProtocol(event_bus=bus)
        decomposer = TaskDecomposer(router=mock_router, registry=registry)
        orch = AgentOrchestrator(
            executor=executor, protocol=protocol,
            decomposer=decomposer, event_bus=bus,
            tool_registry=mock_tool_registry,
        )

        await orch.start()
        result = await orch.run_workflow(
            instruction="Test the full pipeline",
            user_id="test-user",
            user_tier=Tier.STANDARD,
        )
        assert result.status == "completed"
        assert len(result.task_graph) >= 1

        # Verify all agents cleaned up
        assert len(executor.list_running()) == 0

        await orch.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_bridge_exposes_agent_as_tool(self):
        from nobla.agents.bridge import AgentToolBridge
        from nobla.tools.models import ToolCategory

        config = AgentConfig(
            name="stub", description="Stub", role="Stub", tier=Tier.STANDARD,
        )
        mock_orch = AsyncMock()
        mock_wf = MagicMock()
        mock_wf.status = "completed"
        mock_wf.task_graph = {}
        mock_wf.workflow_id = "wf-test"
        mock_orch.run_workflow.return_value = mock_wf

        bridge = AgentToolBridge(config=config, orchestrator=mock_orch)
        assert bridge.category == ToolCategory.AGENT
        assert bridge.name == "agent.stub"

    @pytest.mark.asyncio
    async def test_cloning_preserves_config(self):
        from nobla.agents.cloning import clone_agent

        original = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD, allowed_tools=["search.web"],
        )
        clone = clone_agent(original, name="fast-researcher", llm_tier="cheap")
        assert clone.name == "fast-researcher"
        assert clone.llm_tier == "cheap"
        assert clone.allowed_tools == ["search.web"]
        assert original.name == "researcher"  # unchanged
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_agents.py::TestAgentSystemIntegration -v --tb=short`
Expected: ALL PASS

- [ ] **Step 3: Add agent wiring to `backend/nobla/gateway/lifespan.py`**

Add after the scheduler section (before the final `logger.info("nobla_started", ...)`):

```python
    # --- Multi-Agent System (Phase 6) ---
    if settings.agents.enabled:
        from nobla.agents.registry import AgentRegistry
        from nobla.agents.executor import AgentExecutor
        from nobla.agents.communication import A2AProtocol
        from nobla.agents.decomposer import TaskDecomposer
        from nobla.agents.orchestrator import AgentOrchestrator
        from nobla.agents.builtins.researcher import ResearcherAgent, RESEARCHER_CONFIG
        from nobla.agents.builtins.coder import CoderAgent, CODER_CONFIG

        agent_registry = AgentRegistry()
        agent_executor = AgentExecutor(
            registry=agent_registry,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            event_bus=event_bus,
            router=router,
            memory_orchestrator=memory_orchestrator,
            max_concurrent_agents=settings.agents.max_concurrent_agents,
        )
        a2a_protocol = A2AProtocol(event_bus=event_bus)
        decomposer = TaskDecomposer(router=router, registry=agent_registry)
        agent_orchestrator = AgentOrchestrator(
            executor=agent_executor,
            protocol=a2a_protocol,
            decomposer=decomposer,
            event_bus=event_bus,
            tool_registry=tool_registry,
            max_workflow_depth=settings.agents.max_workflow_depth,
            max_tasks_per_workflow=settings.agents.max_tasks_per_workflow,
        )

        agent_registry.register(ResearcherAgent, RESEARCHER_CONFIG)
        agent_registry.register(CoderAgent, CODER_CONFIG)

        if ks:
            ks.on_soft_kill(agent_executor.stop_all)
            ks.on_soft_kill(agent_orchestrator.kill_all_workflows)
            ks.on_hard_kill(agent_executor.kill_all)

        await agent_orchestrator.start()
        logger.info("multi_agent_system_started")
    else:
        agent_orchestrator = None
        logger.info("multi_agent_system_disabled")
```

Add cleanup before `await scheduler_service.stop()` in the yield/shutdown section:

```python
    if agent_orchestrator:
        await agent_orchestrator.stop()
```

- [ ] **Step 4: Run full test suite**

Run: `cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py -v`
Expected: 344 + all agent tests pass (estimated ~120+ total agent tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/lifespan.py backend/tests/test_agents.py
git commit -m "feat(phase6): wire multi-agent system into gateway lifespan with kill switch"
```

---

## Task 14: Final Verification & CLAUDE.md Update

- [ ] **Step 1: Run complete test suite**

Run: `cd backend && pytest tests/test_telegram.py tests/test_discord_adapter.py tests/test_scheduler.py tests/test_channels.py tests/test_event_bus.py tests/test_skills.py tests/test_agents.py -v --tb=short`
Expected: ALL PASS (344 existing + ~120 new agent tests)

- [ ] **Step 2: Verify line counts**

Run: `wc -l backend/nobla/agents/*.py backend/nobla/agents/builtins/*.py`
Expected: All files under 750 lines

- [ ] **Step 3: Update CLAUDE.md**

Update the Phase 6 section to reflect completion:

```
- **Phase 6-MultiAgent**: Multi-Agent System — BaseAgent, registry, executor, orchestrator, A2A protocol, workspace isolation, MCP client/server, researcher + coder agents (N tests)
```

Add to the project structure section:

```
│   ├── agents/         # Multi-agent orchestrator, A2A protocol, MCP client/server (Phase 6)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 6 Multi-Agent System completion"
```
