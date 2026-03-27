"""Event data models for the Nobla event bus.

Spec reference: Phase 5-Foundation §4.1 — Event Bus Data Models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class NoblaEvent:
    """Immutable event dispatched through the NoblaEventBus.

    Attributes:
        event_type: Dotted event name, e.g. "channel.message.in", "tool.executed".
        source: Origin component, e.g. "telegram", "scheduler", "tool.code.run".
        user_id: Nobla user ID (None for system-originated events).
        conversation_id: Active conversation (None if not conversation-scoped).
        timestamp: UTC creation time.
        payload: Arbitrary event data.
        correlation_id: UUID propagated end-to-end for full trace (auto-generated).
        priority: Dispatch priority — higher values dispatched first.
                  Default 0. Urgent events (e.g. rollback) use 10.
    """

    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    user_id: str | None = None
    conversation_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("event_type must not be empty")
        if not self.source:
            raise ValueError("source must not be empty")

    def with_reply_type(self, reply_type: str) -> NoblaEvent:
        """Create a new event preserving correlation_id and user context."""
        return NoblaEvent(
            event_type=reply_type,
            source=self.source,
            payload=self.payload,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            correlation_id=self.correlation_id,
            priority=self.priority,
        )
