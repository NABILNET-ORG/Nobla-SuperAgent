"""Outbound webhook handler — subscribe to events, POST to targets (Phase 6).

Architecture:
    OutboundWebhookHandler subscribes to the event bus via wildcard patterns.
    When a matching event fires, it signs the payload with the webhook's
    configured scheme and POSTs to the target URL.  Failed deliveries are
    retried with exponential backoff.  After exhausting retries, events
    land in the dead letter queue and trigger a user notification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from nobla.automation.webhooks.models import (
    Webhook,
    WebhookDirection,
    WebhookEvent,
    WebhookEventStatus,
    WebhookStatus,
)
from nobla.automation.webhooks.verification import VerifierRegistry

if TYPE_CHECKING:
    from nobla.automation.webhooks.manager import WebhookManager
    from nobla.events.bus import NoblaEventBus
    from nobla.events.models import NoblaEvent

logger = logging.getLogger(__name__)


class OutboundDeliveryResult:
    """Result of a single outbound delivery attempt."""

    __slots__ = ("success", "status_code", "error", "duration_ms")

    def __init__(
        self,
        success: bool = False,
        status_code: int = 0,
        error: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        self.success = success
        self.status_code = status_code
        self.error = error
        self.duration_ms = duration_ms


class OutboundWebhookHandler:
    """Sends webhook POSTs when internal events match outbound webhooks.

    Subscribes to ``*`` on the event bus and filters events against
    registered outbound webhooks.  Signs payloads, sends HTTP POSTs,
    retries on failure, and routes to dead letter on exhaustion.

    Args:
        webhook_manager: WebhookManager for accessing registrations + dead letters.
        event_bus: NoblaEventBus for subscribing to events.
        verifier_registry: Pluggable verifier registry for signing.
        max_retries: Maximum delivery attempts per event.
        retry_backoff_base: Base delay in seconds for exponential backoff.
        retry_backoff_multiplier: Multiplier for exponential backoff.
        timeout: HTTP request timeout in seconds.
        http_post: Injectable async POST function (for testing).
    """

    def __init__(
        self,
        webhook_manager: WebhookManager,
        event_bus: NoblaEventBus,
        verifier_registry: VerifierRegistry | None = None,
        max_retries: int = 3,
        retry_backoff_base: float = 2.0,
        retry_backoff_multiplier: float = 4.0,
        timeout: float = 10.0,
        http_post: Any = None,
    ) -> None:
        self._manager = webhook_manager
        self._event_bus = event_bus
        self._verifiers = verifier_registry or VerifierRegistry()
        self._max_retries = max_retries
        self._backoff_base = retry_backoff_base
        self._backoff_multiplier = retry_backoff_multiplier
        self._timeout = timeout
        self._http_post = http_post or self._default_http_post
        self._subscription_id: str | None = None
        self._pending_deliveries: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to all events on the bus."""
        self._subscription_id = await self._event_bus.subscribe(
            "*", self._on_event
        )
        logger.info("outbound_webhook_handler_started")

    async def stop(self) -> None:
        """Unsubscribe and cancel pending deliveries."""
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        for task in self._pending_deliveries:
            if not task.done():
                task.cancel()
        self._pending_deliveries.clear()
        logger.info("outbound_webhook_handler_stopped")

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _on_event(self, event: NoblaEvent) -> None:
        """Handle an event from the bus — check against outbound webhooks."""
        outbound_hooks = self._get_matching_outbound(event.event_type)
        for wh in outbound_hooks:
            task = asyncio.create_task(
                self._deliver(wh, event)
            )
            self._pending_deliveries.append(task)
            task.add_done_callback(lambda t: self._pending_deliveries.remove(t) if t in self._pending_deliveries else None)

    def _get_matching_outbound(self, event_type: str) -> list[Webhook]:
        """Find active outbound webhooks whose prefix matches the event."""
        result = []
        for wh in self._manager._webhooks.values():
            if (
                wh.direction == WebhookDirection.OUTBOUND
                and wh.status == WebhookStatus.ACTIVE
                and event_type.startswith(f"webhook.{wh.event_type_prefix}")
            ):
                result.append(wh)
        return result

    # ------------------------------------------------------------------
    # Delivery with retry
    # ------------------------------------------------------------------

    async def _deliver(self, wh: Webhook, event: NoblaEvent) -> None:
        """Attempt to deliver an event to an outbound webhook with retries."""
        payload_dict = {
            "event_type": event.event_type,
            "source": event.source,
            "timestamp": event.timestamp.isoformat(),
            "data": event.payload,
        }
        payload_bytes = json.dumps(payload_dict).encode("utf-8")

        # Sign payload
        verifier = self._verifiers.get(wh.signature_scheme.value)
        signature = verifier.sign(payload_bytes, wh.secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event.event_type,
            "X-Webhook-Id": wh.webhook_id,
        }

        # Create event log entry
        webhook_event = WebhookEvent(
            webhook_id=wh.webhook_id,
            headers=headers,
            payload=payload_dict,
            signature_valid=True,  # We signed it ourselves
        )

        last_error = ""
        for attempt in range(self._max_retries + 1):
            result = await self._attempt_post(wh.url, payload_bytes, headers)

            if result.success:
                webhook_event.status = WebhookEventStatus.PROCESSED
                webhook_event.processed_at = __import__(
                    "datetime"
                ).datetime.now(__import__("datetime").timezone.utc)
                webhook_event.retry_count = attempt
                self._manager._events.setdefault(wh.webhook_id, []).append(
                    webhook_event
                )

                # Emit success event
                from nobla.events.models import NoblaEvent as NE

                await self._event_bus.emit(
                    NE(
                        event_type=f"webhook.{wh.event_type_prefix}.outbound.sent",
                        source=f"webhook.{wh.webhook_id}",
                        payload={
                            "webhook_id": wh.webhook_id,
                            "event_id": webhook_event.event_id,
                            "status_code": result.status_code,
                            "attempt": attempt + 1,
                            "duration_ms": result.duration_ms,
                        },
                        user_id=wh.user_id,
                    )
                )
                logger.info(
                    "outbound_webhook_sent id=%s attempt=%d status=%d",
                    wh.webhook_id, attempt + 1, result.status_code,
                )
                return

            last_error = result.error
            webhook_event.status = WebhookEventStatus.RETRYING
            webhook_event.retry_count = attempt + 1

            if attempt < self._max_retries:
                delay = self._backoff_base * (self._backoff_multiplier ** attempt)
                logger.warning(
                    "outbound_webhook_retry id=%s attempt=%d delay=%.1fs error=%s",
                    wh.webhook_id, attempt + 1, delay, result.error,
                )
                await asyncio.sleep(delay)

        # Exhausted retries — dead letter
        webhook_event.status = WebhookEventStatus.FAILED
        webhook_event.error = last_error
        webhook_event.processed_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        self._manager._events.setdefault(wh.webhook_id, []).append(
            webhook_event
        )

        dl = self._manager.add_dead_letter(
            webhook_id=wh.webhook_id,
            event_id=webhook_event.event_id,
            payload=payload_dict,
            error=last_error,
            retry_count=self._max_retries + 1,
        )
        await self._manager.notify_dead_letter(dl)

        # Emit failure event
        from nobla.events.models import NoblaEvent as NE

        await self._event_bus.emit(
            NE(
                event_type=f"webhook.{wh.event_type_prefix}.outbound.failed",
                source=f"webhook.{wh.webhook_id}",
                payload={
                    "webhook_id": wh.webhook_id,
                    "event_id": webhook_event.event_id,
                    "error": last_error,
                    "attempts": self._max_retries + 1,
                },
                user_id=wh.user_id,
                priority=5,
            )
        )
        logger.error(
            "outbound_webhook_failed id=%s attempts=%d error=%s",
            wh.webhook_id, self._max_retries + 1, last_error,
        )

    async def _attempt_post(
        self, url: str, payload: bytes, headers: dict[str, str]
    ) -> OutboundDeliveryResult:
        """Make a single HTTP POST attempt."""
        start = time.monotonic()
        try:
            result = await self._http_post(
                url, payload, headers, timeout=self._timeout
            )
            elapsed = (time.monotonic() - start) * 1000
            return OutboundDeliveryResult(
                success=result.get("success", False),
                status_code=result.get("status_code", 0),
                error=result.get("error", ""),
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return OutboundDeliveryResult(
                success=False,
                error=str(e),
                duration_ms=elapsed,
            )

    @staticmethod
    async def _default_http_post(
        url: str, payload: bytes, headers: dict[str, str], timeout: float = 10.0
    ) -> dict[str, Any]:
        """Default HTTP POST using httpx (or aiohttp).

        Returns dict with keys: success, status_code, error.
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=payload, headers=headers)
                return {
                    "success": 200 <= resp.status_code < 300,
                    "status_code": resp.status_code,
                    "error": "" if 200 <= resp.status_code < 300 else resp.text[:500],
                }
        except Exception as e:
            return {"success": False, "status_code": 0, "error": str(e)}

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def compute_backoff(self, attempt: int) -> float:
        """Compute backoff delay for a given attempt number."""
        return self._backoff_base * (self._backoff_multiplier ** attempt)
