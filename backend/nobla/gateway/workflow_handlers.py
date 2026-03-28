"""Gateway REST routes for workflow management (Phase 6).

Routes:
    POST   /api/workflows                          — Create from NL
    GET    /api/workflows                          — List user's workflows
    GET    /api/workflows/{id}                     — Get workflow detail
    PUT    /api/workflows/{id}                     — Update workflow
    PUT    /api/workflows/{id}/status              — Pause/resume/archive
    DELETE /api/workflows/{id}                     — Delete
    POST   /api/workflows/{id}/trigger             — Manual trigger
    GET    /api/workflows/{id}/executions          — Execution history
    GET    /api/workflows/{id}/executions/{exec_id} — Execution detail
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nobla.automation.workflows.models import WorkflowStatus

if TYPE_CHECKING:
    from nobla.automation.workflows.service import WorkflowService

_workflow_service: WorkflowService | None = None


def set_workflow_service(svc: WorkflowService) -> None:
    global _workflow_service
    _workflow_service = svc


def get_workflow_service() -> WorkflowService | None:
    return _workflow_service


def _require_service() -> WorkflowService:
    if _workflow_service is None:
        raise HTTPException(status_code=503, detail="Workflow system not initialized")
    return _workflow_service


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class CreateWorkflowRequest(BaseModel):
    description: str = Field(..., min_length=5)
    name: str = ""


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|paused|archived)$")


class WorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    description: str
    version: int
    status: str
    trigger_count: int
    step_count: int
    created_at: str
    updated_at: str


class ExecutionResponse(BaseModel):
    execution_id: str
    workflow_id: str
    workflow_version: int
    user_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    step_count: int
    steps_completed: int
    steps_failed: int


# ------------------------------------------------------------------
# Converters
# ------------------------------------------------------------------


def _wf_to_response(wf) -> dict[str, Any]:
    return WorkflowResponse(
        workflow_id=wf.workflow_id,
        name=wf.name,
        description=wf.description,
        version=wf.version,
        status=wf.status.value,
        trigger_count=len(wf.triggers),
        step_count=len(wf.steps),
        created_at=wf.created_at.isoformat(),
        updated_at=wf.updated_at.isoformat(),
    ).model_dump()


def _exec_to_response(ex) -> dict[str, Any]:
    from nobla.automation.workflows.models import ExecutionStatus
    completed = sum(
        1 for se in ex.step_executions.values()
        if se.status == ExecutionStatus.COMPLETED
    )
    failed = sum(
        1 for se in ex.step_executions.values()
        if se.status == ExecutionStatus.FAILED
    )
    return ExecutionResponse(
        execution_id=ex.execution_id,
        workflow_id=ex.workflow_id,
        workflow_version=ex.workflow_version,
        user_id=ex.user_id,
        status=ex.status.value,
        started_at=ex.started_at.isoformat() if ex.started_at else None,
        completed_at=ex.completed_at.isoformat() if ex.completed_at else None,
        step_count=len(ex.step_executions),
        steps_completed=completed,
        steps_failed=failed,
    ).model_dump()


# ------------------------------------------------------------------
# Router factory
# ------------------------------------------------------------------


def create_workflow_router() -> APIRouter:
    """Create the workflow REST API router."""
    router = APIRouter(tags=["workflows"])

    @router.post("/api/workflows")
    async def create_workflow(req: CreateWorkflowRequest):
        svc = _require_service()
        try:
            wf = await svc.create_from_nl(
                description=req.description,
                user_id="default",  # TODO: extract from auth
                name=req.name,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _wf_to_response(wf)

    @router.get("/api/workflows")
    async def list_workflows(user_id: str = "default"):
        svc = _require_service()
        workflows = svc.list_for_user(user_id)
        return [_wf_to_response(wf) for wf in workflows]

    @router.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        svc = _require_service()
        try:
            wf = svc.get(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        resp = _wf_to_response(wf)
        resp["steps"] = [
            {
                "step_id": s.step_id,
                "name": s.name,
                "type": s.type.value,
                "depends_on": s.depends_on,
                "nl_source": s.nl_source,
                "error_handling": s.error_handling.value,
            }
            for s in wf.steps
        ]
        resp["triggers"] = [
            {
                "trigger_id": t.trigger_id,
                "event_pattern": t.event_pattern,
                "conditions": [
                    {"field_path": c.field_path, "operator": c.operator.value, "value": c.value}
                    for c in t.conditions
                ],
                "active": t.active,
            }
            for t in wf.triggers
        ]
        resp["versions"] = wf.list_versions()
        return resp

    @router.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, req: UpdateWorkflowRequest):
        svc = _require_service()
        try:
            wf = svc.update(
                workflow_id, name=req.name, description=req.description,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return _wf_to_response(wf)

    @router.put("/api/workflows/{workflow_id}/status")
    async def update_workflow_status(workflow_id: str, req: UpdateStatusRequest):
        svc = _require_service()
        try:
            wf = svc.update_status(workflow_id, WorkflowStatus(req.status))
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return _wf_to_response(wf)

    @router.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        svc = _require_service()
        try:
            svc.delete(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"status": "deleted"}

    @router.post("/api/workflows/{workflow_id}/trigger")
    async def trigger_workflow(workflow_id: str):
        svc = _require_service()
        try:
            ex = await svc.trigger_manually(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _exec_to_response(ex)

    @router.get("/api/workflows/{workflow_id}/executions")
    async def get_executions(workflow_id: str, limit: int = 20):
        svc = _require_service()
        try:
            svc.get(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        execs = svc.get_executions(workflow_id, limit=limit)
        return [_exec_to_response(ex) for ex in execs]

    @router.get("/api/workflows/{workflow_id}/executions/{execution_id}")
    async def get_execution_detail(workflow_id: str, execution_id: str):
        svc = _require_service()
        try:
            ex = svc.get_execution(workflow_id, execution_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Execution not found")
        resp = _exec_to_response(ex)
        resp["step_executions"] = {
            sid: {
                "status": se.status.value,
                "result": se.result,
                "error": se.error,
                "branch_taken": se.branch_taken,
                "started_at": se.started_at.isoformat() if se.started_at else None,
                "completed_at": se.completed_at.isoformat() if se.completed_at else None,
            }
            for sid, se in ex.step_executions.items()
        }
        return resp

    return router
