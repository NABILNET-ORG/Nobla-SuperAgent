"""Tests for Phase 6 WorkflowService, gateway handlers, and lifespan wiring."""

from __future__ import annotations

import pytest

from nobla.automation.workflows.models import (
    ExecutionStatus,
    StepType,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeEventBus:
    def __init__(self):
        self.emitted = []
        self._handlers = {}
        self._next = 0

    async def emit(self, event):
        self.emitted.append(event)

    async def subscribe(self, pattern, handler):
        self._next += 1
        sid = str(self._next)
        self._handlers[sid] = (pattern, handler)
        return sid

    async def unsubscribe(self, sid):
        self._handlers.pop(sid, None)


def _make_service(bus=None, max_per_user=50, max_concurrent=5):
    from nobla.automation.workflows.executor import WorkflowExecutor
    from nobla.automation.workflows.interpreter import WorkflowInterpreter
    from nobla.automation.workflows.trigger_matcher import TriggerMatcher
    from nobla.automation.workflows.service import WorkflowService

    bus = bus or _FakeEventBus()

    async def tool_cb(config, user_id):
        return {"output": "ok", "exit_code": 0}

    executor = WorkflowExecutor(event_bus=bus, tool_callback=tool_cb)
    interpreter = WorkflowInterpreter(router=None)
    matcher = TriggerMatcher(event_bus=bus)
    return WorkflowService(
        executor=executor,
        interpreter=interpreter,
        trigger_matcher=matcher,
        event_bus=bus,
        max_workflows_per_user=max_per_user,
        max_concurrent_executions=max_concurrent,
    ), bus


def _make_workflow(**kwargs) -> Workflow:
    defaults = dict(
        user_id="u1",
        name="Test WF",
        steps=[
            WorkflowStep(step_id="s1", type=StepType.TOOL, config={"tool": "code.run"}),
        ],
        triggers=[
            WorkflowTrigger(event_pattern="manual.*"),
        ],
    )
    defaults.update(kwargs)
    return Workflow(**defaults)


# ---------------------------------------------------------------------------
# WorkflowService CRUD tests
# ---------------------------------------------------------------------------


class TestWorkflowServiceCRUD:

    @pytest.mark.asyncio
    async def test_create_from_nl(self):
        svc, _ = _make_service()
        wf = await svc.create_from_nl("run tests then deploy", user_id="u1")
        assert wf.user_id == "u1"
        assert len(wf.steps) >= 2
        assert svc.get(wf.workflow_id) is wf

    @pytest.mark.asyncio
    async def test_create_pre_built(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        assert svc.get(wf.workflow_id) is wf

    @pytest.mark.asyncio
    async def test_list_for_user(self):
        svc, _ = _make_service()
        svc.create(_make_workflow(user_id="u1", name="a"))
        svc.create(_make_workflow(user_id="u1", name="b"))
        svc.create(_make_workflow(user_id="u2", name="c"))
        assert len(svc.list_for_user("u1")) == 2
        assert len(svc.list_for_user("u2")) == 1

    @pytest.mark.asyncio
    async def test_delete(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        svc.delete(wf.workflow_id)
        with pytest.raises(KeyError):
            svc.get(wf.workflow_id)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self):
        svc, _ = _make_service()
        with pytest.raises(KeyError):
            svc.delete("no-such")

    @pytest.mark.asyncio
    async def test_max_workflows_per_user(self):
        svc, _ = _make_service(max_per_user=2)
        svc.create(_make_workflow(name="a"))
        svc.create(_make_workflow(name="b"))
        with pytest.raises(ValueError, match="maximum"):
            svc.create(_make_workflow(name="c"))


class TestWorkflowServiceVersioning:

    @pytest.mark.asyncio
    async def test_update_bumps_version(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        updated = svc.update(wf.workflow_id, name="Updated")
        assert updated.version == 2
        assert updated.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self):
        svc, _ = _make_service()
        with pytest.raises(KeyError):
            svc.update("no-such")

    @pytest.mark.asyncio
    async def test_update_status_pause_resume(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        svc.update_status(wf.workflow_id, WorkflowStatus.PAUSED)
        assert svc.get(wf.workflow_id).status == WorkflowStatus.PAUSED
        svc.update_status(wf.workflow_id, WorkflowStatus.ACTIVE)
        assert svc.get(wf.workflow_id).status == WorkflowStatus.ACTIVE


class TestWorkflowServiceExecution:

    @pytest.mark.asyncio
    async def test_trigger_manually(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        ex = await svc.trigger_manually(wf.workflow_id)
        assert ex.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)
        assert ex.workflow_version == wf.version

    @pytest.mark.asyncio
    async def test_trigger_paused_raises(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        svc.update_status(wf.workflow_id, WorkflowStatus.PAUSED)
        with pytest.raises(ValueError, match="not active"):
            await svc.trigger_manually(wf.workflow_id)

    @pytest.mark.asyncio
    async def test_trigger_nonexistent_raises(self):
        svc, _ = _make_service()
        with pytest.raises(KeyError):
            await svc.trigger_manually("no-such")

    @pytest.mark.asyncio
    async def test_get_executions(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        await svc.trigger_manually(wf.workflow_id)
        await svc.trigger_manually(wf.workflow_id)
        execs = svc.get_executions(wf.workflow_id)
        assert len(execs) == 2

    @pytest.mark.asyncio
    async def test_get_execution_detail(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        ex = await svc.trigger_manually(wf.workflow_id)
        detail = svc.get_execution(wf.workflow_id, ex.execution_id)
        assert detail.execution_id == ex.execution_id

    @pytest.mark.asyncio
    async def test_get_execution_nonexistent_raises(self):
        svc, _ = _make_service()
        wf = _make_workflow()
        svc.create(wf)
        with pytest.raises(KeyError):
            svc.get_execution(wf.workflow_id, "no-such")

    @pytest.mark.asyncio
    async def test_lifecycle_start_stop(self):
        svc, bus = _make_service()
        await svc.start()
        assert len(bus._handlers) == 1
        await svc.stop()
        assert len(bus._handlers) == 0


# ---------------------------------------------------------------------------
# Gateway handler tests
# ---------------------------------------------------------------------------


class TestWorkflowHandlers:

    def setup_method(self):
        import asyncio
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from nobla.gateway.workflow_handlers import (
            create_workflow_router, set_workflow_service,
        )

        self.svc, self.bus = _make_service()
        set_workflow_service(self.svc)
        app = FastAPI()
        app.include_router(create_workflow_router())
        self.client = TestClient(app)

    def test_create_workflow(self):
        resp = self.client.post("/api/workflows", json={
            "description": "run tests then deploy to staging",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow_id" in data
        assert data["status"] == "active"
        assert data["step_count"] >= 2

    def test_create_short_desc_rejected(self):
        resp = self.client.post("/api/workflows", json={"description": "ab"})
        assert resp.status_code == 422

    def test_list_workflows(self):
        self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        self.client.post("/api/workflows", json={"description": "build and notify team"})
        resp = self.client.get("/api/workflows")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_workflow_detail(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        resp = self.client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert "triggers" in data
        assert "versions" in data

    def test_get_nonexistent_returns_404(self):
        resp = self.client.get("/api/workflows/no-such")
        assert resp.status_code == 404

    def test_update_workflow(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        resp = self.client.put(f"/api/workflows/{wf_id}", json={"name": "CI Pipeline"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "CI Pipeline"
        assert resp.json()["version"] == 2

    def test_update_status(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        resp = self.client.put(f"/api/workflows/{wf_id}/status", json={"status": "paused"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_delete_workflow(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        resp = self.client.delete(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_trigger_workflow(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        resp = self.client.post(f"/api/workflows/{wf_id}/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_id" in data
        assert data["status"] in ("completed", "failed")

    def test_get_executions(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        self.client.post(f"/api/workflows/{wf_id}/trigger")
        resp = self.client.get(f"/api/workflows/{wf_id}/executions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_execution_detail(self):
        cr = self.client.post("/api/workflows", json={"description": "run tests then deploy"})
        wf_id = cr.json()["workflow_id"]
        tr = self.client.post(f"/api/workflows/{wf_id}/trigger")
        exec_id = tr.json()["execution_id"]
        resp = self.client.get(f"/api/workflows/{wf_id}/executions/{exec_id}")
        assert resp.status_code == 200
        assert "step_executions" in resp.json()
