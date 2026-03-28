"""Gateway REST routes for workflow templates + import/export (Phase 6).

Routes:
    GET    /api/templates                           — List/search templates
    GET    /api/templates/categories                 — List categories with counts
    GET    /api/templates/{id}                       — Get template detail
    POST   /api/templates/{id}/instantiate           — Create workflow from template
    GET    /api/workflows/{id}/export                — Export workflow as portable JSON
    POST   /api/workflows/import                     — Import workflow from JSON
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from nobla.automation.workflows.service import WorkflowService
    from nobla.automation.workflows.template_registry import TemplateRegistry

_template_registry: TemplateRegistry | None = None
_workflow_service: WorkflowService | None = None


def set_template_registry(reg: TemplateRegistry) -> None:
    global _template_registry
    _template_registry = reg


def get_template_registry() -> TemplateRegistry | None:
    return _template_registry


def set_template_workflow_service(svc: WorkflowService) -> None:
    global _workflow_service
    _workflow_service = svc


def get_template_workflow_service() -> WorkflowService | None:
    return _workflow_service


def _require_registry() -> TemplateRegistry:
    if _template_registry is None:
        raise HTTPException(status_code=503, detail="Template system not initialized")
    return _template_registry


def _require_service() -> WorkflowService:
    if _workflow_service is None:
        raise HTTPException(status_code=503, detail="Workflow system not initialized")
    return _workflow_service


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class InstantiateTemplateRequest(BaseModel):
    name: str | None = None
    user_id: str = "default"


class ImportWorkflowRequest(BaseModel):
    data: dict[str, Any] = Field(..., description="Portable workflow JSON")
    name: str | None = None
    user_id: str = "default"


class TemplateResponse(BaseModel):
    template_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    author: str
    version: str
    step_count: int
    trigger_count: int
    icon: str
    bundled: bool


class TemplateDetailResponse(TemplateResponse):
    steps: list[dict[str, Any]]
    triggers: list[dict[str, Any]]
    created_at: str
    updated_at: str


class ExportResponse(BaseModel):
    data: dict[str, Any]


# ------------------------------------------------------------------
# Converters
# ------------------------------------------------------------------


def _tmpl_to_response(tmpl) -> dict[str, Any]:
    return TemplateResponse(
        template_id=tmpl.template_id,
        name=tmpl.name,
        description=tmpl.description,
        category=tmpl.category.value,
        tags=tmpl.tags,
        author=tmpl.author,
        version=tmpl.version,
        step_count=len(tmpl.steps),
        trigger_count=len(tmpl.triggers),
        icon=tmpl.icon,
        bundled=tmpl.bundled,
    ).model_dump()


def _tmpl_to_detail(tmpl) -> dict[str, Any]:
    return TemplateDetailResponse(
        template_id=tmpl.template_id,
        name=tmpl.name,
        description=tmpl.description,
        category=tmpl.category.value,
        tags=tmpl.tags,
        author=tmpl.author,
        version=tmpl.version,
        step_count=len(tmpl.steps),
        trigger_count=len(tmpl.triggers),
        icon=tmpl.icon,
        bundled=tmpl.bundled,
        steps=[s.to_dict() for s in tmpl.steps],
        triggers=[t.to_dict() for t in tmpl.triggers],
        created_at=tmpl.created_at.isoformat(),
        updated_at=tmpl.updated_at.isoformat(),
    ).model_dump()


# ------------------------------------------------------------------
# Router factory
# ------------------------------------------------------------------


def create_template_router() -> APIRouter:
    """Create the template + import/export REST API router."""
    router = APIRouter(tags=["templates"])

    # -- Template endpoints --

    @router.get("/api/templates")
    async def list_templates(
        query: str = "",
        category: str | None = None,
        tags: str | None = None,
    ):
        reg = _require_registry()
        from nobla.automation.workflows.templates import TemplateCategory
        cat = None
        if category:
            try:
                cat = TemplateCategory(category)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        results = reg.search(query=query, category=cat, tags=tag_list)
        return [_tmpl_to_response(t) for t in results]

    @router.get("/api/templates/categories")
    async def list_categories():
        reg = _require_registry()
        return reg.list_categories()

    @router.get("/api/templates/{template_id}")
    async def get_template(template_id: str):
        reg = _require_registry()
        try:
            tmpl = reg.get(template_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Template not found")
        return _tmpl_to_detail(tmpl)

    @router.post("/api/templates/{template_id}/instantiate")
    async def instantiate_template(template_id: str, req: InstantiateTemplateRequest):
        reg = _require_registry()
        svc = _require_service()
        try:
            tmpl = reg.get(template_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Template not found")
        try:
            wf = svc.instantiate_template(tmpl, req.user_id, name_override=req.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "version": wf.version,
            "status": wf.status.value,
            "step_count": len(wf.steps),
            "trigger_count": len(wf.triggers),
            "template_id": template_id,
        }

    # -- Export / Import endpoints --

    @router.get("/api/workflows/{workflow_id}/export")
    async def export_workflow(workflow_id: str, include_metadata: bool = True):
        svc = _require_service()
        try:
            export_data = svc.export_workflow(workflow_id, include_metadata=include_metadata)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return ExportResponse(data=export_data.to_dict()).model_dump()

    @router.post("/api/workflows/import")
    async def import_workflow(req: ImportWorkflowRequest):
        svc = _require_service()
        from nobla.automation.workflows.templates import WorkflowExportData
        try:
            export_data = WorkflowExportData.from_dict(req.data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid export data: {e}")
        try:
            wf = svc.import_workflow(export_data, req.user_id, name_override=req.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "version": wf.version,
            "status": wf.status.value,
            "step_count": len(wf.steps),
            "trigger_count": len(wf.triggers),
        }

    return router
