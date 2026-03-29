"""Tests for Phase 5B.1 learning models, enums, and dataclasses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from nobla.learning.models import (
    PatternStatus,
    MacroTier,
    ExperimentStatus,
    SuggestionType,
    SuggestionStatus,
    ProactiveLevel,
    FeedbackContext,
    ResponseFeedback,
    PatternOccurrence,
    PatternCandidate,
    MacroParameter,
    WorkflowMacro,
    ABVariant,
    ABExperiment,
    ProactiveSuggestion,
    PatternConfig,
    ProactiveConfig,
)


class TestEnums:
    def test_pattern_status_values(self):
        assert PatternStatus.DETECTED == "detected"
        assert PatternStatus.CONFIRMED == "confirmed"
        assert PatternStatus.SKILL_CREATED == "skill_created"
        assert PatternStatus.DISMISSED == "dismissed"

    def test_macro_tier_values(self):
        assert MacroTier.MACRO == "macro"
        assert MacroTier.SKILL == "skill"
        assert MacroTier.PUBLISHABLE == "publishable"

    def test_experiment_status_values(self):
        assert ExperimentStatus.RUNNING == "running"
        assert ExperimentStatus.CONCLUDED == "concluded"
        assert ExperimentStatus.PAUSED == "paused"

    def test_suggestion_type_values(self):
        assert SuggestionType.PATTERN == "pattern"
        assert SuggestionType.OPTIMIZATION == "optimization"
        assert SuggestionType.ANOMALY == "anomaly"
        assert SuggestionType.BRIEFING == "briefing"

    def test_suggestion_status_values(self):
        assert SuggestionStatus.PENDING == "pending"
        assert SuggestionStatus.ACCEPTED == "accepted"
        assert SuggestionStatus.DISMISSED == "dismissed"
        assert SuggestionStatus.SNOOZED == "snoozed"
        assert SuggestionStatus.EXPIRED == "expired"

    def test_proactive_level_values(self):
        assert ProactiveLevel.OFF == "off"
        assert ProactiveLevel.CONSERVATIVE == "conservative"
        assert ProactiveLevel.MODERATE == "moderate"
        assert ProactiveLevel.AGGRESSIVE == "aggressive"


class TestFeedbackContext:
    def test_create_feedback_context(self):
        ctx = FeedbackContext(
            llm_model="gemini-pro",
            prompt_template=None,
            tool_chain=["file.manage", "code.run"],
            intent_category="medium",
            ab_variant_id=None,
        )
        assert ctx.llm_model == "gemini-pro"
        assert ctx.tool_chain == ["file.manage", "code.run"]


class TestResponseFeedback:
    def test_create_with_thumbs_only(self):
        fb = ResponseFeedback(
            id=str(uuid.uuid4()),
            conversation_id="conv-1",
            message_id="msg-1",
            user_id="user-1",
            quick_rating=1,
            star_rating=None,
            comment=None,
            context=FeedbackContext(
                llm_model="gemini-pro",
                prompt_template=None,
                tool_chain=[],
                intent_category=None,
                ab_variant_id=None,
            ),
            timestamp=datetime.now(timezone.utc),
        )
        assert fb.quick_rating == 1
        assert fb.star_rating is None

    def test_create_with_full_feedback(self):
        fb = ResponseFeedback(
            id=str(uuid.uuid4()),
            conversation_id="conv-1",
            message_id="msg-1",
            user_id="user-1",
            quick_rating=-1,
            star_rating=2,
            comment="Wrong answer",
            context=FeedbackContext(
                llm_model="claude-3",
                prompt_template="tmpl-1",
                tool_chain=["code.run"],
                intent_category="hard",
                ab_variant_id="var-1",
            ),
            timestamp=datetime.now(timezone.utc),
        )
        assert fb.star_rating == 2
        assert fb.comment == "Wrong answer"

    def test_is_positive(self):
        fb = ResponseFeedback(
            id="1", conversation_id="c", message_id="m", user_id="u",
            quick_rating=1, star_rating=5, comment=None,
            context=FeedbackContext(llm_model="x", prompt_template=None, tool_chain=[], intent_category=None, ab_variant_id=None),
            timestamp=datetime.now(timezone.utc),
        )
        assert fb.is_positive is True

    def test_is_negative(self):
        fb = ResponseFeedback(
            id="1", conversation_id="c", message_id="m", user_id="u",
            quick_rating=-1, star_rating=1, comment=None,
            context=FeedbackContext(llm_model="x", prompt_template=None, tool_chain=[], intent_category=None, ab_variant_id=None),
            timestamp=datetime.now(timezone.utc),
        )
        assert fb.is_negative is True


class TestPatternCandidate:
    def test_create_detected_pattern(self):
        p = PatternCandidate(
            id=str(uuid.uuid4()),
            user_id="user-1",
            fingerprint="abc123",
            description="file.manage → code.run",
            occurrences=[],
            tool_sequence=["file.manage", "code.run"],
            variable_params={"path": ["/a", "/b"]},
            status=PatternStatus.DETECTED,
            confidence=0.6,
            detection_method="sequence",
            created_at=datetime.now(timezone.utc),
        )
        assert p.status == PatternStatus.DETECTED
        assert p.detection_method == "sequence"


class TestWorkflowMacro:
    def test_create_macro(self):
        m = WorkflowMacro(
            id=str(uuid.uuid4()),
            name="Deploy to staging",
            description="Runs file sync then code execution",
            pattern_id="pat-1",
            workflow_id="wf-1",
            skill_id=None,
            parameters=[MacroParameter(name="path", description="Target path", type="string", default=None, examples=["/app"])],
            tier=MacroTier.MACRO,
            usage_count=0,
            user_id="user-1",
            created_at=datetime.now(timezone.utc),
            promoted_at=None,
        )
        assert m.tier == MacroTier.MACRO
        assert m.skill_id is None


class TestABExperiment:
    def test_create_experiment(self):
        exp = ABExperiment(
            id=str(uuid.uuid4()),
            task_category="hard",
            variants=[
                ABVariant(id="v1", model="gpt-4", prompt_template=None, feedback_scores=[], sample_count=0, win_rate=0.0),
                ABVariant(id="v2", model="claude-3", prompt_template=None, feedback_scores=[], sample_count=0, win_rate=0.0),
            ],
            status=ExperimentStatus.RUNNING,
            min_samples=20,
            epsilon=0.1,
            created_at=datetime.now(timezone.utc),
            concluded_at=None,
            winner_variant_id=None,
        )
        assert len(exp.variants) == 2
        assert exp.epsilon == 0.1


class TestProactiveSuggestion:
    def test_create_suggestion(self):
        s = ProactiveSuggestion(
            id=str(uuid.uuid4()),
            type=SuggestionType.PATTERN,
            title="Automate deploy",
            description="You do X frequently",
            confidence=0.92,
            action={"workflow_id": "wf-1"},
            user_id="user-1",
            status=SuggestionStatus.PENDING,
            snooze_until=None,
            snooze_count=0,
            expires_at=None,
            created_at=datetime.now(timezone.utc),
            source_pattern_id="pat-1",
        )
        assert s.snooze_count == 0

    def test_snooze_count_tracks(self):
        s = ProactiveSuggestion(
            id="1", type=SuggestionType.PATTERN, title="t", description="d",
            confidence=0.9, action=None, user_id="u",
            status=SuggestionStatus.SNOOZED, snooze_until=datetime.now(timezone.utc),
            snooze_count=3, expires_at=None, created_at=datetime.now(timezone.utc),
            source_pattern_id=None,
        )
        assert s.snooze_count == 3
        assert s.status == SuggestionStatus.SNOOZED


class TestPatternConfig:
    def test_defaults(self):
        cfg = PatternConfig()
        assert cfg.sequence_window_days == 7
        assert cfg.min_occurrences == 3
        assert cfg.intent_clustering_enabled is False
        assert cfg.max_patterns_per_user == 50


class TestProactiveConfig:
    def test_defaults(self):
        cfg = ProactiveConfig()
        assert cfg.level == ProactiveLevel.CONSERVATIVE
        assert cfg.max_suggestions_per_day == 1
        assert cfg.snooze_options_days == [1, 3, 7]
        assert cfg.max_snooze_count == 3
        assert cfg.max_auto_expire_count == 5
