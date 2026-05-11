"""Cross-channel webhook dispatcher route (closes SCM-S3-D3).

Single FastAPI route at ``/webhook/{channel_slug}``. Resolves the channel
via ``channel_manager.get(slug)`` and delegates the inbound request to
``adapter.dispatch_webhook(request)``.

Adapters that don't override ``dispatch_webhook`` (e.g. Telegram, which
self-serves via python-telegram-bot's internal aiohttp webhook server)
return 405 via the base default ``NotImplementedError`` path.

Per-channel signature semantics, body parsing, and challenge handling
all live INSIDE each adapter's ``dispatch_webhook`` — this module is a
~30-line slug-to-adapter resolver, never a per-channel switchyard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from nobla.gateway.channel_handlers import get_channel_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.api_route(
    "/webhook/{channel_slug}",
    methods=["GET", "POST"],
    name="channel_webhook_dispatch",
)
async def dispatch_channel_webhook(channel_slug: str, request: Request):
    """Resolve a channel by URL slug and delegate to its ``dispatch_webhook``.

    - 503 if the channel manager has not been initialized (lifespan failure).
    - 404 if no adapter is registered for ``channel_slug``.
    - 405 if the adapter inherits the base default (no webhook support).
    - Otherwise the adapter's ``dispatch_webhook`` Response is returned verbatim,
      including any ``HTTPException`` it raises (e.g. 401 for bad signature).
    """
    manager = get_channel_manager()
    if manager is None:
        logger.error("Channel webhook dispatch failed: channel manager not initialized")
        raise HTTPException(status_code=503, detail="Channel manager not initialized")

    adapter = manager.get(channel_slug)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_slug!r}")

    try:
        return await adapter.dispatch_webhook(request)
    except NotImplementedError as exc:
        logger.warning(
            "Channel %s does not implement dispatch_webhook: %s", channel_slug, exc,
        )
        raise HTTPException(status_code=405, detail=str(exc))
