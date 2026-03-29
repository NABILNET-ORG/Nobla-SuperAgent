# Phase 5B.1: Self-Improving Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a learning layer that collects feedback, detects behavioral patterns, auto-generates skills from repeated workflows, A/B tests LLM models, and proactively suggests improvements.

**Architecture:** Five backend modules (`feedback`, `patterns`, `generator`, `ab_testing`, `proactive`) orchestrated by a `LearningService`. Flutter UI adds inline feedback widgets in chat and an Agent Intelligence sub-screen under Settings.

**Storage strategy:** All modules use **in-memory storage** for this phase (dict-based stores), making tests fast and dependency-free. The spec describes dedicated SQLAlchemy tables (`learning_feedback`, `learning_patterns`, etc.) — these will be added as a follow-up task once the in-memory logic is validated. The dataclass models are designed to map 1:1 to future SQLAlchemy ORM models.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), PostgreSQL (JSONB, ARRAY, UUID), Pydantic v2, structlog, pytest. Flutter 3.x, Riverpod, GoRouter, flutter_test.

**Spec:** `docs/superpowers/specs/2026-03-28-self-improving-agent-design.md`

---

## File Map

### Backend — New Files

| File | Responsibility | Est. Lines |
|------|---------------|------------|
| `backend/nobla/learning/__init__.py` | Package exports | ~15 |
| `backend/nobla/learning/models.py` | SQLAlchemy models + dataclasses + enums | ~300 |
| `backend/nobla/learning/feedback.py` | FeedbackCollector — capture, store, emit events | ~180 |
| `backend/nobla/learning/patterns.py` | PatternDetector — sequence hash + intent cluster | ~300 |
| `backend/nobla/learning/generator.py` | SkillGenerator — macro, promote, publish-prep | ~250 |
| `backend/nobla/learning/ab_testing.py` | ABTestManager — experiments, epsilon-greedy | ~250 |
| `backend/nobla/learning/proactive.py` | ProactiveEngine — suggest, snooze, dismiss | ~300 |
| `backend/nobla/learning/service.py` | LearningService — orchestrator, wiring, settings | ~180 |
| `backend/nobla/gateway/learning_handlers.py` | REST API routes + Pydantic schemas | ~300 |
| `backend/tests/test_learning_models.py` | Tests for models + enums | ~200 |
| `backend/tests/test_learning_feedback.py` | Tests for FeedbackCollector | ~250 |
| `backend/tests/test_learning_patterns.py` | Tests for PatternDetector | ~300 |
| `backend/tests/test_learning_generator.py` | Tests for SkillGenerator | ~250 |
| `backend/tests/test_learning_ab.py` | Tests for ABTestManager | ~250 |
| `backend/tests/test_learning_proactive.py` | Tests for ProactiveEngine | ~300 |
| `backend/tests/test_learning_service.py` | Tests for LearningService integration | ~200 |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/nobla/config/settings.py` | Add `LearningSettings` model + `learning` field on `Settings` |
| `backend/nobla/gateway/lifespan.py` | Wire `LearningService` init, event subscriptions, kill switch, router |
| `backend/nobla/brain/router.py` | Add optional `ab_manager` dependency, `get_variant()` hook, `update_preference()` method |

**Note:** `backend/nobla/tools/executor.py` already emits `tool.failed` events (confirmed at lines 124, 135). No changes needed there.

| File | Responsibility | Est. Lines |
|------|---------------|------------|
| `backend/tests/test_learning_handlers.py` | Tests for REST API handlers | ~250 |

### Flutter — New Files

| File | Responsibility | Est. Lines |
|------|---------------|------------|
| `app/lib/features/learning/models/learning_models.dart` | Dart models + enums | ~250 |
| `app/lib/features/learning/providers/learning_providers.dart` | Riverpod providers | ~180 |
| `app/lib/features/learning/screens/agent_intelligence_screen.dart` | TabBarView (4 tabs) | ~250 |
| `app/lib/features/learning/widgets/feedback_widget.dart` | Thumbs + expandable stars | ~120 |
| `app/lib/features/learning/widgets/pattern_card.dart` | Pattern notification card | ~100 |
| `app/lib/features/learning/widgets/suggestion_card.dart` | Suggestion with snooze/dismiss | ~120 |
| `app/lib/features/learning/widgets/learning_stats_widget.dart` | Overview dashboard stats | ~100 |
| `app/test/features/learning/learning_models_test.dart` | Model + enum tests | ~150 |
| `app/test/features/learning/screens_test.dart` | Screen widget tests | ~200 |
| `app/test/features/learning/widgets_test.dart` | Widget tests | ~200 |

### Flutter — Modified Files

| File | Change |
|------|--------|
| `app/lib/core/routing/app_router.dart` | Add `/home/settings/intelligence` sub-route |

---

## Task 1: Models + Enums + Settings

**Files:**
- Create: `backend/nobla/learning/__init__.py`
- Create: `backend/nobla/learning/models.py`
- Modify: `backend/nobla/config/settings.py`
- Test: `backend/tests/test_learning_models.py`

- [ ] **Step 1: Create package init**

```python
# backend/nobla/learning/__init__.py
"""Self-Improving Agent — learning layer for feedback, patterns, auto-skills, A/B testing."""
```

- [ ] **Step 2: Write failing tests for enums + dataclasses**

Create `backend/tests/test_learning_models.py`:

```python
"""Tests for Phase 5B.1 learning models, enums, and SQLAlchemy tables."""

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
        assert exp.epsilon == 0.1  # lower for HARD category


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
        assert cfg.max_snooze_count == 3       # soft-dismiss threshold
        assert cfg.max_auto_expire_count == 5  # auto-expire threshold
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.learning'`

- [ ] **Step 4: Implement models.py with all enums, dataclasses, configs**

Create `backend/nobla/learning/models.py` with:
- Enums: `PatternStatus`, `MacroTier`, `ExperimentStatus`, `SuggestionType`, `SuggestionStatus`, `ProactiveLevel`
- Frozen dataclasses: `FeedbackContext`, `ResponseFeedback` (with `is_positive`/`is_negative` properties), `PatternOccurrence`, `PatternCandidate`, `MacroParameter`, `WorkflowMacro`, `ABVariant`, `ABExperiment`, `ProactiveSuggestion`
- Config dataclasses: `PatternConfig`, `ProactiveConfig`

Each dataclass matches the spec exactly (Section 3-7). `ResponseFeedback.is_positive` returns `True` if `quick_rating == 1` or `star_rating >= 4`. `is_negative` returns `True` if `quick_rating == -1` or `star_rating <= 2`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_models.py -v`
Expected: all PASS

- [ ] **Step 6: Add LearningSettings to config**

Modify `backend/nobla/config/settings.py`:
- Add `LearningSettings(BaseModel)` class with fields: `enabled: bool = True`, `feedback_enabled: bool = True`, `pattern_detection_enabled: bool = True`, `ab_testing_enabled: bool = True`, `proactive_level: str = "conservative"`
- Add `learning: LearningSettings = LearningSettings()` field on the `Settings` class

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/learning/__init__.py backend/nobla/learning/models.py backend/nobla/config/settings.py backend/tests/test_learning_models.py
git commit -m "feat(5b1): add learning models, enums, configs, LearningSettings"
```

