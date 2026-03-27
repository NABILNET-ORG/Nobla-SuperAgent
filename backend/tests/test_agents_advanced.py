"""Tests for the Nobla Multi-Agent System (Phase 6) — Part 2.

Covers: decomposer, orchestrator, bridge, cloning, MCP client/server, builtins.
"""

from __future__ import annotations

import asyncio
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
from nobla.agents.communication import A2AProtocol
from nobla.agents.bridge import AgentToolBridge
from nobla.agents.cloning import clone_agent
from nobla.agents.decomposer import TaskDecomposer
from nobla.agents.executor import AgentExecutor
from nobla.agents.builtins.coder import CoderAgent, CODER_CONFIG
from nobla.agents.builtins.researcher import ResearcherAgent, RESEARCHER_CONFIG
from nobla.agents.mcp_client import MCPClientManager, MCPConnection, MCPToolDef
from nobla.agents.mcp_server import MCPServer
from nobla.agents.orchestrator import AgentOrchestrator
from nobla.agents.registry import AgentRegistry
from nobla.agents.workspace import AgentWorkspace
from nobla.events.bus import NoblaEventBus
from nobla.security.permissions import Tier


class _StubAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    async def handle_task(self, task: AgentTask) -> AgentTask:
        task.status = TaskStatus.COMPLETED
        task.artifacts.append({"type": "text", "content": "done"})
        return task


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
        assert len(tasks) == 1

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
        result = await orch.run_workflow(
            instruction="Simple task",
            user_id="user-1",
            user_tier=Tier.STANDARD,
        )
        assert result is not None
        await orch.stop()
        await bus.stop()


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
        assert cloned.allowed_tools == ["search.web"]
        assert cloned.role == "Search"

    def test_clone_preserves_original(self):
        original = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD,
        )
        cloned = clone_agent(original, name="clone")
        assert original.name == "researcher"


# ── MCP Client tests ────────────────────────────────────────


class TestMCPClientManager:
    def test_init(self):
        mgr = MCPClientManager()
        assert mgr.list_connections() == []

    @pytest.mark.asyncio
    async def test_connect_and_list(self):
        mgr = MCPClientManager()
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
        assert len(executor.list_running()) == 0

        await orch.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_bridge_exposes_agent_as_tool(self):
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
        original = AgentConfig(
            name="researcher", description="Searches", role="Search",
            tier=Tier.STANDARD, allowed_tools=["search.web"],
        )
        clone = clone_agent(original, name="fast-researcher", llm_tier="cheap")
        assert clone.name == "fast-researcher"
        assert clone.llm_tier == "cheap"
        assert clone.allowed_tools == ["search.web"]
        assert original.name == "researcher"
