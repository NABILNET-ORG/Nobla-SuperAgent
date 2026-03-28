"""Gateway REST routes for webhook management and inbound receiver (Phase 6).

Routes:
    POST   /api/webhooks                  — Register a new webhook
    GET    /api/webhooks                  — List user's webhooks
    DELETE /api/webhooks/{webhook_id}      — Delete a webhook
    PUT    /api/webhooks/{webhook_id}/status — Pause/resume
    GET    /api/webhooks/{webhook_id}/events — Event history
    GET    /api/webhooks/{webhook_id}/health — Health summary
    POST   /api/webhooks/{webhook_id}/test  — Send test event
    POST   /webhooks/inbound/{webhook_id}   — Inbound webhook receiver
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from nobla.automation.webhooks.models import (
    SignatureScheme,
    Webhook,
    WebhookDirection,
    WebhookStatus,
)

if TYPE_CHECKING:
    from nobla.automation.webhooks.manager import WebhookManager

# Module-level service reference (set during lifespan)
_webhook_manager: WebhookManager | None = None


def set_webhook_manager(mgr: WebhookManager) -> None:
    global _webhook_manager
    _webhook_manager = mgr


def get_webhook_manager() -> WebhookManager | None:
    return _webhook_manager


def _require_manager() -> WebhookManager:
    if _webhook_manager is None:
        raise HTTPException(status_code=503, detail="Webhook system not initialized")
    return _webhook_manager


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class RegisterWebhookRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    direction: str = "inbound"
    url: str = ""
    event_type_prefix: str = Field(..., min_length=1, max_length=200)
    secret: str = Field(..., min_length=8)
    signature_scheme: str = "hmac-sha256"


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|paused|disabled)$")


class WebhookResponse(BaseModel):
    webhook_id: str
    name: str
    direction: str
    url: str
    event_type_prefix: str
    signature_scheme: str
    status: str
    created_at: str
    updated_at: str


class WebhookEventResponse(BaseModel):
    event_id: str
    webhook_id: str
    signature_valid: bool
    status: str
    retry_count: int
    error: str | None
    processed_at: str | None
    created_at: str


class WebhookHealthResponse(BaseModel):
    webhook_id: str
    event_count: int
    failure_count: int
    failure_rate: float
    dead_letter_count: int
    last_received_at: str | None
    status: str


class DeadLetterResponse(BaseModel):
    id: str
    webhook_id: str
    event_id: str
    error: str
    retry_count: int
    user_notified: bool
    created_at: str


# ------------------------------------------------------------------
# Converters
# ------------------------------------------------------------------


def _wh_to_response(wh: Webhook) -> dict[str, Any]:
    return WebhookResponse(
        webhook_id=wh.webhook_id,
        name=wh.name,
        direction=wh.direction.value,
        url=wh.url,
        event_type_prefix=wh.event_type_prefix,
        signature_scheme=wh.signature_scheme.value,
        status=wh.status.value,
        created_at=wh.created_at.isoformat(),
        updated_at=wh.updated_at.isoformat(),
    ).model_dump()


# ------------------------------------------------------------------
# Router factory
# ------------------------------------------------------------------


def create_webhook_router() -> APIRouter:
    """Create the webhook REST API router."""
    router = APIRouter(tags=["webhooks"])

    @router.post("/api/webhooks")
    async def register_webhook(req: RegisterWebhookRequest):
        mgr = _require_manager()
        wh = Webhook(
            user_id="default",  # TODO: extract from auth context
            name=req.name,
            direction=WebhookDirection(req.direction),
            url=req.url,
            event_type_prefix=req.event_type_prefix,
            secret=req.secret,
            signature_scheme=SignatureScheme(req.signature_scheme),
        )
        try:
            mgr.register(wh)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _wh_to_response(wh)

    @router.get("/api/webhooks")
    async def list_webhooks(user_id: str = "default"):
        mgr = _require_manager()
        hooks = mgr.list_for_user(user_id)
        return [_wh_to_response(wh) for wh in hooks]

    @router.delete("/api/webhooks/{webhook_id}")
    async def delete_webhook(webhook_id: str):
        mgr = _require_manager()
        try:
            mgr.delete(webhook_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted"}

    @router.put("/api/webhooks/{webhook_id}/status")
    async def update_webhook_status(webhook_id: str, req: UpdateStatusRequest):
        mgr = _require_manager()
        try:
            wh = mgr.update_status(webhook_id, WebhookStatus(req.status))
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return _wh_to_response(wh)

    @router.get("/api/webhooks/{webhook_id}/events")
    async def get_webhook_events(webhook_id: str, limit: int = 50):
        mgr = _require_manager()
        try:
            mgr.get(webhook_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        events = mgr.get_events(webhook_id, limit=limit)
        return [
            WebhookEventResponse(
                event_id=e.event_id,
                webhook_id=e.webhook_id,
                signature_valid=e.signature_valid,
                status=e.status.value,
                retry_count=e.retry_count,
                error=e.error,
                processed_at=e.processed_at.isoformat() if e.processed_at else None,
                created_at=e.created_at.isoformat(),
            ).model_dump()
            for e in events
        ]

    @router.get("/api/webhooks/{webhook_id}/health")
    async def get_webhook_health(webhook_id: str):
        mgr = _require_manager()
        try:
            health = mgr.get_health(webhook_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return WebhookHealthResponse(
            webhook_id=health.webhook_id,
            event_count=health.event_count,
            failure_count=health.failure_count,
            failure_rate=health.failure_rate,
            dead_letter_count=health.dead_letter_count,
            last_received_at=(
                health.last_received_at.isoformat()
                if health.last_received_at
                else None
            ),
            status=health.status.value,
        ).model_dump()

    @router.get("/api/webhooks/{webhook_id}/dead-letters")
    async def get_dead_letters(webhook_id: str):
        mgr = _require_manager()
        try:
            mgr.get(webhook_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        dls = mgr.get_dead_letters(webhook_id)
        return [
            DeadLetterResponse(
                id=dl.id,
                webhook_id=dl.webhook_id,
                event_id=dl.event_id,
                error=dl.error,
                retry_count=dl.retry_count,
                user_notified=dl.user_notified,
                created_at=dl.created_at.isoformat(),
            ).model_dump()
            for dl in dls
        ]

    @router.post("/api/webhooks/{webhook_id}/test")
    async def test_webhook(webhook_id: str):
        mgr = _require_manager()
        try:
            event = await mgr.send_test_event(webhook_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "status": "ok",
            "event_id": event.event_id,
            "signature_valid": event.signature_valid,
        }

    @router.post("/webhooks/inbound/{webhook_id}")
    async def inbound_webhook(webhook_id: str, request: Request):
        """Receive an inbound webhook from an external service."""
        mgr = _require_manager()
        body = await request.body()
        headers = dict(request.headers)

        # Extract signature from common header locations
        signature = (
            headers.get("x-hub-signature-256", "")
            or headers.get("x-hub-signature", "")
            or headers.get("x-signature", "")
            or headers.get("x-webhook-signature", "")
        )

        try:
            event = await mgr.process_inbound(
                webhook_id=webhook_id,
                payload_bytes=body,
                headers=headers,
                signature=signature,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Webhook not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PermissionError:
            raise HTTPException(status_code=401, detail="Invalid signature")

        return {"status": "accepted", "event_id": event.event_id}

    return router
