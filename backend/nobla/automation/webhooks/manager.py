"""Webhook manager — CRUD, inbound processing, health, dead letters (Phase 6).

Handles both inbound (external → Nobla) and outbound (Nobla → external)
webhook registration.  Inbound processing verifies signatures, logs events,
and emits NoblaEvents on the event bus.  Health computation aggregates
recent event stats per webhook.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from nobla.automation.webhooks.models import (
    DeadLetterEvent,
    Webhook,
    WebhookDirection,
    WebhookEvent,
    WebhookEventStatus,
    WebhookHealth,
    WebhookHealthStatus,
    WebhookStatus,
)
from nobla.automation.webhooks.verification import VerifierRegistry

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)


class WebhookManager:
    """Manages webhook registration, inbound processing, and health.

    All state is in-memory (dict-based).  A future migration to PostgreSQL
    tables is planned but deferred — the interface stays the same.

    Args:
        event_bus: NoblaEventBus for emitting webhook events.
        verifier_registry: Pluggable signature verifier registry.
        max_webhooks_per_user: Registration limit per user.
        max_retries: Maximum retry attempts for failed processing.
        max_payload_bytes: Reject inbound payloads exceeding this size.
    """

    def __init__(
        self,
        event_bus: NoblaEventBus,
        verifier_registry: VerifierRegistry | None = None,
        max_webhooks_per_user: int = 50,
        max_retries: int = 3,
        max_payload_bytes: int = 1_048_576,
    ) -> None:
        self._event_bus = event_bus
        self._verifiers = verifier_registry or VerifierRegistry()
        self._max_per_user = max_webhooks_per_user
        self._max_retries = max_retries
        self._max_payload_bytes = max_payload_bytes

        # In-memory stores
        self._webhooks: dict[str, Webhook] = {}
        self._events: dict[str, list[WebhookEvent]] = {}  # webhook_id → events
        self._dead_letters: dict[str, list[DeadLetterEvent]] = {}  # webhook_id → dead letters

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, webhook: Webhook) -> Webhook:
        """Register a new webhook.

        Raises:
            ValueError: If user has reached the registration limit.
            KeyError: If the signature scheme is not registered.
        """
        user_count = sum(
            1 for wh in self._webhooks.values() if wh.user_id == webhook.user_id
        )
        if user_count >= self._max_per_user:
            raise ValueError(
                f"User {webhook.user_id} has reached the maximum of "
                f"{self._max_per_user} webhooks"
            )
        # Validate scheme exists
        self._verifiers.get(webhook.signature_scheme.value)

        self._webhooks[webhook.webhook_id] = webhook
        self._events[webhook.webhook_id] = []
        self._dead_letters[webhook.webhook_id] = []
        logger.info(
            "webhook_registered id=%s name=%s dir=%s",
            webhook.webhook_id, webhook.name, webhook.direction.value,
        )
        return webhook

    def get(self, webhook_id: str) -> Webhook:
        """Retrieve a webhook by ID.

        Raises:
            KeyError: If not found.
        """
        try:
            return self._webhooks[webhook_id]
        except KeyError:
            raise KeyError(f"Webhook not found: {webhook_id}") from None

    def list_for_user(self, user_id: str) -> list[Webhook]:
        """List all webhooks for a user."""
        return [
            wh for wh in self._webhooks.values() if wh.user_id == user_id
        ]

    def delete(self, webhook_id: str) -> None:
        """Deactivate and remove a webhook.

        Raises:
            KeyError: If not found.
        """
        wh = self.get(webhook_id)
        wh.status = WebhookStatus.DISABLED
        del self._webhooks[webhook_id]
        self._events.pop(webhook_id, None)
        # Keep dead letters for audit
        logger.info("webhook_deleted id=%s", webhook_id)

    def update_status(self, webhook_id: str, status: WebhookStatus) -> Webhook:
        """Update a webhook's status (pause/resume/disable).

        Raises:
            KeyError: If not found.
        """
        wh = self.get(webhook_id)
        wh.status = status
        wh.updated_at = datetime.now(timezone.utc)
        logger.info("webhook_status_updated id=%s status=%s", webhook_id, status.value)
        return wh

    # ------------------------------------------------------------------
    # Inbound processing
    # ------------------------------------------------------------------

    async def process_inbound(
        self,
        webhook_id: str,
        payload_bytes: bytes,
        headers: dict[str, str],
        signature: str = "",
    ) -> WebhookEvent:
        """Process an inbound webhook event.

        1. Lookup webhook.
        2. Verify signature.
        3. Log event.
        4. Emit NoblaEvent on event bus.

        Args:
            webhook_id: Target webhook ID.
            payload_bytes: Raw request body.
            headers: HTTP headers dict.
            signature: Signature header value.

        Returns:
            The created WebhookEvent.

        Raises:
            KeyError: If webhook not found.
            ValueError: If webhook is not active or payload too large.
            PermissionError: If signature verification fails.
        """
        wh = self.get(webhook_id)

        if wh.status != WebhookStatus.ACTIVE:
            raise ValueError(f"Webhook {webhook_id} is not active (status={wh.status.value})")

        if wh.direction != WebhookDirection.INBOUND:
            raise ValueError(f"Webhook {webhook_id} is outbound, cannot receive events")

        if len(payload_bytes) > self._max_payload_bytes:
            raise ValueError(
                f"Payload size {len(payload_bytes)} exceeds limit "
                f"{self._max_payload_bytes}"
            )

        # Verify signature
        verifier = self._verifiers.get(wh.signature_scheme.value)
        sig_valid = verifier.verify(payload_bytes, signature, wh.secret)

        # Parse payload
        try:
            payload = json.loads(payload_bytes) if payload_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"raw": payload_bytes.decode("utf-8", errors="replace")}

        # Create event log
        event = WebhookEvent(
            webhook_id=webhook_id,
            headers=dict(headers),
            payload=payload,
            signature_valid=sig_valid,
        )

        if not sig_valid:
            event.status = WebhookEventStatus.FAILED
            event.error = "Signature verification failed"
            event.processed_at = datetime.now(timezone.utc)
            self._events.setdefault(webhook_id, []).append(event)
            logger.warning(
                "webhook_signature_failed id=%s event=%s",
                webhook_id, event.event_id,
            )
            raise PermissionError("Webhook signature verification failed")

        # Emit on event bus
        from nobla.events.models import NoblaEvent

        nobla_event = NoblaEvent(
            event_type=f"webhook.{wh.event_type_prefix}.received",
            source=f"webhook.{webhook_id}",
            payload={
                "webhook_id": webhook_id,
                "webhook_name": wh.name,
                "event_id": event.event_id,
                "headers": event.headers,
                "data": payload,
            },
            user_id=wh.user_id,
        )
        await self._event_bus.emit(nobla_event)

        event.status = WebhookEventStatus.PROCESSED
        event.processed_at = datetime.now(timezone.utc)
        self._events.setdefault(webhook_id, []).append(event)

        logger.info(
            "webhook_inbound_processed id=%s event=%s type=%s",
            webhook_id, event.event_id, wh.event_type_prefix,
        )
        return event

    # ------------------------------------------------------------------
    # Test event
    # ------------------------------------------------------------------

    async def send_test_event(self, webhook_id: str) -> WebhookEvent:
        """Send a test event through a webhook for verification.

        Raises:
            KeyError: If webhook not found.
        """
        wh = self.get(webhook_id)
        test_payload = json.dumps({
            "type": "test",
            "webhook_id": webhook_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }).encode("utf-8")

        verifier = self._verifiers.get(wh.signature_scheme.value)
        sig = verifier.sign(test_payload, wh.secret)

        return await self.process_inbound(
            webhook_id=webhook_id,
            payload_bytes=test_payload,
            headers={"x-webhook-test": "true"},
            signature=sig,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def get_health(self, webhook_id: str) -> WebhookHealth:
        """Compute health summary for a webhook.

        Raises:
            KeyError: If webhook not found.
        """
        self.get(webhook_id)  # Validate exists
        events = self._events.get(webhook_id, [])
        dead_letters = self._dead_letters.get(webhook_id, [])

        event_count = len(events)
        failure_count = sum(
            1 for e in events if e.status == WebhookEventStatus.FAILED
        )
        failure_rate = failure_count / event_count if event_count > 0 else 0.0
        last_received = events[-1].created_at if events else None

        health = WebhookHealth(
            webhook_id=webhook_id,
            event_count=event_count,
            failure_count=failure_count,
            failure_rate=failure_rate,
            dead_letter_count=len(dead_letters),
            last_received_at=last_received,
        )
        health.status = health.compute_status()
        return health

    # ------------------------------------------------------------------
    # Dead letters
    # ------------------------------------------------------------------

    def add_dead_letter(
        self, webhook_id: str, event_id: str, payload: dict, error: str, retry_count: int
    ) -> DeadLetterEvent:
        """Move a failed event to the dead letter queue.

        Emits a ``webhook.dead_letter`` event on the bus for user notification.
        """
        dl = DeadLetterEvent(
            webhook_id=webhook_id,
            event_id=event_id,
            payload=payload,
            error=error,
            retry_count=retry_count,
        )
        self._dead_letters.setdefault(webhook_id, []).append(dl)
        logger.warning(
            "webhook_dead_letter id=%s event=%s error=%s",
            webhook_id, event_id, error,
        )
        return dl

    async def notify_dead_letter(self, dl: DeadLetterEvent) -> None:
        """Emit a dead letter notification event on the bus."""
        from nobla.events.models import NoblaEvent

        wh = self._webhooks.get(dl.webhook_id)
        user_id = wh.user_id if wh else None

        event = NoblaEvent(
            event_type="webhook.dead_letter",
            source=f"webhook.{dl.webhook_id}",
            payload={
                "dead_letter_id": dl.id,
                "webhook_id": dl.webhook_id,
                "event_id": dl.event_id,
                "error": dl.error,
                "retry_count": dl.retry_count,
            },
            user_id=user_id,
            priority=5,  # Elevated — user should be notified
        )
        await self._event_bus.emit(event)
        dl.user_notified = True

    def get_dead_letters(self, webhook_id: str) -> list[DeadLetterEvent]:
        """Retrieve dead letter events for a webhook."""
        return list(self._dead_letters.get(webhook_id, []))

    def get_events(self, webhook_id: str, limit: int = 50) -> list[WebhookEvent]:
        """Retrieve recent events for a webhook."""
        events = self._events.get(webhook_id, [])
        return list(events[-limit:])