---

## Task 2: FeedbackCollector

**Files:**
- Create: `backend/nobla/learning/feedback.py`
- Test: `backend/tests/test_learning_feedback.py`

- [ ] **Step 1: Write failing tests for FeedbackCollector**

Create `backend/tests/test_learning_feedback.py`:

```python
"""Tests for Phase 5B.1 FeedbackCollector — capture, store, emit events."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.feedback import FeedbackCollector
from nobla.learning.models import (
    FeedbackContext,
    ResponseFeedback,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def collector(event_bus):
    return FeedbackCollector(event_bus=event_bus)


def _make_feedback(quick_rating=1, star_rating=None, comment=None, ab_variant_id=None):
    return ResponseFeedback(
        id=str(uuid.uuid4()),
        conversation_id="conv-1",
        message_id="msg-1",
        user_id="user-1",
        quick_rating=quick_rating,
        star_rating=star_rating,
        comment=comment,
        context=FeedbackContext(
            llm_model="gemini-pro",
            prompt_template=None,
            tool_chain=["code.run"],
            intent_category="medium",
            ab_variant_id=ab_variant_id,
        ),
        timestamp=datetime.now(timezone.utc),
    )


class TestSubmitFeedback:
    @pytest.mark.asyncio
    async def test_submit_stores_feedback(self, collector):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        result = await collector.get_feedback_for_conversation("conv-1")
        assert len(result) == 1
        assert result[0].id == fb.id

    @pytest.mark.asyncio
    async def test_submit_emits_submitted_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.submitted"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_positive_feedback_emits_positive_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.positive"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_negative_feedback_emits_negative_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=-1, star_rating=1)
        await collector.submit_feedback(fb)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.negative"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_neutral_feedback_no_positive_or_negative_event(self, collector, event_bus):
        fb = _make_feedback(quick_rating=0, star_rating=3)
        await collector.submit_feedback(fb)
        pos = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.positive"]
        neg = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.feedback.negative"]
        assert len(pos) == 0
        assert len(neg) == 0


class TestToolChainTracking:
    @pytest.mark.asyncio
    async def test_on_tool_executed_records_chain(self, collector):
        event = MagicMock()
        event.event_type = "tool.executed"
        event.correlation_id = "corr-1"
        event.payload = {"tool_name": "file.manage"}
        await collector.on_tool_executed(event)
        chain = collector.get_tool_chain("corr-1")
        assert chain == ["file.manage"]

    @pytest.mark.asyncio
    async def test_multiple_tools_build_chain(self, collector):
        for tool in ["file.manage", "code.run", "ssh.exec"]:
            event = MagicMock()
            event.event_type = "tool.executed"
            event.correlation_id = "corr-1"
            event.payload = {"tool_name": tool}
            await collector.on_tool_executed(event)
        chain = collector.get_tool_chain("corr-1")
        assert chain == ["file.manage", "code.run", "ssh.exec"]


class TestFeedbackStats:
    @pytest.mark.asyncio
    async def test_stats_count(self, collector):
        await collector.submit_feedback(_make_feedback(quick_rating=1))
        await collector.submit_feedback(_make_feedback(quick_rating=1, star_rating=5))
        await collector.submit_feedback(_make_feedback(quick_rating=-1))
        stats = await collector.get_feedback_stats("user-1")
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_feedback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.learning.feedback'`

- [ ] **Step 3: Implement FeedbackCollector**

Create `backend/nobla/learning/feedback.py`:
- `FeedbackCollector.__init__(self, event_bus)` — in-memory store (dict of lists by conversation_id), tool chain tracker (dict of lists by correlation_id)
- `submit_feedback(fb)` — store, emit `learning.feedback.submitted`, conditionally emit `learning.feedback.positive` or `learning.feedback.negative`
- `on_tool_executed(event)` — append tool_name to chain by correlation_id
- `get_tool_chain(correlation_id)` — return accumulated tool names
- `get_feedback_for_conversation(conversation_id)` — return stored feedback
- `get_feedback_stats(user_id)` — return dict with total/positive/negative counts

Events created with `NoblaEvent(event_type=..., source="learning.feedback", payload=...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_feedback.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/learning/feedback.py backend/tests/test_learning_feedback.py
git commit -m "feat(5b1): add FeedbackCollector with tool chain tracking"
```

---

## Task 3: PatternDetector

**Files:**
- Create: `backend/nobla/learning/patterns.py`
- Test: `backend/tests/test_learning_patterns.py`

- [ ] **Step 1: Write failing tests for PatternDetector**

Create `backend/tests/test_learning_patterns.py`:

