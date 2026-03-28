"""Webhook data models — registration, event logs, dead letters (Phase 6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WebhookDirection(str, Enum):
    """Whether the webhook receives or sends events."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class WebhookStatus(str, Enum):
    """Lifecycle status of a webhook registration."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class WebhookEventStatus(str, Enum):
    """Processing status of a single webhook event."""

    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookHealthStatus(str, Enum):
    """Aggregate health of a webhook based on recent failure rate."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"


class SignatureScheme(str, Enum):
    """Supported signature verification schemes."""

    HMAC_SHA256 = "hmac-sha256"
    HMAC_SHA1 = "hmac-sha1"
    NONE = "none"


@dataclass(slots=True)
class Webhook:
    """A registered webhook — inbound (we receive) or outbound (we send).

    Attributes:
        webhook_id: Unique identifier.
        user_id: Owner who registered this webhook.
        name: Human-friendly label.
        direction: Inbound or outbound.
        url: Inbound: caller's origin (informational). Outbound: target URL.
        event_type_prefix: Event namespace, e.g. "github.push", "stripe.payment".
        secret: Shared secret for HMAC signature verification/signing.
        signature_scheme: Which verification algorithm to use.
        status: Current lifecycle status.
        created_at: Registration timestamp.
        updated_at: Last modification timestamp.
    """

    webhook_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: str = ""
    direction: WebhookDirection = WebhookDirection.INBOUND
    url: str = ""
    event_type_prefix: str = ""
    secret: str = ""
    signature_scheme: SignatureScheme = SignatureScheme.HMAC_SHA256
    status: WebhookStatus = WebhookStatus.ACTIVE
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class WebhookEvent:
    """Log entry for a received or sent webhook event.

    Attributes:
        event_id: Unique identifier.
        webhook_id: Parent webhook registration.
        headers: HTTP headers from the request.
        payload: Deserialized JSON body.
        signature_valid: Whether signature verification passed.
        status: Processing status.
        retry_count: How many retry attempts have been made.
        error: Error message if processing failed.
        processed_at: When processing completed (success or final failure).
        created_at: When the event was first received/sent.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    webhook_id: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    signature_valid: bool = False
    status: WebhookEventStatus = WebhookEventStatus.RECEIVED
    retry_count: int = 0
    error: str | None = None
    processed_at: datetime | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class DeadLetterEvent:
    """Events that failed after exhausting all retries.

    Attributes:
        id: Unique identifier.
        webhook_id: Parent webhook registration.
        event_id: Original WebhookEvent id.
        payload: Event payload preserved for inspection.
        error: Final error message.
        retry_count: Total attempts made before giving up.
        user_notified: Whether the user was alerted about this failure.
        created_at: When the event was moved to dead letter.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    webhook_id: str = ""
    event_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retry_count: int = 0
    user_notified: bool = False
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class WebhookHealth:
    """Aggregate health summary for a webhook.

    Attributes:
        webhook_id: Which webhook this summarizes.
        event_count: Total events received/sent.
        failure_count: Events that failed processing.
        failure_rate: Percentage of failed events (0.0-1.0).
        dead_letter_count: Events in dead letter queue.
        last_received_at: Timestamp of most recent event.
        status: Derived health status.
    """

    webhook_id: str = ""
    event_count: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0
    dead_letter_count: int = 0
    last_received_at: datetime | None = None
    status: WebhookHealthStatus = WebhookHealthStatus.HEALTHY

    def compute_status(self) -> WebhookHealthStatus:
        """Derive health status from failure rate."""
        if self.event_count == 0:
            return WebhookHealthStatus.HEALTHY
        if self.failure_rate >= 0.5:
            return WebhookHealthStatus.FAILING
        if self.failure_rate >= 0.1:
            return WebhookHealthStatus.DEGRADED
        return WebhookHealthStatus.HEALTHY
