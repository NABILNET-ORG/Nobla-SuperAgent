"""FeedbackCollector — captures user feedback, tracks tool chains, emits events."""

from __future__ import annotations

from collections import defaultdict

import structlog

from nobla.events.models import NoblaEvent
from nobla.learning.models import ResponseFeedback

logger = structlog.get_logger(__name__)


class FeedbackCollector:
    """Collects user feedback, tracks tool execution chains, and emits learning events."""

    def __init__(self, event_bus) -> None:
        self._event_bus = event_bus
        self._feedback: dict[str, list[ResponseFeedback]] = defaultdict(list)
        self._tool_chains: dict[str, list[str]] = defaultdict(list)

    async def submit_feedback(self, fb: ResponseFeedback) -> None:
        """Store feedback and emit relevant events."""
        self._feedback[fb.conversation_id].append(fb)

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.feedback.submitted",
                source="learning.feedback",
                payload={
                    "feedback_id": fb.id,
                    "user_id": fb.user_id,
                    "quick_rating": fb.quick_rating,
                },
            )
        )

        if fb.is_positive:
            await self._event_bus.emit(
                NoblaEvent(
                    event_type="learning.feedback.positive",
                    source="learning.feedback",
                    payload={
                        "feedback_id": fb.id,
                        "user_id": fb.user_id,
                        "quick_rating": fb.quick_rating,
                    },
                )
            )
        elif fb.is_negative:
            await self._event_bus.emit(
                NoblaEvent(
                    event_type="learning.feedback.negative",
                    source="learning.feedback",
                    payload={
                        "feedback_id": fb.id,
                        "user_id": fb.user_id,
                        "quick_rating": fb.quick_rating,
                    },
                )
            )

        logger.info(
            "feedback.submitted",
            feedback_id=fb.id,
            user_id=fb.user_id,
            quick_rating=fb.quick_rating,
        )

    async def on_tool_executed(self, event) -> None:
        """Record tool name into the chain for the event's correlation_id."""
        tool_name = event.payload.get("tool_name")
        if tool_name:
            self._tool_chains[event.correlation_id].append(tool_name)

    def get_tool_chain(self, correlation_id: str) -> list[str]:
        """Return the ordered list of tools executed under a correlation_id."""
        return self._tool_chains.get(correlation_id, [])

    async def get_feedback_for_conversation(
        self, conversation_id: str
    ) -> list[ResponseFeedback]:
        """Return all feedback stored for a given conversation."""
        return list(self._feedback.get(conversation_id, []))

    async def get_feedback_stats(self, user_id: str) -> dict:
        """Aggregate feedback counts for a user across all conversations."""
        total = 0
        positive = 0
        negative = 0

        for feedback_list in self._feedback.values():
            for fb in feedback_list:
                if fb.user_id != user_id:
                    continue
                total += 1
                if fb.is_positive:
                    positive += 1
                elif fb.is_negative:
                    negative += 1

        return {"total": total, "positive": positive, "negative": negative}