```python
"""Tests for Phase 5B.1 PatternDetector — sequence matching + intent clustering."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.patterns import PatternDetector
from nobla.learning.models import PatternCandidate, PatternConfig, PatternStatus


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def config():
    return PatternConfig(min_occurrences=3, sequence_window_days=7)


@pytest.fixture
def detector(event_bus, config):
    return PatternDetector(event_bus=event_bus, config=config)


def _tool_event(tool_name, user_id="user-1", correlation_id="corr-1", params=None):
    event = MagicMock()
    event.event_type = "tool.executed"
    event.payload = {"tool_name": tool_name, "params": params or {}, "user_id": user_id}
    event.user_id = user_id
    event.correlation_id = correlation_id
    event.timestamp = datetime.now(timezone.utc)
    return event


class TestFingerprinting:
    def test_same_sequence_same_fingerprint(self, detector):
        fp1 = detector.compute_fingerprint(["file.manage", "code.run"])
        fp2 = detector.compute_fingerprint(["file.manage", "code.run"])
        assert fp1 == fp2

    def test_different_sequence_different_fingerprint(self, detector):
        fp1 = detector.compute_fingerprint(["file.manage", "code.run"])
        fp2 = detector.compute_fingerprint(["code.run", "file.manage"])
        assert fp1 != fp2

    def test_fingerprint_is_hex_digest(self, detector):
        fp = detector.compute_fingerprint(["file.manage"])
        assert len(fp) == 64  # SHA-256 hex


class TestSequenceDetection:
    @pytest.mark.asyncio
    async def test_no_pattern_below_threshold(self, detector, event_bus):
        # Two occurrences — below min_occurrences=3
        for corr_id in ["c1", "c2"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert len(patterns) == 0

    @pytest.mark.asyncio
    async def test_pattern_detected_at_threshold(self, detector, event_bus):
        # Three occurrences of same sequence
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert len(patterns) == 1
        assert patterns[0].status == PatternStatus.DETECTED
        assert patterns[0].tool_sequence == ["file.manage", "code.run"]

    @pytest.mark.asyncio
    async def test_pattern_emits_detected_event(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.pattern.detected"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_variable_params_extracted(self, detector, event_bus):
        for i, corr_id in enumerate(["c1", "c2", "c3"]):
            await detector.on_tool_executed(_tool_event("file.manage", correlation_id=corr_id, params={"path": f"/dir{i}"}))
            await detector.on_tool_executed(_tool_event("code.run", correlation_id=corr_id, params={"code": "print('hi')"}))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        assert "path" in patterns[0].variable_params


class TestDismissPattern:
    @pytest.mark.asyncio
    async def test_dismiss_sets_status(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        await detector.dismiss_pattern(patterns[0].id)
        updated = await detector.get_patterns("user-1", status=PatternStatus.DISMISSED)
        assert len(updated) == 1

    @pytest.mark.asyncio
    async def test_dismiss_emits_event(self, detector, event_bus):
        for corr_id in ["c1", "c2", "c3"]:
            for tool in ["file.manage", "code.run"]:
                await detector.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
            await detector.finalize_sequence("user-1", corr_id)
        patterns = await detector.get_patterns("user-1")
        event_bus.emit.reset_mock()
        await detector.dismiss_pattern(patterns[0].id)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.pattern.dismissed"]
        assert len(calls) == 1


class TestMaxPatternsPerUser:
    @pytest.mark.asyncio
    async def test_cap_enforced(self, event_bus):
        config = PatternConfig(min_occurrences=3, max_patterns_per_user=2)
        det = PatternDetector(event_bus=event_bus, config=config)
        # Create 3 distinct patterns
        for seq_idx in range(3):
            tools = [f"tool_{seq_idx}_a", f"tool_{seq_idx}_b"]
            for corr_id in [f"c{seq_idx}_1", f"c{seq_idx}_2", f"c{seq_idx}_3"]:
                for tool in tools:
                    await det.on_tool_executed(_tool_event(tool, correlation_id=corr_id))
                await det.finalize_sequence("user-1", corr_id)
        patterns = await det.get_patterns("user-1")
        assert len(patterns) <= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_patterns.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement PatternDetector**

Create `backend/nobla/learning/patterns.py`:
- `PatternDetector.__init__(self, event_bus, config: PatternConfig)` — in-memory stores: `_sequences` (dict[user_id, dict[correlation_id, list[tool_event]]]), `_patterns` (dict[user_id, list[PatternCandidate]]), `_fingerprint_counts` (dict[user_id, dict[fingerprint, list[occurrence]]])
- `compute_fingerprint(tool_names: list[str]) -> str` — SHA-256 of `"|".join(tool_names)`
- `on_tool_executed(event)` — append to `_sequences[user_id][correlation_id]`
- `finalize_sequence(user_id, correlation_id)` — compute fingerprint, increment count, check threshold, create PatternCandidate if >= min_occurrences, extract variable params, emit event
- `dismiss_pattern(pattern_id)` — set status to DISMISSED, emit event
- `get_patterns(user_id, status=None)` — return filtered list
- Cap patterns per user at `config.max_patterns_per_user` (drop lowest confidence)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_patterns.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/learning/patterns.py backend/tests/test_learning_patterns.py
git commit -m "feat(5b1): add PatternDetector with sequence matching"
```

---

## Task 4: SkillGenerator

**Files:**
- Create: `backend/nobla/learning/generator.py`
- Test: `backend/tests/test_learning_generator.py`

- [ ] **Step 1: Write failing tests for SkillGenerator**

Create `backend/tests/test_learning_generator.py` with tests for:
- `create_macro(pattern)` — creates WorkflowMacro from PatternCandidate, calls workflow_service to create workflow, emits `learning.macro.created`
- `promote_to_skill(macro_id)` — generates NoblaSkill via LLM, runs security scanner, installs via skill_runtime, updates tier to SKILL, emits `learning.skill.promoted`
- `mark_publishable(macro_id, metadata)` — updates tier to PUBLISHABLE, emits `learning.skill.publishable`
- `get_macros(user_id, tier=None)` — returns filtered list
- `delete_macro(macro_id)` — removes macro
- Security: scanner rejection prevents install (promote fails gracefully)

Tests mock `workflow_service`, `skill_runtime`, `security_scanner`, and `llm_router`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SkillGenerator**

Create `backend/nobla/learning/generator.py`:
- `SkillGenerator.__init__(self, event_bus, workflow_service, skill_runtime, security_scanner, llm_router)` — in-memory `_macros` dict
- `create_macro(pattern)` — build WorkflowStep list from pattern.tool_sequence, create Workflow via workflow_service, extract MacroParameters from pattern.variable_params, store WorkflowMacro, emit event
- `promote_to_skill(macro_id)` — get macro, use llm_router to generate NoblaSkill code, scan with security_scanner, dry-run in sandbox (mock for now), install via skill_runtime, update macro.tier and macro.skill_id, emit event
- `mark_publishable(macro_id, metadata)` — update tier, emit event
- `get_macros(user_id, tier=None)` — filter by user and optional tier
- `delete_macro(macro_id)` — remove from store

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_generator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/learning/generator.py backend/tests/test_learning_generator.py
git commit -m "feat(5b1): add SkillGenerator with macro → skill → publishable lifecycle"
```

---

## Task 5: ABTestManager

**Files:**
- Create: `backend/nobla/learning/ab_testing.py`
- Test: `backend/tests/test_learning_ab.py`

- [ ] **Step 1: Write failing tests for ABTestManager**

Create `backend/tests/test_learning_ab.py` with tests for:
- `create_experiment(task_category, variants)` — stores experiment, emits `learning.ab.started`
- `get_variant(task_category, user_id)` — returns variant via epsilon-greedy; returns None if no active experiment
- `record_feedback(variant_id, score)` — updates variant scores and sample_count
- `check_conclusion(experiment_id)` — returns True when all variants >= min_samples and win rate gap > 0.1
- `pause_experiment(experiment_id)` — sets status to PAUSED
- Epsilon-greedy: with epsilon=1.0 always explores, with epsilon=0.0 always exploits (use seeded random)
- Per-category epsilon: hard=0.1, medium=0.15, easy=0.2

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_ab.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ABTestManager**

Create `backend/nobla/learning/ab_testing.py`:
- `ABTestManager.__init__(self, event_bus)` — in-memory `_experiments` dict
- `create_experiment(task_category, variants)` — build ABExperiment + ABVariants, set epsilon based on category, store, emit event
- `get_variant(task_category, user_id)` — find RUNNING experiment for category, epsilon-greedy selection (random.random() < epsilon → random variant, else highest win_rate)
- `record_feedback(variant_id, score)` — find variant across experiments, append score, increment sample_count, recalculate win_rate, call `check_conclusion()`
- `check_conclusion(experiment_id)` — all variants >= min_samples AND highest win_rate - second highest > 0.1 → conclude, set winner, emit `learning.ab.concluded`
- `pause_experiment(experiment_id)` — status → PAUSED
- `get_experiments(status=None)` — filtered list

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_ab.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/learning/ab_testing.py backend/tests/test_learning_ab.py
git commit -m "feat(5b1): add ABTestManager with epsilon-greedy variant assignment"
```

