"""Tests for Phase 6 v2 — parallel orchestration, delegation, capabilities, MCP transport.

Covers: topological sort, decomposer deps, parallel orchestrator, delegation,
capability discovery, StdioTransport, SSETransport, MCP server endpoints.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.agents.base import BaseAgent
from nobla.agents.communication import A2AProtocol
from nobla.agents.decomposer import TaskDecomposer
from nobla.agents.executor import AgentExecutor
from nobla.agents.mcp_client import (
    MCPClientManager,
    MCPConnection,
    MCPToolDef,
    MCPTransport,
    SSETransport,
    StdioTransport,
)
from nobla.agents.mcp_server import MCPServer
from nobla.agents.models import (
    AgentConfig,
    AgentTask,
    TaskStatus,
    WorkflowState,
    topological_sort_tasks,
)
from nobla.agents.orchestrator import AgentOrchestrator
from nobla.agents.registry import AgentRegistry
from nobla.events.bus import NoblaEventBus
from nobla.security.permissions import Tier


# ── Helpers ──


class _StubAgent(BaseAgent):
    async def handle_task(self, task: AgentTask) -> AgentTask:
        task.status = TaskStatus.COMPLETED
        task.artifacts.append({"type": "text", "content": "done"})
        return task


class _FailAgent(BaseAgent):
    async def handle_task(self, task: AgentTask) -> AgentTask:
        raise RuntimeError("intentional failure")


class _SlowAgent(BaseAgent):
    """Agent that records call order to verify parallelism."""

    call_log: list[str] = []

    async def handle_task(self, task: AgentTask) -> AgentTask:
        _SlowAgent.call_log.append(task.instruction)
        task.status = TaskStatus.COMPLETED
        return task


def _make_task(
    wf: str = "w1",
    instruction: str = "do something",
    task_id: str | None = None,
    depends_on: list[str] | None = None,
) -> AgentTask:
    t = AgentTask(
        workflow_id=wf,
        assigner="orchestrator",
        assignee="stub",
        instruction=instruction,
    )
    if task_id:
        t.task_id = task_id
    if depends_on:
        t.depends_on = depends_on
    return t


def _make_registry(*agents) -> AgentRegistry:
    reg = AgentRegistry()
    for cls, cfg in agents:
        reg.register(cls, cfg)
    return reg


_STUB_CFG = AgentConfig(
    name="stub", description="Stub agent", role="test", tier=Tier.STANDARD,
)
_FAIL_CFG = AgentConfig(
    name="fail", description="Fail agent", role="test", tier=Tier.STANDARD,
)


# ═══════════════════════════════════════════════════════════════
# 1. Topological Sort
# ═══════════════════════════════════════════════════════════════


class TestTopologicalSort:
    def test_empty(self):
        assert topological_sort_tasks([]) == []

    def test_single_task(self):
        t = _make_task()
        tiers = topological_sort_tasks([t])
        assert len(tiers) == 1
        assert tiers[0] == [t]

    def test_all_independent(self):
        """Tasks with no deps should be in one tier (parallel)."""
        tasks = [_make_task(instruction=f"t{i}") for i in range(4)]
        tiers = topological_sort_tasks(tasks)
        assert len(tiers) == 1
        assert len(tiers[0]) == 4

    def test_linear_chain(self):
        """A -> B -> C should produce 3 tiers."""
        a = _make_task(task_id="a", instruction="a")
        b = _make_task(task_id="b", instruction="b", depends_on=["a"])
        c = _make_task(task_id="c", instruction="c", depends_on=["b"])
        tiers = topological_sort_tasks([a, b, c])
        assert len(tiers) == 3
        assert tiers[0][0].task_id == "a"
        assert tiers[1][0].task_id == "b"
        assert tiers[2][0].task_id == "c"

    def test_diamond_dependency(self):
        """A -> B, A -> C, B+C -> D: 3 tiers, tier 1 has B and C."""
        a = _make_task(task_id="a")
        b = _make_task(task_id="b", depends_on=["a"])
        c = _make_task(task_id="c", depends_on=["a"])
        d = _make_task(task_id="d", depends_on=["b", "c"])
        tiers = topological_sort_tasks([a, b, c, d])
        assert len(tiers) == 3
        tier1_ids = {t.task_id for t in tiers[1]}
        assert tier1_ids == {"b", "c"}
        assert tiers[2][0].task_id == "d"

    def test_cycle_raises(self):
        a = _make_task(task_id="a", depends_on=["b"])
        b = _make_task(task_id="b", depends_on=["a"])
        with pytest.raises(ValueError, match="Cycle"):
            topological_sort_tasks([a, b])

    def test_missing_dep_raises(self):
        a = _make_task(task_id="a", depends_on=["nonexistent"])
        with pytest.raises(ValueError, match="unknown tasks"):
            topological_sort_tasks([a])

    def test_mixed_deps_and_independent(self):
        """Two independent + one dependent: 2 tiers."""
        a = _make_task(task_id="a")
        b = _make_task(task_id="b")
        c = _make_task(task_id="c", depends_on=["a"])
        tiers = topological_sort_tasks([a, b, c])
        assert len(tiers) == 2
        tier0_ids = {t.task_id for t in tiers[0]}
        assert tier0_ids == {"a", "b"}


# ═══════════════════════════════════════════════════════════════
# 2. Decomposer Dependency Awareness
# ═══════════════════════════════════════════════════════════════


class TestDecomposerDeps:
    def _make_decomposer(self, llm_response: str) -> TaskDecomposer:
        registry = _make_registry((_StubAgent, _STUB_CFG))
        router = AsyncMock()
        router.route = AsyncMock(return_value=llm_response)
        return TaskDecomposer(router, registry)

    @pytest.mark.asyncio
    async def test_llm_produces_dependencies(self):
        llm_json = json.dumps({"tasks": [
            {"id": "t1", "instruction": "research", "agent": "stub", "depends_on": []},
            {"id": "t2", "instruction": "code", "agent": "stub", "depends_on": ["t1"]},
        ]})
        d = self._make_decomposer(llm_json)
        tasks = await d.decompose("build feature", "wf1")

        assert len(tasks) == 2
        assert tasks[0].depends_on == []
        assert len(tasks[1].depends_on) == 1
        # depends_on should reference the real task_id of tasks[0]
        assert tasks[1].depends_on[0] == tasks[0].task_id

    @pytest.mark.asyncio
    async def test_llm_no_deps_all_parallel(self):
        llm_json = json.dumps({"tasks": [
            {"id": "t1", "instruction": "a", "agent": "stub"},
            {"id": "t2", "instruction": "b", "agent": "stub"},
        ]})
        d = self._make_decomposer(llm_json)
        tasks = await d.decompose("do both", "wf1")
        assert all(t.depends_on == [] for t in tasks)

    @pytest.mark.asyncio
    async def test_llm_invalid_dep_ignored(self):
        """Unknown dep id in LLM response should be silently skipped."""
        llm_json = json.dumps({"tasks": [
            {"id": "t1", "instruction": "a", "agent": "stub", "depends_on": ["ghost"]},
        ]})
        d = self._make_decomposer(llm_json)
        tasks = await d.decompose("test", "wf1")
        assert tasks[0].depends_on == []

    @pytest.mark.asyncio
    async def test_heuristic_fallback_no_deps(self):
        d = self._make_decomposer("")
        d._router.route = AsyncMock(side_effect=RuntimeError("LLM down"))
        tasks = await d.decompose("do thing", "wf1")
        assert len(tasks) == 1
        assert tasks[0].depends_on == []


# ═══════════════════════════════════════════════════════════════
# 3. Parallel Orchestrator
# ═══════════════════════════════════════════════════════════════


class TestParallelOrchestrator:
    def _build(self, registry=None):
        registry = registry or _make_registry((_StubAgent, _STUB_CFG))
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)
        router = AsyncMock()
        router.route = AsyncMock(return_value="ok")
        decomposer = TaskDecomposer(router, registry)
        tool_registry = MagicMock()
        tool_executor = MagicMock()
        executor = AgentExecutor(
            registry=registry,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            event_bus=bus,
            router=router,
        )
        orch = AgentOrchestrator(
            executor=executor,
            protocol=protocol,
            decomposer=decomposer,
            event_bus=bus,
            tool_registry=tool_registry,
        )
        return orch, decomposer, bus

    @pytest.mark.asyncio
    async def test_workflow_completes(self):
        orch, _, _ = self._build()
        await orch.start()
        wf = await orch.run_workflow("do stuff", "user1", Tier.STANDARD)
        assert wf.status == "completed"
        assert len(wf.task_graph) >= 1
        await orch.stop()

    @pytest.mark.asyncio
    async def test_parallel_independent_tasks(self):
        """Two independent tasks should both complete."""
        orch, decomposer, _ = self._build()
        await orch.start()

        # Override decomposer to return 2 independent tasks
        async def _two_tasks(instruction, workflow_id):
            return [
                AgentTask(workflow_id=workflow_id, assigner="orch", assignee="stub", instruction="a"),
                AgentTask(workflow_id=workflow_id, assigner="orch", assignee="stub", instruction="b"),
            ]
        decomposer.decompose = _two_tasks

        wf = await orch.run_workflow("parallel", "user1", Tier.STANDARD)
        assert wf.status == "completed"
        statuses = [t.status for t in wf.task_graph.values()]
        assert all(s == TaskStatus.COMPLETED for s in statuses)
        await orch.stop()

    @pytest.mark.asyncio
    async def test_dependency_cascade_failure(self):
        """If task A fails, task B (depends on A) should be marked failed."""
        reg = _make_registry(
            (_FailAgent, _FAIL_CFG),
            (_StubAgent, _STUB_CFG),
        )
        orch, decomposer, _ = self._build(registry=reg)
        await orch.start()

        t_a = AgentTask(
            task_id="a", workflow_id="w", assigner="orch",
            assignee="fail", instruction="will fail",
        )
        t_b = AgentTask(
            task_id="b", workflow_id="w", assigner="orch",
            assignee="stub", instruction="depends on a",
            depends_on=["a"],
        )

        async def _dep_tasks(instruction, workflow_id):
            t_a.workflow_id = workflow_id
            t_b.workflow_id = workflow_id
            return [t_a, t_b]
        decomposer.decompose = _dep_tasks

        wf = await orch.run_workflow("cascade", "user1", Tier.STANDARD)
        assert wf.status == "failed"
        assert t_a.status == TaskStatus.FAILED
        assert t_b.status == TaskStatus.FAILED
        await orch.stop()

    @pytest.mark.asyncio
    async def test_depth_parameter_set(self):
        orch, _, _ = self._build()
        await orch.start()
        wf = await orch.run_workflow("test", "u", Tier.STANDARD, depth=3)
        assert wf.depth == 3
        await orch.stop()

    @pytest.mark.asyncio
    async def test_task_limit_enforced(self):
        orch, decomposer, _ = self._build()
        orch._max_tasks = 2
        await orch.start()

        async def _many_tasks(instruction, workflow_id):
            return [
                AgentTask(workflow_id=workflow_id, assigner="orch", assignee="stub", instruction=f"t{i}")
                for i in range(5)
            ]
        decomposer.decompose = _many_tasks

        wf = await orch.run_workflow("lots", "u", Tier.STANDARD)
        assert len(wf.task_graph) == 2
        await orch.stop()


# ═══════════════════════════════════════════════════════════════
# 4. Depth-Limited Delegation
# ═══════════════════════════════════════════════════════════════


class TestDelegation:
    def _build_orch(self):
        reg = _make_registry((_StubAgent, _STUB_CFG))
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)
        router = AsyncMock()
        router.route = AsyncMock(return_value="ok")
        decomposer = TaskDecomposer(router, reg)
        tool_registry = MagicMock()
        executor = AgentExecutor(
            registry=reg, tool_registry=tool_registry,
            tool_executor=MagicMock(), event_bus=bus, router=router,
        )
        orch = AgentOrchestrator(
            executor=executor, protocol=protocol, decomposer=decomposer,
            event_bus=bus, tool_registry=tool_registry,
            max_workflow_depth=3,
        )
        return orch, bus

    @pytest.mark.asyncio
    async def test_find_agent_depth_unknown(self):
        orch, _ = self._build_orch()
        assert orch._find_agent_depth("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_find_agent_depth_in_workflow(self):
        orch, _ = self._build_orch()
        wf = WorkflowState(
            workflow_id="wf1", user_id="u", user_tier=Tier.STANDARD,
            instruction="test", task_graph={}, agent_assignments={"t1": "agent-42"},
            status="running", depth=2, created_at=datetime.now(timezone.utc),
        )
        orch._active_workflows["wf1"] = wf
        assert orch._find_agent_depth("agent-42") == 2

    @pytest.mark.asyncio
    async def test_find_agent_context_default(self):
        orch, _ = self._build_orch()
        uid, tier = orch._find_agent_context("unknown")
        assert uid == "system"
        assert tier == Tier.STANDARD

    @pytest.mark.asyncio
    async def test_find_agent_context_from_workflow(self):
        orch, _ = self._build_orch()
        wf = WorkflowState(
            workflow_id="wf1", user_id="alice", user_tier=Tier.ELEVATED,
            instruction="test", task_graph={}, agent_assignments={"t1": "a-1"},
            status="running", depth=0, created_at=datetime.now(timezone.utc),
        )
        orch._active_workflows["wf1"] = wf
        uid, tier = orch._find_agent_context("a-1")
        assert uid == "alice"
        assert tier == Tier.ELEVATED

    @pytest.mark.asyncio
    async def test_delegation_max_depth_rejected(self):
        orch, bus = self._build_orch()
        await orch.start()
        # Place agent at depth 2 (max is 3, so depth+1=3 >= max → reject)
        wf = WorkflowState(
            workflow_id="wf1", user_id="u", user_tier=Tier.STANDARD,
            instruction="parent", task_graph={},
            agent_assignments={"t": "deep-agent"},
            status="running", depth=2, created_at=datetime.now(timezone.utc),
        )
        orch._active_workflows["wf1"] = wf

        from nobla.events.models import NoblaEvent
        event = NoblaEvent(
            event_type="agent.task.delegate",
            source="agent.deep-agent",
            payload={
                "task": {"assigner": "deep-agent", "instruction": "delegate me"},
                "preferred_target": None,
            },
        )
        # Should silently return (depth exceeded)
        await orch._handle_delegation(event)
        # No new workflow created beyond the one we injected
        assert len(orch._active_workflows) == 1
        await orch.stop()

    @pytest.mark.asyncio
    async def test_delegation_succeeds_within_depth(self):
        orch, bus = self._build_orch()
        await orch.start()
        wf = WorkflowState(
            workflow_id="wf1", user_id="u", user_tier=Tier.STANDARD,
            instruction="parent", task_graph={},
            agent_assignments={"t": "shallow-agent"},
            status="running", depth=0, created_at=datetime.now(timezone.utc),
        )
        orch._active_workflows["wf1"] = wf

        from nobla.events.models import NoblaEvent
        event = NoblaEvent(
            event_type="agent.task.delegate",
            source="agent.shallow-agent",
            payload={
                "task": {"assigner": "shallow-agent", "instruction": "sub-task"},
                "preferred_target": "stub",
            },
        )
        # Should succeed (depth 0 + 1 = 1 < max 3)
        await orch._handle_delegation(event)
        # Original workflow still there (sub-workflow completed and was cleaned up)
        assert "wf1" in orch._active_workflows
        await orch.stop()


# ═══════════════════════════════════════════════════════════════
# 5. Capability Discovery
# ═══════════════════════════════════════════════════════════════


class TestCapabilityDiscovery:
    def test_base_agent_get_capabilities(self):
        agent = _StubAgent(_STUB_CFG)
        caps = agent.get_capabilities()
        assert caps["name"] == "stub"
        assert caps["role"] == "test"
        assert caps["description"] == "Stub agent"
        assert isinstance(caps["allowed_tools"], list)
        assert caps["llm_tier"] == "balanced"

    @pytest.mark.asyncio
    async def test_query_capabilities_future_resolves(self):
        """Directly resolve the pending future to verify the pattern."""
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)

        cid = "cap-orchestrator-responder"

        # Start query in background so it creates the future
        task = asyncio.create_task(
            protocol.query_capabilities("orchestrator", "responder", timeout=5),
        )
        await asyncio.sleep(0)  # yield to let task start

        # Simulate the response arriving via the event bus
        from nobla.events.models import NoblaEvent
        await protocol._on_capability_response(NoblaEvent(
            event_type="agent.a2a.capability.response",
            source="agent.responder",
            payload={"capabilities": {"role": "coder", "tools": ["code.run"]}},
            correlation_id=cid,
        ))

        caps = await task
        assert caps["role"] == "coder"
        assert "code.run" in caps["tools"]

    @pytest.mark.asyncio
    async def test_pending_caps_cleanup_on_resolve(self):
        """Future is removed from _pending_caps after resolution."""
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)
        cid = "cap-a-b"

        task = asyncio.create_task(
            protocol.query_capabilities("a", "b", timeout=5),
        )
        await asyncio.sleep(0)
        assert cid in protocol._pending_caps

        from nobla.events.models import NoblaEvent
        await protocol._on_capability_response(NoblaEvent(
            event_type="agent.a2a.capability.response",
            source="agent.b",
            payload={"capabilities": {}},
            correlation_id=cid,
        ))
        await task
        assert cid not in protocol._pending_caps

    @pytest.mark.asyncio
    async def test_query_capabilities_timeout(self):
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)
        with pytest.raises(asyncio.TimeoutError):
            await protocol.query_capabilities("a", "b", timeout=0.1)

    @pytest.mark.asyncio
    async def test_capability_response_handler_ignores_unknown(self):
        bus = NoblaEventBus()
        protocol = A2AProtocol(bus)
        from nobla.events.models import NoblaEvent
        # Should not raise — no matching pending future
        await protocol._on_capability_response(NoblaEvent(
            event_type="agent.a2a.capability.response",
            source="agent.x",
            payload={"capabilities": {}},
            correlation_id="no-match",
        ))


# ═══════════════════════════════════════════════════════════════
# 6. MCP Transport — StdioTransport
# ═══════════════════════════════════════════════════════════════


class TestStdioTransport:
    def test_is_mcp_transport(self):
        assert issubclass(StdioTransport, MCPTransport)

    @pytest.mark.asyncio
    async def test_spawn_and_close(self):
        """Spawn a simple process and close it."""
        transport = await StdioTransport.spawn("python", ["-u", "-c", "pass"])
        assert transport._proc is not None
        await transport.close()
        # Process should be terminated
        assert transport._proc.returncode is not None

    @pytest.mark.asyncio
    async def test_send_request_and_read_response(self):
        """Spawn a process that echoes JSON-RPC responses."""
        echo_script = (
            "import sys, json\n"
            "for line in sys.stdin:\n"
            "    msg = json.loads(line)\n"
            "    resp = {'jsonrpc': '2.0', 'id': msg['id'], 'result': {'echo': msg['method']}}\n"
            "    sys.stdout.write(json.dumps(resp) + '\\n')\n"
            "    sys.stdout.flush()\n"
        )
        transport = await StdioTransport.spawn("python", ["-u", "-c", echo_script])
        try:
            result = await transport.send_request("test/hello", {"x": 1})
            assert result["echo"] == "test/hello"
        finally:
            await transport.close()

    @pytest.mark.asyncio
    async def test_send_request_error_response(self):
        """Process returns a JSON-RPC error."""
        err_script = (
            "import sys, json\n"
            "for line in sys.stdin:\n"
            "    msg = json.loads(line)\n"
            "    resp = {'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -1, 'message': 'boom'}}\n"
            "    sys.stdout.write(json.dumps(resp) + '\\n')\n"
            "    sys.stdout.flush()\n"
        )
        transport = await StdioTransport.spawn("python", ["-u", "-c", err_script])
        try:
            with pytest.raises(RuntimeError, match="boom"):
                await transport.send_request("fail")
        finally:
            await transport.close()


# ═══════════════════════════════════════════════════════════════
# 7. MCP Transport — SSETransport
# ═══════════════════════════════════════════════════════════════


class TestSSETransport:
    def test_is_mcp_transport(self):
        assert issubclass(SSETransport, MCPTransport)

    def test_url_resolution_absolute(self):
        t = SSETransport("http://localhost:8100")
        assert t._resolve_url("http://other/msg") == "http://other/msg"

    def test_url_resolution_relative(self):
        t = SSETransport("http://localhost:8100")
        resolved = t._resolve_url("/mcp/message")
        assert "localhost" in resolved
        assert "/mcp/message" in resolved

    def test_handle_message_resolves_future(self):
        t = SSETransport("http://localhost:8100")
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        t._pending[1] = future
        t._handle_message(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}))
        assert future.done()
        assert future.result() == {"ok": True}
        loop.close()

    def test_handle_message_error(self):
        t = SSETransport("http://localhost:8100")
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        t._pending[2] = future
        t._handle_message(json.dumps({
            "jsonrpc": "2.0", "id": 2,
            "error": {"code": -1, "message": "fail"},
        }))
        assert future.done()
        with pytest.raises(RuntimeError, match="fail"):
            future.result()
        loop.close()

    def test_handle_message_ignores_invalid_json(self):
        t = SSETransport("http://localhost:8100")
        t._handle_message("not json")  # should not raise

    def test_handle_message_ignores_unknown_id(self):
        t = SSETransport("http://localhost:8100")
        t._handle_message(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}))


# ═══════════════════════════════════════════════════════════════
# 8. MCP Server Endpoints
# ═══════════════════════════════════════════════════════════════


class TestMCPServerDispatch:
    def _make_server(self):
        tool_reg = MagicMock()
        agent_reg = AgentRegistry()
        agent_reg.register(_StubAgent, _STUB_CFG)
        orch = AsyncMock()
        bus = NoblaEventBus()
        server = MCPServer(
            tool_registry=tool_reg, agent_registry=agent_reg,
            orchestrator=orch, event_bus=bus,
        )
        return server

    @pytest.mark.asyncio
    async def test_dispatch_initialize(self):
        s = self._make_server()
        result = await s.dispatch("initialize", {}, "c1")
        assert result["protocolVersion"] == "2024-11-05"
        assert "serverInfo" in result

    @pytest.mark.asyncio
    async def test_dispatch_tools_list(self):
        s = self._make_server()
        s.expose_agent("stub")
        result = await s.dispatch("tools/list", {}, "c1")
        assert "tools" in result
        names = [t["name"] for t in result["tools"]]
        assert "agent.stub" in names

    @pytest.mark.asyncio
    async def test_dispatch_tools_call_agent(self):
        s = self._make_server()
        s.expose_agent("stub")
        wf_mock = MagicMock()
        wf_mock.status = "completed"
        wf_mock.workflow_id = "wf1"
        wf_mock.task_graph = {}
        s._orchestrator.run_workflow = AsyncMock(return_value=wf_mock)

        result = await s.dispatch(
            "tools/call",
            {"name": "agent.stub", "arguments": {"instruction": "test"}},
            "c1",
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_unknown_method(self):
        s = self._make_server()
        result = await s.dispatch("unknown/method", {}, "c1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_client_tracking(self):
        s = self._make_server()
        assert len(s._clients) == 0
        q = asyncio.Queue()
        s._clients["c1"] = q
        s._send_to_client("c1", {"test": True})
        msg = q.get_nowait()
        assert json.loads(msg)["test"] is True

    @pytest.mark.asyncio
    async def test_send_to_unknown_client(self):
        s = self._make_server()
        # Should not raise
        s._send_to_client("nonexistent", {"x": 1})

    def test_create_router_returns_api_router(self):
        s = self._make_server()
        router = s.create_router()
        from fastapi import APIRouter
        assert isinstance(router, APIRouter)

    @pytest.mark.asyncio
    async def test_stop_clears_clients(self):
        s = self._make_server()
        s._clients["c1"] = asyncio.Queue()
        s._clients["c2"] = asyncio.Queue()
        await s.stop()
        assert len(s._clients) == 0


# ═══════════════════════════════════════════════════════════════
# 9. MCPClientManager — transport dispatch
# ═══════════════════════════════════════════════════════════════


class TestMCPClientManagerTransport:
    @pytest.mark.asyncio
    async def test_connect_fallback_mock(self):
        """Unknown transport falls back to mock connection."""
        mgr = MCPClientManager()
        cid = await mgr.connect("test://server", transport="unknown")
        conns = mgr.list_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "connected"
        await mgr.disconnect(cid)
        assert len(mgr.list_connections()) == 0

    @pytest.mark.asyncio
    async def test_disconnect_closes_transport(self):
        """Disconnect should call transport.close()."""
        mgr = MCPClientManager()
        mock_transport = AsyncMock(spec=MCPTransport)
        conn = MCPConnection(
            connection_id="c1", server_uri="test", transport="stdio",
            server_info={}, capabilities={}, status="connected",
            _transport_obj=mock_transport,
        )
        mgr._connections["c1"] = conn
        await mgr.disconnect("c1")
        mock_transport.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_tool_no_transport_raises(self):
        mgr = MCPClientManager()
        await mgr.connect("test://x", transport="unknown")
        cid = mgr.list_connections()[0]["connection_id"]
        with pytest.raises(NotImplementedError):
            await mgr.call_tool(cid, "some_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_with_transport(self):
        mgr = MCPClientManager()
        mock_transport = AsyncMock(spec=MCPTransport)
        mock_transport.send_request = AsyncMock(return_value={"result": "ok"})
        conn = MCPConnection(
            connection_id="c1", server_uri="test", transport="stdio",
            server_info={}, capabilities={}, status="connected",
            _transport_obj=mock_transport,
        )
        mgr._connections["c1"] = conn
        result = await mgr.call_tool("c1", "my_tool", {"arg": 1})
        assert result == {"result": "ok"}
        mock_transport.send_request.assert_awaited_once_with(
            "tools/call", {"name": "my_tool", "arguments": {"arg": 1}},
        )

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        mgr = MCPClientManager()
        await mgr.connect("a", transport="unknown")
        await mgr.connect("b", transport="unknown")
        assert len(mgr.list_connections()) == 2
        await mgr.disconnect_all()
        assert len(mgr.list_connections()) == 0

    @pytest.mark.asyncio
    async def test_max_connections_enforced(self):
        mgr = MCPClientManager(max_connections=1)
        await mgr.connect("a", transport="unknown")
        with pytest.raises(RuntimeError, match="Max MCP"):
            await mgr.connect("b", transport="unknown")


# ═══════════════════════════════════════════════════════════════
# 10. AgentTask.depends_on field
# ═══════════════════════════════════════════════════════════════


class TestAgentTaskDependsOn:
    def test_default_empty(self):
        t = AgentTask(workflow_id="w", assigner="a", assignee="b", instruction="x")
        assert t.depends_on == []

    def test_set_depends_on(self):
        t = AgentTask(
            workflow_id="w", assigner="a", assignee="b",
            instruction="x", depends_on=["id1", "id2"],
        )
        assert t.depends_on == ["id1", "id2"]

    def test_serialization(self):
        t = AgentTask(
            workflow_id="w", assigner="a", assignee="b",
            instruction="x", depends_on=["id1"],
        )
        data = t.model_dump()
        assert data["depends_on"] == ["id1"]
        restored = AgentTask.model_validate(data)
        assert restored.depends_on == ["id1"]
