"""PatternDetector — detects repeated tool sequences via fingerprint hashing.

Phase 5B.1: sequence matching + variable param extraction.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog

from nobla.events.models import NoblaEvent
from nobla.learning.models import (
    PatternCandidate,
    PatternConfig,
    PatternOccurrence,
    PatternStatus,
)

logger = structlog.get_logger(__name__)


class PatternDetector:
    """Detects repeated tool-use sequences for a user and promotes them to PatternCandidates."""

    def __init__(self, event_bus: Any, config: PatternConfig) -> None:
        self._event_bus = event_bus
        self._config = config

        # {user_id: {correlation_id: [{"tool_name": str, "params": dict}]}}
        self._sequences: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

        # {user_id: {fingerprint: [PatternOccurrence]}}
        self._fingerprint_occurrences: dict[str, dict[str, list[PatternOccurrence]]] = defaultdict(lambda: defaultdict(list))

        # {fingerprint: [tool_names]}
        self._fingerprint_tool_sequences: dict[str, list[str]] = {}

        # {fingerprint: {param_name: [values]}}  — aggregated across occurrences
        self._fingerprint_params: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))

        # {user_id: [PatternCandidate]}
        self._patterns: dict[str, list[PatternCandidate]] = defaultdict(list)

        # set of (user_id, fingerprint) already promoted to avoid duplicate candidates
        self._promoted: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_fingerprint(self, tool_names: list[str]) -> str:
        """Return a SHA-256 hex digest of the ordered tool sequence."""
        return hashlib.sha256("|".join(tool_names).encode()).hexdigest()

    async def on_tool_executed(self, event: Any) -> None:
        """Append a tool execution event to the in-progress sequence for its correlation_id."""
        user_id: str = event.payload.get("user_id") or event.user_id or "unknown"
        correlation_id: str = event.correlation_id
        tool_name: str = event.payload.get("tool_name", "")
        params: dict[str, Any] = event.payload.get("params", {})

        self._sequences[user_id][correlation_id].append(
            {"tool_name": tool_name, "params": params}
        )

    async def finalize_sequence(self, user_id: str, correlation_id: str) -> None:
        """Called when a correlated sequence of tool calls is complete.

        Computes fingerprint, records occurrence, and promotes to PatternCandidate
        when min_occurrences is reached.
        """
        steps = self._sequences[user_id].pop(correlation_id, [])
        if not steps:
            return

        tool_names = [s["tool_name"] for s in steps]
        fingerprint = self.compute_fingerprint(tool_names)

        # Store canonical tool sequence for this fingerprint
        self._fingerprint_tool_sequences.setdefault(fingerprint, tool_names)

        # Aggregate params across occurrences
        for step in steps:
            for param_name, param_value in step["params"].items():
                self._fingerprint_params[fingerprint][param_name].append(param_value)

        # Record occurrence
        occurrence = PatternOccurrence(
            conversation_id=correlation_id,
            message_ids=[],
            tool_sequence=tool_names,
            params_snapshot={s["tool_name"]: s["params"] for s in steps},
            occurred_at=datetime.now(timezone.utc),
        )
        self._fingerprint_occurrences[user_id][fingerprint].append(occurrence)

        occurrences = self._fingerprint_occurrences[user_id][fingerprint]

        # Promote to pattern if threshold met and not already promoted
        if (
            len(occurrences) >= self._config.min_occurrences
            and (user_id, fingerprint) not in self._promoted
        ):
            await self._promote_pattern(user_id, fingerprint, occurrences, tool_names)

    async def get_patterns(
        self,
        user_id: str,
        status: PatternStatus | None = None,
    ) -> list[PatternCandidate]:
        """Return patterns for a user, optionally filtered by status."""
        candidates = self._patterns.get(user_id, [])
        if status is not None:
            candidates = [p for p in candidates if p.status == status]
        return list(candidates)

    async def dismiss_pattern(self, pattern_id: str) -> None:
        """Mark a pattern as dismissed and emit a dismissal event."""
        pattern = self._find_pattern_by_id(pattern_id)
        if pattern is None:
            logger.warning("dismiss_pattern: pattern not found", pattern_id=pattern_id)
            return

        pattern.status = PatternStatus.DISMISSED
        logger.info("pattern dismissed", pattern_id=pattern_id)

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.pattern.dismissed",
                source="learning.patterns",
                payload={"pattern_id": pattern_id, "user_id": pattern.user_id},
                user_id=pattern.user_id,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _promote_pattern(
        self,
        user_id: str,
        fingerprint: str,
        occurrences: list[PatternOccurrence],
        tool_names: list[str],
    ) -> None:
        """Create a PatternCandidate and emit detection event."""
        variable_params = self._extract_variable_params(fingerprint)

        pattern = PatternCandidate(
            id=str(uuid.uuid4()),
            user_id=user_id,
            fingerprint=fingerprint,
            description=" → ".join(tool_names),
            occurrences=list(occurrences),
            tool_sequence=tool_names,
            variable_params=variable_params,
            status=PatternStatus.DETECTED,
            confidence=0.6,
            detection_method="sequence",
            created_at=datetime.now(timezone.utc),
        )

        self._patterns[user_id].append(pattern)
        self._promoted.add((user_id, fingerprint))

        # Enforce per-user cap — drop lowest confidence if over limit
        if len(self._patterns[user_id]) > self._config.max_patterns_per_user:
            self._patterns[user_id].sort(key=lambda p: p.confidence, reverse=True)
            self._patterns[user_id] = self._patterns[user_id][: self._config.max_patterns_per_user]

        logger.info(
            "pattern detected",
            user_id=user_id,
            fingerprint=fingerprint[:8],
            tools=tool_names,
            occurrences=len(occurrences),
        )

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.pattern.detected",
                source="learning.patterns",
                payload={
                    "pattern_id": pattern.id,
                    "user_id": user_id,
                    "tool_sequence": tool_names,
                    "occurrences": len(occurrences),
                    "confidence": pattern.confidence,
                },
                user_id=user_id,
            )
        )

    def _extract_variable_params(self, fingerprint: str) -> dict[str, list[Any]]:
        """Return params that varied across occurrences (more than 1 unique value)."""
        variable: dict[str, list[Any]] = {}
        for param_name, values in self._fingerprint_params.get(fingerprint, {}).items():
            unique_values = list({str(v): v for v in values}.values())
            if len(unique_values) > 1:
                variable[param_name] = values
        return variable

    def _find_pattern_by_id(self, pattern_id: str) -> PatternCandidate | None:
        for candidates in self._patterns.values():
            for p in candidates:
                if p.id == pattern_id:
                    return p
        return None