---

## Task 6: LLM Router A/B Integration

**Files:**
- Modify: `backend/nobla/brain/router.py`
- Test: `backend/tests/test_learning_ab.py` (extend)

- [ ] **Step 1: Write failing tests for router integration**

Add to `backend/tests/test_learning_ab.py`:

```python
class TestRouterIntegration:
    """Tests for LLMRouter A/B variant injection."""

    @pytest.mark.asyncio
    async def test_get_variant_hook_called_when_ab_manager_set(self):
        """Router calls ab_manager.get_variant() during route()."""
        from nobla.brain.router import LLMRouter
        from nobla.learning.ab_testing import ABTestManager

        ab = AsyncMock(spec=ABTestManager)
        variant = MagicMock()
        variant.model = "claude-3-sonnet"
        variant.id = "var-1"
        variant.prompt_template = None
        ab.get_variant = AsyncMock(return_value=variant)

        router = LLMRouter(ab_manager=ab)
        # route() should call get_variant and use the returned model
        result = await router.route("test prompt", task_category="hard", user_id="u1")
        ab.get_variant.assert_called_once_with("hard", "u1")

    @pytest.mark.asyncio
    async def test_route_without_ab_manager_uses_default(self):
        """Router works normally when ab_manager is None."""
        from nobla.brain.router import LLMRouter

        router = LLMRouter(ab_manager=None)
        # Should not raise, should use default _PREFERENCE routing
        result = await router.route("test prompt", task_category="easy")
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_preference_changes_default(self):
        """update_preference() modifies the default model for a category."""
        from nobla.brain.router import LLMRouter

        router = LLMRouter()
        router.update_preference("hard", "claude-3-sonnet")
        # The preference dict should now have claude-3-sonnet as primary for hard
        prefs = router.get_preference("hard")
        assert prefs[0] == "claude-3-sonnet"

    @pytest.mark.asyncio
    async def test_no_active_experiment_returns_none(self):
        """get_variant returns None when no experiment is running for category."""
        from nobla.learning.ab_testing import ABTestManager

        ab = ABTestManager(event_bus=AsyncMock())
        variant = await ab.get_variant("hard", "u1")
        assert variant is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_ab.py::TestRouterIntegration -v`
Expected: FAIL — LLMRouter doesn't accept ab_manager yet

- [ ] **Step 3: Modify LLMRouter**

Edit `backend/nobla/brain/router.py`:
- Add `ab_manager: ABTestManager | None = None` parameter to `__init__`
- In `route()` and `stream_route()`: if `ab_manager` is not None, call `await ab_manager.get_variant(task_category, user_id)` before building candidates; if variant returned, override primary model selection with `variant.model`, tag response metadata with `variant.id`
- Add `update_preference(task_category: str, model: str)` method: moves `model` to position 0 in `_PREFERENCE[task_category]`
- Add `get_preference(task_category: str) -> list[str]` method: returns current preference list

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_ab.py -v`
Expected: all PASS (both original ABTestManager tests and new router integration tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/brain/router.py backend/tests/test_learning_ab.py
git commit -m "feat(5b1): add A/B variant hook to LLMRouter"
```

---

## Task 7: ProactiveEngine

**Files:**
- Create: `backend/nobla/learning/proactive.py`
- Test: `backend/tests/test_learning_proactive.py`

- [ ] **Step 1: Write failing tests for ProactiveEngine**

Create `backend/tests/test_learning_proactive.py`:

