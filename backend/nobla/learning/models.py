"""Learning layer models — enums, dataclasses, and config for Phase 5B self-improving agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PatternStatus(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    SKILL_CREATED = "skill_created"
    DISMISSED = "dismissed"


class MacroTier(str, Enum):
    MACRO = "macro"
    SKILL = "skill"
    PUBLISHABLE = "publishable"


class ExperimentStatus(str, Enum):
    RUNNING = "running"
    CONCLUDED = "concluded"
    PAUSED = "paused"


class SuggestionType(str, Enum):
    PATTERN = "pattern"
    OPTIMIZATION = "optimization"
    ANOMALY = "anomaly"
    BRIEFING = "briefing"


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    EXPIRED = "expired"


class ProactiveLevel(str, Enum):
    OFF = "off"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


# ---------------------------------------------------------------------------
# Feedback dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeedbackContext:
    llm_model: str
    prompt_template: str | None
    tool_chain: list[str]
    intent_category: str | None
    ab_variant_id: str | None


@dataclass(frozen=True)
class ResponseFeedback:
    id: str
    conversation_id: str
    message_id: str
    user_id: str
    quick_rating: int          # 1 = thumbs up, -1 = thumbs down
    star_rating: int | None    # 1-5 or None
    comment: str | None
    context: FeedbackContext
    timestamp: datetime

    @property
    def is_positive(self) -> bool:
        return self.quick_rating == 1 or (
            self.star_rating is not None and self.star_rating >= 4
        )

    @property
    def is_negative(self) -> bool:
        return self.quick_rating == -1 or (
            self.star_rating is not None and self.star_rating <= 2
        )


# ---------------------------------------------------------------------------
# Pattern detection dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PatternOccurrence:
    conversation_id: str
    message_ids: list[str]
    tool_sequence: list[str]
    params_snapshot: dict[str, Any]
    occurred_at: datetime


@dataclass
class PatternCandidate:
    id: str
    user_id: str
    fingerprint: str
    description: str
    occurrences: list[PatternOccurrence]
    tool_sequence: list[str]
    variable_params: dict[str, list[Any]]
    status: PatternStatus
    confidence: float
    detection_method: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Workflow macro dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MacroParameter:
    name: str
    description: str
    type: str
    default: Any
    examples: list[Any] = field(default_factory=list)


@dataclass
class WorkflowMacro:
    id: str
    name: str
    description: str
    pattern_id: str
    workflow_id: str
    skill_id: str | None
    parameters: list[MacroParameter]
    tier: MacroTier
    usage_count: int
    user_id: str
    created_at: datetime
    promoted_at: datetime | None


# ---------------------------------------------------------------------------
# A/B testing dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ABVariant:
    id: str
    model: str
    prompt_template: str | None
    feedback_scores: list[float]
    sample_count: int
    win_rate: float


@dataclass
class ABExperiment:
    id: str
    task_category: str
    variants: list[ABVariant]
    status: ExperimentStatus
    min_samples: int
    epsilon: float
    created_at: datetime
    concluded_at: datetime | None
    winner_variant_id: str | None


# ---------------------------------------------------------------------------
# Proactive suggestions dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProactiveSuggestion:
    id: str
    type: SuggestionType
    title: str
    description: str
    confidence: float
    action: dict[str, Any] | None
    user_id: str
    status: SuggestionStatus
    snooze_until: datetime | None
    snooze_count: int
    expires_at: datetime | None
    created_at: datetime
    source_pattern_id: str | None


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PatternConfig:
    sequence_window_days: int = 7
    min_occurrences: int = 3
    intent_clustering_enabled: bool = False
    max_patterns_per_user: int = 50
    fingerprint_algorithm: str = "sequence_hash"
    confidence_threshold: float = 0.6


@dataclass
class ProactiveConfig:
    level: ProactiveLevel = ProactiveLevel.CONSERVATIVE
    max_suggestions_per_day: int = 1
    snooze_options_days: list[int] = field(default_factory=lambda: [1, 3, 7])
    max_snooze_count: int = 3       # soft-dismiss threshold
    max_auto_expire_count: int = 5  # auto-expire threshold
    min_confidence: float = 0.7
    briefing_hour: int = 8          # hour of day for daily briefing
