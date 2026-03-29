"""ProactiveEngine — generates, delivers, and learns from user suggestion responses."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from nobla.events.models import NoblaEvent
from nobla.learning.models import (
    ProactiveConfig,
    ProactiveLevel,
    ProactiveSuggestion,
    SuggestionStatus,
    SuggestionType,
)

logger = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLDS: dict[ProactiveLevel, float] = {
    ProactiveLevel.CONSERVATIVE: 0.9,
    ProactiveLevel.MODERATE: 0.7,
    ProactiveLevel.AGGRESSIVE: 0.5,
}

ACCEPT_BOOST = 0.1
DISMISS_PENALTY = -0.2
SOFT_PENALTY = -0.05
SOFT_PENALTY_THRESHOLD = 3   # snooze count where soft penalty kicks in
AUTO_EXPIRE_THRESHOLD = 5    # snooze count where suggestion auto-expires


class ProactiveEngine:
    """Manages proactive suggestions — evaluation, acceptance, dismissal, snooze, and briefings."""

    def __init__(self, event_bus: Any, config: ProactiveConfig) -> None:
        self._event_bus = event_bus
        self._config = config
        self._suggestions: dict[str, ProactiveSuggestion] = {}
        self._confidence_adjustments: dict[SuggestionType, float] = defaultdict(float)
        self._daily_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # ------------------------------------------------------------------
    # Candidate management
    # ------------------------------------------------------------------

    def add_candidate(self, suggestion: ProactiveSuggestion) -> None:
        """Store a suggestion candidate for later evaluation."""
        self._suggestions[suggestion.id] = suggestion

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate_suggestions(self, user_id: str) -> list[ProactiveSuggestion]:
        """Return PENDING suggestions that pass the confidence threshold and daily cap."""
        if self._config.level == ProactiveLevel.OFF:
            return []

        threshold = CONFIDENCE_THRESHOLDS[self._config.level]
        today = datetime.now(timezone.utc).date().isoformat()
        already_shown = self._daily_counts[user_id][today]
        remaining = self._config.max_suggestions_per_day - already_shown

        if remaining <= 0:
            return []

        results: list[ProactiveSuggestion] = []
        for s in self._suggestions.values():
            if s.user_id != user_id or s.status != SuggestionStatus.PENDING:
                continue
            adjusted = s.confidence + self._confidence_adjustments.get(s.type, 0.0)
            if adjusted >= threshold:
                results.append(s)
            if len(results) >= remaining:
                break

        self._daily_counts[user_id][today] += len(results)
        return results

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    async def accept_suggestion(self, suggestion_id: str) -> dict[str, Any] | None:
        """Mark suggestion as accepted, boost confidence for its type, emit event."""
        s = self._suggestions[suggestion_id]
        self._suggestions[suggestion_id] = _replace(s, status=SuggestionStatus.ACCEPTED)
        self._confidence_adjustments[s.type] += ACCEPT_BOOST

        await self._event_bus.emit(NoblaEvent(
            event_type="learning.suggestion.accepted",
            source="proactive_engine",
            user_id=s.user_id,
            payload={"suggestion_id": suggestion_id, "type": s.type},
        ))
        logger.info("suggestion_accepted", suggestion_id=suggestion_id)
        return s.action

    # ------------------------------------------------------------------
    # Dismiss
    # ------------------------------------------------------------------

    async def dismiss_suggestion(self, suggestion_id: str, reason: str | None = None) -> None:
        """Mark suggestion as dismissed, apply penalty, emit event."""
        s = self._suggestions[suggestion_id]
        self._suggestions[suggestion_id] = _replace(s, status=SuggestionStatus.DISMISSED)
        self._confidence_adjustments[s.type] += DISMISS_PENALTY

        await self._event_bus.emit(NoblaEvent(
            event_type="learning.suggestion.dismissed",
            source="proactive_engine",
            user_id=s.user_id,
            payload={"suggestion_id": suggestion_id, "reason": reason},
        ))
        logger.info("suggestion_dismissed", suggestion_id=suggestion_id, reason=reason)

    # ------------------------------------------------------------------
    # Snooze
    # ------------------------------------------------------------------

    async def snooze_suggestion(self, suggestion_id: str, days: int) -> None:
        """Snooze a suggestion; auto-expire after threshold; apply soft penalty at threshold."""
        s = self._suggestions[suggestion_id]
        new_count = s.snooze_count + 1
        snooze_until = datetime.now(timezone.utc) + timedelta(days=days)

        if new_count >= AUTO_EXPIRE_THRESHOLD:
            updated = _replace(s, snooze_count=new_count, snooze_until=snooze_until,
                               status=SuggestionStatus.EXPIRED)
        else:
            if new_count >= SOFT_PENALTY_THRESHOLD:
                self._confidence_adjustments[s.type] += SOFT_PENALTY
            updated = _replace(s, snooze_count=new_count, snooze_until=snooze_until,
                               status=SuggestionStatus.SNOOZED)

        self._suggestions[suggestion_id] = updated

        await self._event_bus.emit(NoblaEvent(
            event_type="learning.suggestion.snoozed",
            source="proactive_engine",
            user_id=s.user_id,
            payload={"suggestion_id": suggestion_id, "days": days, "snooze_count": new_count},
        ))
        logger.info("suggestion_snoozed", suggestion_id=suggestion_id, days=days, count=new_count)

    # ------------------------------------------------------------------
    # Check snoozed
    # ------------------------------------------------------------------

    async def check_snoozed(self) -> list[ProactiveSuggestion]:
        """Reactivate snoozed suggestions whose snooze_until has passed."""
        now = datetime.now(timezone.utc)
        reactivated: list[ProactiveSuggestion] = []

        for sid, s in list(self._suggestions.items()):
            if s.status != SuggestionStatus.SNOOZED:
                continue
            if s.snooze_until is not None and s.snooze_until <= now:
                updated = _replace(s, status=SuggestionStatus.PENDING, snooze_until=None)
                self._suggestions[sid] = updated
                reactivated.append(updated)

        return reactivated

    # ------------------------------------------------------------------
    # Briefing
    # ------------------------------------------------------------------

    async def generate_briefing(self, user_id: str) -> ProactiveSuggestion | None:
        """Generate a daily briefing suggestion — only in AGGRESSIVE mode."""
        if self._config.level != ProactiveLevel.AGGRESSIVE:
            return None

        briefing = ProactiveSuggestion(
            id=str(uuid.uuid4()),
            type=SuggestionType.BRIEFING,
            title="Daily Briefing",
            description="Summary of activity",
            confidence=1.0,
            action=None,
            user_id=user_id,
            status=SuggestionStatus.PENDING,
            snooze_until=None,
            snooze_count=0,
            expires_at=None,
            created_at=datetime.now(timezone.utc),
            source_pattern_id=None,
        )
        logger.info("briefing_generated", user_id=user_id)
        return briefing

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_suggestion(self, suggestion_id: str) -> ProactiveSuggestion:
        """Return a suggestion by ID."""
        return self._suggestions[suggestion_id]

    def get_suggestions(
        self, user_id: str, status: SuggestionStatus | None = None
    ) -> list[ProactiveSuggestion]:
        """Return all suggestions for a user, optionally filtered by status."""
        return [
            s for s in self._suggestions.values()
            if s.user_id == user_id and (status is None or s.status == status)
        ]

    def get_confidence_adjustment(self, stype: SuggestionType) -> float:
        """Return the cumulative confidence adjustment for a suggestion type."""
        return self._confidence_adjustments.get(stype, 0.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _replace(suggestion: ProactiveSuggestion, **kwargs: Any) -> ProactiveSuggestion:
    """Return a new ProactiveSuggestion with updated fields (dataclass is not frozen)."""
    import dataclasses
    return dataclasses.replace(suggestion, **kwargs)
