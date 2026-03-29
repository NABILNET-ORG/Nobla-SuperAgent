"""REST API for the self-improving agent learning system."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

learning_router = APIRouter(prefix="/api/learning", tags=["learning"])


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    quick_rating: int
    star_rating: int | None = None
    comment: str | None = None
    context: dict = {}

class DismissRequest(BaseModel):
    reason: str | None = None

class SnoozeRequest(BaseModel):
    days: int

class CreateExperimentRequest(BaseModel):
    task_category: str
    variants: list[dict]

class PublishRequest(BaseModel):
    metadata: dict = {}


def _get_service(request: Request):
    svc = getattr(request.app.state, "learning_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Learning service not available")
    return svc


# --- Feedback ---
@learning_router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, request: Request):
    import uuid
    from datetime import datetime, timezone
    from nobla.learning.models import ResponseFeedback, FeedbackContext
    svc = _get_service(request)
    fb = ResponseFeedback(
        id=str(uuid.uuid4()), conversation_id=body.conversation_id,
        message_id=body.message_id, user_id="current-user",
        quick_rating=body.quick_rating, star_rating=body.star_rating,
        comment=body.comment,
        context=FeedbackContext(
            llm_model=body.context.get("llm_model", "unknown"),
            prompt_template=body.context.get("prompt_template"),
            tool_chain=body.context.get("tool_chain", []),
            intent_category=body.context.get("intent_category"),
            ab_variant_id=body.context.get("ab_variant_id"),
        ),
        timestamp=datetime.now(timezone.utc),
    )
    await svc.submit_feedback(fb)
    return {"status": "ok", "feedback_id": fb.id}

@learning_router.get("/feedback")
async def get_feedback(request: Request, conversation_id: str = ""):
    svc = _get_service(request)
    items = await svc.get_feedback_for_conversation(conversation_id)
    return {"items": [{"id": f.id, "quick_rating": f.quick_rating} for f in items]}

@learning_router.get("/feedback/stats")
async def get_feedback_stats(request: Request):
    svc = _get_service(request)
    return await svc.get_feedback_stats("current-user")

# --- Patterns ---
@learning_router.get("/patterns")
async def list_patterns(request: Request, status: str | None = None):
    svc = _get_service(request)
    from nobla.learning.models import PatternStatus
    s = PatternStatus(status) if status else None
    items = await svc.get_patterns("current-user", status=s)
    return {"items": [{"id": p.id, "description": p.description, "status": p.status.value} for p in items]}

@learning_router.get("/patterns/{pattern_id}")
async def get_pattern(pattern_id: str, request: Request):
    svc = _get_service(request)
    items = await svc.get_patterns("current-user")
    for p in items:
        if p.id == pattern_id:
            return {"id": p.id, "description": p.description, "status": p.status.value}
    raise HTTPException(status_code=404, detail="Pattern not found")

@learning_router.post("/patterns/{pattern_id}/dismiss")
async def dismiss_pattern(pattern_id: str, request: Request):
    svc = _get_service(request)
    await svc.dismiss_pattern(pattern_id)
    return {"status": "ok"}

# --- Macros ---
@learning_router.get("/macros")
async def list_macros(request: Request, tier: str | None = None):
    svc = _get_service(request)
    from nobla.learning.models import MacroTier
    t = MacroTier(tier) if tier else None
    items = await svc.get_macros("current-user", tier=t)
    return {"items": [{"id": m.id, "name": m.name, "tier": m.tier.value} for m in items]}

@learning_router.get("/macros/{macro_id}")
async def get_macro(macro_id: str, request: Request):
    svc = _get_service(request)
    items = await svc.get_macros("current-user")
    for m in items:
        if m.id == macro_id:
            return {"id": m.id, "name": m.name, "tier": m.tier.value}
    raise HTTPException(status_code=404, detail="Macro not found")

@learning_router.post("/macros/{macro_id}/promote")
async def promote_macro(macro_id: str, request: Request):
    svc = _get_service(request)
    result = await svc.promote_to_skill(macro_id)
    if result is None:
        raise HTTPException(status_code=400, detail="Security scan failed")
    return {"status": "ok", "skill_id": result.id}

@learning_router.post("/macros/{macro_id}/publish")
async def publish_macro(macro_id: str, body: PublishRequest, request: Request):
    svc = _get_service(request)
    result = await svc.mark_publishable(macro_id, body.metadata)
    return {"status": "ok", "tier": result.tier.value}

@learning_router.delete("/macros/{macro_id}")
async def delete_macro(macro_id: str, request: Request):
    svc = _get_service(request)
    await svc.delete_macro(macro_id)
    return {"status": "ok"}

# --- Experiments ---
@learning_router.post("/experiments")
async def create_experiment(body: CreateExperimentRequest, request: Request):
    svc = _get_service(request)
    exp = await svc.create_experiment(body.task_category, body.variants)
    return {"id": exp.id, "status": exp.status.value}

@learning_router.get("/experiments")
async def list_experiments(request: Request, status: str | None = None):
    svc = _get_service(request)
    from nobla.learning.models import ExperimentStatus
    s = ExperimentStatus(status) if status else None
    items = await svc.get_experiments(status=s)
    return {"items": [{"id": e.id, "task_category": e.task_category, "status": e.status.value} for e in items]}

@learning_router.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, request: Request):
    svc = _get_service(request)
    items = await svc.get_experiments()
    for e in items:
        if e.id == experiment_id:
            return {"id": e.id, "task_category": e.task_category, "status": e.status.value}
    raise HTTPException(status_code=404, detail="Experiment not found")

@learning_router.post("/experiments/{experiment_id}/pause")
async def pause_experiment(experiment_id: str, request: Request):
    svc = _get_service(request)
    await svc.pause_experiment(experiment_id)
    return {"status": "ok"}

# --- Suggestions ---
@learning_router.get("/suggestions")
async def list_suggestions(request: Request, status: str | None = None):
    svc = _get_service(request)
    from nobla.learning.models import SuggestionStatus
    s = SuggestionStatus(status) if status else None
    items = await svc.get_suggestions("current-user", status=s)
    return {"items": [{"id": s.id, "title": s.title, "status": s.status.value} for s in items]}

@learning_router.post("/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: str, request: Request):
    svc = _get_service(request)
    action = await svc.accept_suggestion(suggestion_id)
    return {"status": "ok", "action": action}

@learning_router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, body: DismissRequest, request: Request):
    svc = _get_service(request)
    await svc.dismiss_suggestion(suggestion_id, reason=body.reason)
    return {"status": "ok"}

@learning_router.post("/suggestions/{suggestion_id}/snooze")
async def snooze_suggestion(suggestion_id: str, body: SnoozeRequest, request: Request):
    svc = _get_service(request)
    await svc.snooze_suggestion(suggestion_id, body.days)
    return {"status": "ok"}

# --- Settings ---
@learning_router.get("/settings")
async def get_settings(request: Request):
    svc = _get_service(request)
    return svc.get_settings()

@learning_router.put("/settings")
async def update_settings(request: Request, body: dict):
    svc = _get_service(request)
    await svc.update_settings(body)
    return {"status": "ok"}

@learning_router.delete("/data")
async def clear_data(request: Request):
    svc = _get_service(request)
    await svc.clear_data()
    return {"status": "ok"}
