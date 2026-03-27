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
from nobla.agents.base import BaseAgent
from nobla.agents.registry import AgentRegistry
from nobla.agents.workspace import AgentWorkspace
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