```python
"""Tests for Phase 5B.1 ProactiveEngine — suggestions, snooze, dismiss, auto-expire."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.proactive import ProactiveEngine
from nobla.learning.models import (
    ProactiveConfig,
    ProactiveLevel,
    ProactiveSuggestion,
    SuggestionStatus,
    SuggestionType,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


def _make_config(level=ProactiveLevel.CONSERVATIVE, max_per_day=1):
    return ProactiveConfig(level=level, max_suggestions_per_day=max_per_day)


def _make_suggestion(suggestion_id=None, confidence=0.95, status=SuggestionStatus.PENDING,
                     stype=SuggestionType.PATTERN, snooze_count=0, snooze_until=None):
    return ProactiveSuggestion(
        id=suggestion_id or str(uuid.uuid4()),
        type=stype, title="Test", description="desc",
        confidence=confidence, action={"wf": "1"}, user_id="user-1",
        status=status, snooze_until=snooze_until, snooze_count=snooze_count,
        expires_at=None, created_at=datetime.now(timezone.utc), source_pattern_id=None,
    )


class TestLevelFiltering:
    @pytest.mark.asyncio
    async def test_off_returns_nothing(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.OFF))
        engine.add_candidate(_make_suggestion(confidence=0.99))
        result = await engine.evaluate_suggestions("user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_conservative_filters_below_90(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.CONSERVATIVE))
        engine.add_candidate(_make_suggestion(confidence=0.85))
        engine.add_candidate(_make_suggestion(confidence=0.95))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1
        assert result[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_moderate_filters_below_70(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.MODERATE))
        engine.add_candidate(_make_suggestion(confidence=0.65))
        engine.add_candidate(_make_suggestion(confidence=0.75))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_aggressive_filters_below_50(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.AGGRESSIVE))
        engine.add_candidate(_make_suggestion(confidence=0.45))
        engine.add_candidate(_make_suggestion(confidence=0.55))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1


class TestMaxPerDay:
    @pytest.mark.asyncio
    async def test_conservative_max_1_per_day(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(max_per_day=1))
        engine.add_candidate(_make_suggestion(confidence=0.95))
        engine.add_candidate(_make_suggestion(confidence=0.92))
        result = await engine.evaluate_suggestions("user-1")
        assert len(result) == 1


class TestAccept:
    @pytest.mark.asyncio
    async def test_accept_returns_action(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        s = _make_suggestion(suggestion_id="s1")
        engine.add_candidate(s)
        action = await engine.accept_suggestion("s1")
        assert action == {"wf": "1"}

    @pytest.mark.asyncio
    async def test_accept_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.accept_suggestion("s1")
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.accepted"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_accept_boosts_confidence(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.PATTERN))
        await engine.accept_suggestion("s1")
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(0.1)


class TestDismiss:
    @pytest.mark.asyncio
    async def test_dismiss_sets_status(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.dismiss_suggestion("s1", reason="irrelevant")
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.DISMISSED

    @pytest.mark.asyncio
    async def test_dismiss_applies_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.PATTERN))
        await engine.dismiss_suggestion("s1", reason="wrong")
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(-0.2)

    @pytest.mark.asyncio
    async def test_dismiss_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.dismiss_suggestion("s1")
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.dismissed"]
        assert len(calls) == 1


class TestSnooze:
    @pytest.mark.asyncio
    async def test_snooze_sets_status_and_until(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.snooze_suggestion("s1", days=3)
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.SNOOZED
        assert s.snooze_count == 1
        assert s.snooze_until is not None

    @pytest.mark.asyncio
    async def test_snooze_1_2x_no_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", stype=SuggestionType.OPTIMIZATION))
        await engine.snooze_suggestion("s1", days=1)
        assert engine.get_confidence_adjustment(SuggestionType.OPTIMIZATION) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_snooze_3x_applies_soft_penalty(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", snooze_count=2, stype=SuggestionType.PATTERN))
        await engine.snooze_suggestion("s1", days=1)  # now count=3
        assert engine.get_confidence_adjustment(SuggestionType.PATTERN) == pytest.approx(-0.05)

    @pytest.mark.asyncio
    async def test_snooze_5x_auto_expires(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1", snooze_count=4))
        await engine.snooze_suggestion("s1", days=1)  # now count=5
        s = engine.get_suggestion("s1")
        assert s.status == SuggestionStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_snooze_emits_event(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        engine.add_candidate(_make_suggestion(suggestion_id="s1"))
        await engine.snooze_suggestion("s1", days=7)
        calls = [c for c in event_bus.emit.call_args_list if c[0][0].event_type == "learning.suggestion.snoozed"]
        assert len(calls) == 1


class TestCheckSnoozed:
    @pytest.mark.asyncio
    async def test_expired_snooze_resets_to_pending(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        engine.add_candidate(_make_suggestion(
            suggestion_id="s1", status=SuggestionStatus.SNOOZED,
            snooze_until=past, snooze_count=1,
        ))
        reactivated = await engine.check_snoozed()
        assert len(reactivated) == 1
        assert reactivated[0].status == SuggestionStatus.PENDING

    @pytest.mark.asyncio
    async def test_future_snooze_stays_snoozed(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config())
        future = datetime.now(timezone.utc) + timedelta(days=2)
        engine.add_candidate(_make_suggestion(
            suggestion_id="s1", status=SuggestionStatus.SNOOZED,
            snooze_until=future, snooze_count=1,
        ))
        reactivated = await engine.check_snoozed()
        assert len(reactivated) == 0


class TestBriefing:
    @pytest.mark.asyncio
    async def test_briefing_only_when_aggressive(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.CONSERVATIVE))
        result = await engine.generate_briefing("user-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_briefing_generated_when_aggressive(self, event_bus):
        engine = ProactiveEngine(event_bus=event_bus, config=_make_config(ProactiveLevel.AGGRESSIVE))
        result = await engine.generate_briefing("user-1")
        assert result is not None
        assert result.type == SuggestionType.BRIEFING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_proactive.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ProactiveEngine**

Create `backend/nobla/learning/proactive.py`:
- `ProactiveEngine.__init__(self, event_bus, config: ProactiveConfig)` — in-memory `_suggestions` dict, `_confidence_penalties` dict (type → penalty), `_daily_counts` dict (user_id → date → count)
- `evaluate_suggestions(user_id)` — check patterns for suggestions, check A/B results for optimization suggestions; filter by confidence threshold and daily limit; return list
- `accept_suggestion(suggestion_id)` — update status, emit, return action
- `dismiss_suggestion(suggestion_id, reason)` — update status, record reason, apply -0.2 penalty to type, emit
- `snooze_suggestion(suggestion_id, days)` — update status + snooze_until + snooze_count; if snooze_count >= max_snooze_count → EXPIRED; if 3-4 → apply -0.05; emit
- `check_snoozed()` — scan for snooze_until < now, reset to PENDING
- `generate_briefing(user_id)` — only if level == AGGRESSIVE, return summary suggestion
- `get_suggestions(user_id, status=None)` — filtered list

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_proactive.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/learning/proactive.py backend/tests/test_learning_proactive.py
git commit -m "feat(5b1): add ProactiveEngine with snooze/dismiss/auto-expire"
```

---

## Task 8: LearningService + Gateway Wiring

**Files:**
- Create: `backend/nobla/learning/service.py`
- Create: `backend/nobla/gateway/learning_handlers.py`
- Modify: `backend/nobla/gateway/lifespan.py`
- Test: `backend/tests/test_learning_service.py`

- [ ] **Step 1: Write failing tests for LearningService**

Create `backend/tests/test_learning_service.py` with tests for:
- `start()` — registers event bus subscriptions (tool.executed, tool.failed, agent.a2a.task.result, scheduler.task.executed)
- `stop()` — unsubscribes all handlers
- `start()` skipped when `settings.learning.enabled == False`
- Kill switch active → start() is no-op
- Delegates to sub-components: submit_feedback → FeedbackCollector, get_patterns → PatternDetector, etc.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_learning_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement LearningService**

