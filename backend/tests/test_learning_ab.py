"""Tests for Phase 5B.1 ABTestManager — experiments, epsilon-greedy, conclusion."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.learning.ab_testing import ABTestManager
from nobla.learning.models import (
    ABExperiment,
    ABVariant,
    ExperimentStatus,
)


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def manager(event_bus):
    return ABTestManager(event_bus=event_bus)


class TestCreateExperiment:
    @pytest.mark.asyncio
    async def test_creates_experiment(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4", "prompt_template": None},
            {"model": "claude-3", "prompt_template": None},
        ])
        assert exp.task_category == "hard"
        assert exp.status == ExperimentStatus.RUNNING
        assert len(exp.variants) == 2

    @pytest.mark.asyncio
    async def test_per_category_epsilon(self, manager):
        hard = await manager.create_experiment("hard", [
            {"model": "a"}, {"model": "b"},
        ])
        medium = await manager.create_experiment("medium", [
            {"model": "a"}, {"model": "b"},
        ])
        easy = await manager.create_experiment("easy", [
            {"model": "a"}, {"model": "b"},
        ])
        assert hard.epsilon == pytest.approx(0.1)
        assert medium.epsilon == pytest.approx(0.15)
        assert easy.epsilon == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_emits_started_event(self, manager, event_bus):
        await manager.create_experiment("easy", [{"model": "a"}, {"model": "b"}])
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "learning.ab.started"]
        assert len(calls) == 1


class TestGetVariant:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_experiment(self, manager):
        result = await manager.get_variant("hard", "user-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_variant_when_experiment_active(self, manager):
        await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        result = await manager.get_variant("hard", "user-1")
        assert result is not None
        assert result.model in ("gpt-4", "claude-3")

    @pytest.mark.asyncio
    async def test_epsilon_zero_always_exploits(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        # Give gpt-4 higher win rate
        for v in exp.variants:
            if v.model == "gpt-4":
                v.win_rate = 0.8
                v.sample_count = 5
            else:
                v.win_rate = 0.2
                v.sample_count = 5
        # With epsilon=0, should always pick highest win_rate
        random.seed(42)
        results = []
        for _ in range(10):
            v = await manager.get_variant("hard", "user-1", epsilon_override=0.0)
            results.append(v.model)
        assert all(m == "gpt-4" for m in results)

    @pytest.mark.asyncio
    async def test_epsilon_one_explores(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        for v in exp.variants:
            if v.model == "gpt-4":
                v.win_rate = 0.9
                v.sample_count = 5
        random.seed(42)
        results = set()
        for _ in range(20):
            v = await manager.get_variant("hard", "user-1", epsilon_override=1.0)
            results.add(v.model)
        assert len(results) == 2  # both models seen


class TestRecordFeedback:
    @pytest.mark.asyncio
    async def test_records_score(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        variant = exp.variants[0]
        await manager.record_feedback(variant.id, 0.8)
        assert variant.sample_count == 1
        assert 0.8 in variant.feedback_scores

    @pytest.mark.asyncio
    async def test_updates_win_rate(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        v0, v1 = exp.variants
        # Give v0 higher scores
        for _ in range(5):
            await manager.record_feedback(v0.id, 0.9)
            await manager.record_feedback(v1.id, 0.3)
        assert v0.win_rate > v1.win_rate


class TestConclusion:
    @pytest.mark.asyncio
    async def test_concludes_when_enough_samples(self, manager, event_bus):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        exp.min_samples = 5
        v0, v1 = exp.variants
        for _ in range(5):
            await manager.record_feedback(v0.id, 0.9)
            await manager.record_feedback(v1.id, 0.3)
        # Should be concluded now
        exps = await manager.get_experiments(status=ExperimentStatus.CONCLUDED)
        assert len(exps) == 1
        assert exps[0].winner_variant_id == v0.id

    @pytest.mark.asyncio
    async def test_emits_concluded_event(self, manager, event_bus):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        exp.min_samples = 3
        v0, v1 = exp.variants
        event_bus.emit.reset_mock()
        for _ in range(3):
            await manager.record_feedback(v0.id, 0.9)
            await manager.record_feedback(v1.id, 0.2)
        calls = [c for c in event_bus.emit.call_args_list
                 if c[0][0].event_type == "learning.ab.concluded"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_no_conclusion_if_gap_too_small(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        exp.min_samples = 3
        v0, v1 = exp.variants
        for _ in range(3):
            await manager.record_feedback(v0.id, 0.55)
            await manager.record_feedback(v1.id, 0.50)
        # Gap is small — should NOT conclude
        assert exp.status == ExperimentStatus.RUNNING


class TestPauseExperiment:
    @pytest.mark.asyncio
    async def test_pause_sets_status(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        await manager.pause_experiment(exp.id)
        assert exp.status == ExperimentStatus.PAUSED

    @pytest.mark.asyncio
    async def test_paused_experiment_returns_no_variant(self, manager):
        exp = await manager.create_experiment("hard", [
            {"model": "gpt-4"}, {"model": "claude-3"},
        ])
        await manager.pause_experiment(exp.id)
        result = await manager.get_variant("hard", "user-1")
        assert result is None