Create `backend/nobla/learning/service.py`:
- `LearningService.__init__(self, event_bus, feedback, patterns, generator, ab_testing, proactive, settings)` — stores all sub-components
- `start()` — check settings.enabled, subscribe to events (route tool.executed to both feedback.on_tool_executed and patterns.on_tool_executed)
- `stop()` — unsubscribe all
- Delegation methods: `submit_feedback()`, `get_patterns()`, `create_macro()`, etc.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_learning_service.py -v`
Expected: all PASS

- [ ] **Step 5: Implement REST handlers**

Create `backend/nobla/gateway/learning_handlers.py`:
- FastAPI `APIRouter(prefix="/api/learning")`
- Pydantic request/response schemas for each endpoint
- 22 routes total matching spec Section 10 (feedback: 3, patterns: 3, macros: 5, experiments: 4, suggestions: 4, settings: 3)
- All routes get `learning_service` from `request.app.state.learning_service`

- [ ] **Step 6: Wire into gateway lifespan**

Modify `backend/nobla/gateway/lifespan.py`:
- Import `LearningService`, `FeedbackCollector`, `PatternDetector`, `SkillGenerator`, `ABTestManager`, `ProactiveEngine`
- After workflow_service init: instantiate all learning components, create LearningService
- Call `await learning_service.start()` if enabled and kill switch not active
- Set `app.state.learning_service = learning_service`
- Include `learning_router` on app
- In shutdown: `await learning_service.stop()`

- [ ] **Step 7: Write handler tests**

Create `backend/tests/test_learning_handlers.py`:

```python
"""Tests for Phase 5B.1 REST API handlers — request validation, response shape, errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from nobla.gateway.learning_handlers import learning_router


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.submit_feedback = AsyncMock(return_value=None)
    svc.get_feedback_for_conversation = AsyncMock(return_value=[])
    svc.get_feedback_stats = AsyncMock(return_value={"total": 0, "positive": 0, "negative": 0})
    svc.get_patterns = AsyncMock(return_value=[])
    svc.dismiss_pattern = AsyncMock(return_value=None)
    svc.get_macros = AsyncMock(return_value=[])
    svc.promote_to_skill = AsyncMock(return_value={"skill_id": "s1"})
    svc.get_experiments = AsyncMock(return_value=[])
    svc.get_suggestions = AsyncMock(return_value=[])
    svc.accept_suggestion = AsyncMock(return_value={"wf": "1"})
    svc.dismiss_suggestion = AsyncMock(return_value=None)
    svc.snooze_suggestion = AsyncMock(return_value=None)
    svc.get_settings = MagicMock(return_value={"enabled": True, "proactive_level": "conservative"})
    svc.update_settings = AsyncMock(return_value=None)
    svc.clear_data = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.state.learning_service = mock_service
    app.include_router(learning_router)
    return TestClient(app)


class TestFeedbackEndpoints:
    def test_submit_feedback(self, client, mock_service):
        resp = client.post("/api/learning/feedback", json={
            "conversation_id": "c1", "message_id": "m1",
            "quick_rating": 1, "context": {"llm_model": "gemini"},
        })
        assert resp.status_code == 200
        mock_service.submit_feedback.assert_called_once()

    def test_get_feedback_stats(self, client):
        resp = client.get("/api/learning/feedback/stats")
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_get_feedback_by_conversation(self, client):
        resp = client.get("/api/learning/feedback?conversation_id=c1")
        assert resp.status_code == 200


class TestPatternEndpoints:
    def test_list_patterns(self, client):
        resp = client.get("/api/learning/patterns")
        assert resp.status_code == 200

    def test_dismiss_pattern(self, client, mock_service):
        resp = client.post("/api/learning/patterns/pat-1/dismiss")
        assert resp.status_code == 200
        mock_service.dismiss_pattern.assert_called_once_with("pat-1")


class TestMacroEndpoints:
    def test_list_macros(self, client):
        resp = client.get("/api/learning/macros")
        assert resp.status_code == 200

    def test_promote_macro(self, client, mock_service):
        resp = client.post("/api/learning/macros/m1/promote")
        assert resp.status_code == 200
        mock_service.promote_to_skill.assert_called_once_with("m1")

    def test_delete_macro(self, client, mock_service):
        resp = client.delete("/api/learning/macros/m1")
        assert resp.status_code == 200


class TestSuggestionEndpoints:
    def test_accept_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/accept")
        assert resp.status_code == 200
        mock_service.accept_suggestion.assert_called_once_with("s1")

    def test_dismiss_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/dismiss", json={"reason": "irrelevant"})
        assert resp.status_code == 200

    def test_snooze_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/snooze", json={"days": 3})
        assert resp.status_code == 200
        mock_service.snooze_suggestion.assert_called_once_with("s1", 3)


class TestSettingsEndpoints:
    def test_get_settings(self, client):
        resp = client.get("/api/learning/settings")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_update_settings(self, client, mock_service):
        resp = client.put("/api/learning/settings", json={"proactive_level": "moderate"})
        assert resp.status_code == 200

    def test_clear_data(self, client, mock_service):
        resp = client.delete("/api/learning/data")
        assert resp.status_code == 200
        mock_service.clear_data.assert_called_once()
```

- [ ] **Step 8: Run all learning tests together**

Run: `cd backend && python -m pytest tests/test_learning_models.py tests/test_learning_feedback.py tests/test_learning_patterns.py tests/test_learning_generator.py tests/test_learning_ab.py tests/test_learning_proactive.py tests/test_learning_service.py tests/test_learning_handlers.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add backend/nobla/learning/service.py backend/nobla/gateway/learning_handlers.py backend/nobla/gateway/lifespan.py backend/tests/test_learning_service.py backend/tests/test_learning_handlers.py
git commit -m "feat(5b1): add LearningService, REST API (22 routes), gateway wiring"
```

---

## Task 9: Flutter Models + Providers

**Files:**
- Create: `app/lib/features/learning/models/learning_models.dart`
- Create: `app/lib/features/learning/providers/learning_providers.dart`
- Test: `app/test/features/learning/learning_models_test.dart`

- [ ] **Step 1: Write failing tests for Dart models**

Create `app/test/features/learning/learning_models_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';

void main() {
  group('PatternStatus', () {
    test('has all values', () {
      expect(PatternStatus.values.length, 4);
      expect(PatternStatus.detected.name, 'detected');
    });
  });

  group('SuggestionStatus', () {
    test('has snoozed status', () {
      expect(SuggestionStatus.snoozed.name, 'snoozed');
    });
    test('has all 5 values', () {
      expect(SuggestionStatus.values.length, 5);
    });
  });

  group('ProactiveLevel', () {
    test('has all 4 values', () {
      expect(ProactiveLevel.values.length, 4);
    });
  });

  group('ResponseFeedback', () {
    test('fromJson round-trip', () {
      final json = {
        'id': 'fb-1',
        'conversation_id': 'conv-1',
        'message_id': 'msg-1',
        'user_id': 'user-1',
        'quick_rating': 1,
        'star_rating': 5,
        'comment': 'Great!',
        'context': {
          'llm_model': 'gemini-pro',
          'tool_chain': ['code.run'],
        },
        'timestamp': '2026-03-28T10:00:00Z',
      };
      final fb = ResponseFeedback.fromJson(json);
      expect(fb.quickRating, 1);
      expect(fb.starRating, 5);
      expect(fb.isPositive, true);
      expect(fb.toJson()['quick_rating'], 1);
    });

    test('isNegative for thumbs down', () {
      final fb = ResponseFeedback.fromJson({
        'id': 'fb-2', 'conversation_id': 'c', 'message_id': 'm',
        'user_id': 'u', 'quick_rating': -1, 'context': {'llm_model': 'x', 'tool_chain': []},
        'timestamp': '2026-03-28T10:00:00Z',
      });
      expect(fb.isNegative, true);
    });
  });

  group('PatternCandidate', () {
    test('fromJson creates pattern', () {
      final json = {
        'id': 'pat-1', 'user_id': 'u', 'fingerprint': 'abc',
        'description': 'test', 'occurrences': [], 'tool_sequence': ['a', 'b'],
        'variable_params': {}, 'status': 'detected', 'confidence': 0.8,
        'detection_method': 'sequence', 'created_at': '2026-03-28T10:00:00Z',
      };
      final p = PatternCandidate.fromJson(json);
      expect(p.status, PatternStatus.detected);
      expect(p.toolSequence, ['a', 'b']);
    });
  });

  group('ProactiveSuggestion', () {
    test('fromJson with snooze fields', () {
      final json = {
        'id': 's-1', 'type': 'pattern', 'title': 'Test',
        'description': 'desc', 'confidence': 0.9, 'user_id': 'u',
        'status': 'snoozed', 'snooze_until': '2026-03-30T10:00:00Z',
        'snooze_count': 2, 'created_at': '2026-03-28T10:00:00Z',
      };
      final s = ProactiveSuggestion.fromJson(json);
      expect(s.status, SuggestionStatus.snoozed);
      expect(s.snoozeCount, 2);
      expect(s.snoozeUntil, isNotNull);
    });
  });

  group('LearningSettings', () {
    test('fromJson defaults', () {
      final s = LearningSettings.fromJson({
        'enabled': true,
        'proactive_level': 'conservative',
      });
      expect(s.enabled, true);
      expect(s.proactiveLevel, ProactiveLevel.conservative);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/learning/learning_models_test.dart`
Expected: FAIL — compilation error

- [ ] **Step 3: Implement Dart models**

Create `app/lib/features/learning/models/learning_models.dart`:
- Enums: `PatternStatus`, `MacroTier`, `ExperimentStatus`, `SuggestionType`, `SuggestionStatus`, `ProactiveLevel`
- Classes with `fromJson`/`toJson`: `FeedbackContext`, `ResponseFeedback` (with `isPositive`/`isNegative` getters), `PatternOccurrence`, `PatternCandidate`, `MacroParameter`, `WorkflowMacro`, `ABVariant`, `ABExperiment`, `ProactiveSuggestion`, `LearningSettings`
- Follow existing pattern: immutable classes, snake_case JSON keys mapped to camelCase Dart fields

- [ ] **Step 4: Implement Riverpod providers**

Create `app/lib/features/learning/providers/learning_providers.dart`:
- `feedbackStatsProvider` — FutureProvider fetching GET `/api/learning/feedback/stats`
- `patternListProvider` — FutureProvider fetching GET `/api/learning/patterns`
- `macroListProvider` — FutureProvider fetching GET `/api/learning/macros`
- `experimentListProvider` — FutureProvider fetching GET `/api/learning/experiments`
- `suggestionListProvider` — FutureProvider fetching GET `/api/learning/suggestions`
- `learningSettingsProvider` — StateNotifierProvider for GET/PUT `/api/learning/settings`
- Action providers: `submitFeedbackProvider`, `dismissPatternProvider`, `promoteMacroProvider`, `acceptSuggestionProvider`, `dismissSuggestionProvider`, `snoozeSuggestionProvider`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/learning/learning_models_test.dart`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/lib/features/learning/models/learning_models.dart app/lib/features/learning/providers/learning_providers.dart app/test/features/learning/learning_models_test.dart
git commit -m "feat(5b1): add Flutter learning models, providers, and model tests"
```

---

## Task 10: Flutter Widgets

**Files:**
- Create: `app/lib/features/learning/widgets/feedback_widget.dart`
- Create: `app/lib/features/learning/widgets/pattern_card.dart`
- Create: `app/lib/features/learning/widgets/suggestion_card.dart`
- Create: `app/lib/features/learning/widgets/learning_stats_widget.dart`
- Test: `app/test/features/learning/widgets_test.dart`

- [ ] **Step 1: Write failing tests for widgets**

Create `app/test/features/learning/widgets_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/learning/models/learning_models.dart';
import 'package:nobla_agent/features/learning/widgets/feedback_widget.dart';
import 'package:nobla_agent/features/learning/widgets/pattern_card.dart';
import 'package:nobla_agent/features/learning/widgets/suggestion_card.dart';
import 'package:nobla_agent/features/learning/widgets/learning_stats_widget.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: Scaffold(body: child)),
  );
}

void main() {
  group('FeedbackWidget', () {
    testWidgets('shows thumbs up and down buttons', (tester) async {
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (_) {}),
      ));
      expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
      expect(find.byIcon(Icons.thumb_down_outlined), findsOneWidget);
    });

    testWidgets('tap thumbs up calls callback with 1', (tester) async {
      int? rating;
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (r) => rating = r),
      ));
      await tester.tap(find.byIcon(Icons.thumb_up_outlined));
      await tester.pump();
      expect(rating, 1);
    });

    testWidgets('tap expands to star rating', (tester) async {
      await tester.pumpWidget(_wrap(
        FeedbackWidget(messageId: 'msg-1', onFeedback: (_) {}),
      ));
      await tester.tap(find.byIcon(Icons.thumb_up_outlined));
      await tester.pumpAndSettle();
      // Should show 5 star icons after expansion
      expect(find.byIcon(Icons.star_border), findsNWidgets(5));
    });
  });

  group('PatternCard', () {
    testWidgets('shows pattern description', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'file.manage → code.run',
          status: PatternStatus.detected,
          confidence: 0.85,
          onReview: () {},
          onDismiss: () {},
        ),
      ));
      expect(find.text('file.manage → code.run'), findsOneWidget);
    });

    testWidgets('shows Review and Dismiss buttons', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'test', status: PatternStatus.detected,
          confidence: 0.8, onReview: () {}, onDismiss: () {},
        ),
      ));
      expect(find.text('Review'), findsOneWidget);
      expect(find.text('Dismiss'), findsOneWidget);
    });

    testWidgets('shows status chip', (tester) async {
      await tester.pumpWidget(_wrap(
        PatternCard(
          description: 'test', status: PatternStatus.confirmed,
          confidence: 0.9, onReview: () {}, onDismiss: () {},
        ),
      ));
      expect(find.text('confirmed'), findsOneWidget);
    });
  });

  group('SuggestionCard', () {
    testWidgets('shows title and description', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 'Automate deploy',
          description: 'You do this every Monday',
          type: SuggestionType.pattern,
          onAccept: () {},
          onDismiss: () {},
          onSnooze: (_) {},
        ),
      ));
      expect(find.text('Automate deploy'), findsOneWidget);
      expect(find.text('You do this every Monday'), findsOneWidget);
    });

    testWidgets('shows Accept, Snooze, Dismiss actions', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 't', description: 'd', type: SuggestionType.pattern,
          onAccept: () {}, onDismiss: () {}, onSnooze: (_) {},
        ),
      ));
      expect(find.text('Accept'), findsOneWidget);
      expect(find.text('Snooze'), findsOneWidget);
      expect(find.text('Dismiss'), findsOneWidget);
    });

    testWidgets('snooze shows duration options', (tester) async {
      await tester.pumpWidget(_wrap(
        SuggestionCard(
          title: 't', description: 'd', type: SuggestionType.pattern,
          onAccept: () {}, onDismiss: () {}, onSnooze: (_) {},
        ),
      ));
      await tester.tap(find.text('Snooze'));
      await tester.pumpAndSettle();
      expect(find.text('1 day'), findsOneWidget);
      expect(find.text('3 days'), findsOneWidget);
      expect(find.text('7 days'), findsOneWidget);
    });
  });

  group('LearningStatsWidget', () {
    testWidgets('shows stat labels', (tester) async {
      await tester.pumpWidget(_wrap(
        LearningStatsWidget(
          feedbackCount: 42,
          positiveCount: 35,
          negativeCount: 7,
          patternsDetected: 5,
          autoSkillsActive: 2,
          experimentsRunning: 1,
        ),
      ));
      expect(find.text('42'), findsOneWidget);
      expect(find.text('Feedback'), findsOneWidget);
      expect(find.text('Patterns'), findsOneWidget);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/learning/widgets_test.dart`
Expected: FAIL — compilation error

- [ ] **Step 3: Implement widgets**

Create all four widget files:
- `feedback_widget.dart` — `FeedbackWidget(messageId, onFeedback)`: Row with thumb_up/thumb_down IconButtons. On tap, show thumb filled + AnimatedContainer expanding to show 5 star icons + TextField for comment.
- `pattern_card.dart` — `PatternCard(description, status, confidence, onReview, onDismiss)`: Card with description, status Chip, confidence percentage, Review + Dismiss TextButtons.
- `suggestion_card.dart` — `SuggestionCard(title, description, type, onAccept, onDismiss, onSnooze)`: Card with type icon, title, description, three action buttons. Snooze shows PopupMenuButton with 1/3/7 day options.
- `learning_stats_widget.dart` — `LearningStatsWidget(feedbackCount, positiveCount, negativeCount, patternsDetected, autoSkillsActive, experimentsRunning)`: Grid of stat cards with icons and numbers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && flutter test test/features/learning/widgets_test.dart`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/lib/features/learning/widgets/ app/test/features/learning/widgets_test.dart
git commit -m "feat(5b1): add Flutter learning widgets — feedback, pattern, suggestion, stats"
```

---

## Task 11: Flutter Screen + Router Wiring

**Files:**
- Create: `app/lib/features/learning/screens/agent_intelligence_screen.dart`
- Modify: `app/lib/core/routing/app_router.dart`
- Test: `app/test/features/learning/screens_test.dart`

- [ ] **Step 1: Write failing tests for screen**

Create `app/test/features/learning/screens_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/learning/providers/learning_providers.dart';
import 'package:nobla_agent/features/learning/screens/agent_intelligence_screen.dart';

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

void main() {
  group('AgentIntelligenceScreen', () {
    testWidgets('shows 4 tabs', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: [
          feedbackStatsProvider.overrideWith((_) async => {
            'total': 0, 'positive': 0, 'negative': 0,
          }),
          patternListProvider.overrideWith((_) async => []),
          macroListProvider.overrideWith((_) async => []),
          experimentListProvider.overrideWith((_) async => []),
          suggestionListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Overview'), findsOneWidget);
      expect(find.text('Patterns'), findsOneWidget);
      expect(find.text('Auto-Skills'), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('tabs are tappable', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: [
          feedbackStatsProvider.overrideWith((_) async => {
            'total': 0, 'positive': 0, 'negative': 0,
          }),
          patternListProvider.overrideWith((_) async => []),
          macroListProvider.overrideWith((_) async => []),
          experimentListProvider.overrideWith((_) async => []),
          suggestionListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Patterns'));
      await tester.pumpAndSettle();
      // No crash = tab switch works
    });

    testWidgets('shows app bar with title', (tester) async {
      await tester.pumpWidget(_wrap(
        const AgentIntelligenceScreen(),
        overrides: [
          feedbackStatsProvider.overrideWith((_) async => {
            'total': 0, 'positive': 0, 'negative': 0,
          }),
          patternListProvider.overrideWith((_) async => []),
          macroListProvider.overrideWith((_) async => []),
          experimentListProvider.overrideWith((_) async => []),
          suggestionListProvider.overrideWith((_) async => []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Agent Intelligence'), findsOneWidget);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && flutter test test/features/learning/screens_test.dart`
Expected: FAIL

- [ ] **Step 3: Implement AgentIntelligenceScreen**

Create `app/lib/features/learning/screens/agent_intelligence_screen.dart`:
- `AgentIntelligenceScreen` — StatelessWidget with `DefaultTabController(length: 4)`
- AppBar with title "Agent Intelligence" and `TabBar` with 4 tabs: Overview, Patterns, Auto-Skills, Settings
- `TabBarView` with 4 tab bodies:
  - **Overview**: Consumer widget using feedbackStatsProvider + patternListProvider + macroListProvider + experimentListProvider → LearningStatsWidget
  - **Patterns**: Consumer with patternListProvider → ListView of PatternCards with dismiss/review callbacks
  - **Auto-Skills**: Consumer with macroListProvider → ListView of macro cards with tier badges, promote button, publish toggle
  - **Settings**: Consumer with learningSettingsProvider → proactive level slider, A/B toggle, clear data button

- [ ] **Step 4: Add route to app_router.dart**

Modify `app/lib/core/routing/app_router.dart`:
- Add import for `AgentIntelligenceScreen`
- Add a `GoRoute` under the settings route (or as a sibling within the ShellRoute):
  ```dart
  GoRoute(
    path: '/home/settings/intelligence',
    builder: (context, state) => const AgentIntelligenceScreen(),
  ),
  ```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && flutter test test/features/learning/screens_test.dart`
Expected: all PASS

- [ ] **Step 6: Run all Flutter learning tests**

Run: `cd app && flutter test test/features/learning/`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add app/lib/features/learning/screens/agent_intelligence_screen.dart app/lib/core/routing/app_router.dart app/test/features/learning/screens_test.dart
git commit -m "feat(5b1): add AgentIntelligenceScreen with 4 tabs + router wiring"
```

---

## Task 12: Integration Verification + CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run all backend learning tests**

Run: `cd backend && python -m pytest tests/test_learning_models.py tests/test_learning_feedback.py tests/test_learning_patterns.py tests/test_learning_generator.py tests/test_learning_ab.py tests/test_learning_proactive.py tests/test_learning_service.py -v`
Expected: ~180-220 tests, all PASS

- [ ] **Step 2: Run all Flutter learning tests**

Run: `cd app && flutter test test/features/learning/`
Expected: ~60-80 tests, all PASS

- [ ] **Step 3: Run full backend test suite (ensure no regressions)**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/test_chat_flow.py --ignore=tests/test_consolidation.py --ignore=tests/test_extraction.py --ignore=tests/test_orchestrator.py --ignore=tests/test_routes.py --ignore=tests/test_security_integration.py --ignore=tests/test_websocket.py`
Expected: all existing 845 tests + new learning tests PASS

- [ ] **Step 4: Run full Flutter test suite**

Run: `cd app && flutter test`
Expected: all existing 217 tests + new learning tests PASS

- [ ] **Step 5: Verify line counts**

Run: `find backend/nobla/learning -name "*.py" -exec wc -l {} + | sort -rn`
Expected: all files < 750 lines

- [ ] **Step 6: Update CLAUDE.md**

Add Phase 5B.1 to Completed Phases and update test counts. Add `learning/` to Project Structure. Update Phase 5 sub-phases table.

- [ ] **Step 7: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 5B.1 Self-Improving Agent completion"
```
