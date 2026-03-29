"""ABTestManager — epsilon-greedy A/B testing for LLM models + prompt templates."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from nobla.events.models import NoblaEvent
from nobla.learning.models import ABExperiment, ABVariant, ExperimentStatus

logger = structlog.get_logger(__name__)

CATEGORY_EPSILON: dict[str, float] = {"easy": 0.2, "medium": 0.15, "hard": 0.1}
DEFAULT_MIN_SAMPLES = 20
WIN_RATE_GAP_THRESHOLD = 0.1


class ABTestManager:
    """Manages A/B experiments for LLM model and prompt-template selection.

    Uses an epsilon-greedy strategy:
      - With probability epsilon  → explore  (random variant)
      - With probability 1-epsilon → exploit (best win_rate variant)

    Experiments auto-conclude when all variants reach min_samples AND
    the gap between the top two win_rates exceeds WIN_RATE_GAP_THRESHOLD.
    """

    def __init__(self, event_bus: Any) -> None:
        self._event_bus = event_bus
        # Keyed by experiment id
        self._experiments: dict[str, ABExperiment] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_experiment(
        self,
        task_category: str,
        variants: list[dict[str, Any]],
    ) -> ABExperiment:
        """Create and store a new running experiment for *task_category*."""
        epsilon = CATEGORY_EPSILON.get(task_category, 0.2)
        ab_variants: list[ABVariant] = [
            ABVariant(
                id=str(uuid.uuid4()),
                model=v.get("model", ""),
                prompt_template=v.get("prompt_template"),
                feedback_scores=[],
                sample_count=0,
                win_rate=0.0,
            )
            for v in variants
        ]
        experiment = ABExperiment(
            id=str(uuid.uuid4()),
            task_category=task_category,
            variants=ab_variants,
            status=ExperimentStatus.RUNNING,
            min_samples=DEFAULT_MIN_SAMPLES,
            epsilon=epsilon,
            created_at=datetime.now(timezone.utc),
            concluded_at=None,
            winner_variant_id=None,
        )
        self._experiments[experiment.id] = experiment
        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.ab.started",
                source="ab_testing",
                payload={"experiment_id": experiment.id, "task_category": task_category},
            )
        )
        logger.info(
            "ab_experiment_started",
            experiment_id=experiment.id,
            task_category=task_category,
            num_variants=len(ab_variants),
        )
        return experiment

    async def get_variant(
        self,
        task_category: str,
        user_id: str,
        epsilon_override: float | None = None,
    ) -> ABVariant | None:
        """Return a variant for *task_category* using epsilon-greedy selection.

        Returns None when no RUNNING experiment exists for the category.
        """
        experiment = self._find_running(task_category)
        if experiment is None:
            return None

        epsilon = epsilon_override if epsilon_override is not None else experiment.epsilon

        if random.random() < epsilon:
            # Explore: pick uniformly at random
            return random.choice(experiment.variants)

        # Exploit: pick variant with highest win_rate
        return max(experiment.variants, key=lambda v: v.win_rate)

    async def record_feedback(self, variant_id: str, score: float) -> None:
        """Append *score* to the matching variant and update win rates.

        After updating, checks whether the experiment can be concluded.
        """
        experiment, variant = self._find_variant(variant_id)
        if experiment is None or variant is None:
            logger.warning("ab_variant_not_found", variant_id=variant_id)
            return

        variant.feedback_scores.append(score)
        variant.sample_count += 1

        # Recalculate win_rate for ALL variants in the experiment
        for v in experiment.variants:
            if v.feedback_scores:
                v.win_rate = sum(v.feedback_scores) / len(v.feedback_scores)

        await self._check_conclusion(experiment)

    async def pause_experiment(self, experiment_id: str) -> None:
        """Set experiment status to PAUSED."""
        exp = self._experiments.get(experiment_id)
        if exp is not None:
            exp.status = ExperimentStatus.PAUSED
            logger.info("ab_experiment_paused", experiment_id=experiment_id)

    async def get_experiments(
        self,
        status: ExperimentStatus | None = None,
    ) -> list[ABExperiment]:
        """Return all experiments, optionally filtered by *status*."""
        exps = list(self._experiments.values())
        if status is not None:
            exps = [e for e in exps if e.status == status]
        return exps

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_running(self, task_category: str) -> ABExperiment | None:
        """Return the first RUNNING experiment for *task_category*, or None."""
        for exp in self._experiments.values():
            if exp.task_category == task_category and exp.status == ExperimentStatus.RUNNING:
                return exp
        return None

    def _find_variant(
        self,
        variant_id: str,
    ) -> tuple[ABExperiment | None, ABVariant | None]:
        """Return (experiment, variant) pair for *variant_id* across all experiments."""
        for exp in self._experiments.values():
            for v in exp.variants:
                if v.id == variant_id:
                    return exp, v
        return None, None

    async def _check_conclusion(self, experiment: ABExperiment) -> None:
        """Conclude *experiment* when conditions are met.

        Conditions:
        1. All variants have sample_count >= min_samples.
        2. Gap between top-two win_rates > WIN_RATE_GAP_THRESHOLD.
        """
        if experiment.status != ExperimentStatus.RUNNING:
            return

        if not all(v.sample_count >= experiment.min_samples for v in experiment.variants):
            return

        sorted_variants = sorted(experiment.variants, key=lambda v: v.win_rate, reverse=True)
        best = sorted_variants[0]
        second = sorted_variants[1] if len(sorted_variants) > 1 else None

        gap = best.win_rate - (second.win_rate if second else 0.0)
        if gap <= WIN_RATE_GAP_THRESHOLD:
            return

        experiment.status = ExperimentStatus.CONCLUDED
        experiment.winner_variant_id = best.id
        experiment.concluded_at = datetime.now(timezone.utc)

        await self._event_bus.emit(
            NoblaEvent(
                event_type="learning.ab.concluded",
                source="ab_testing",
                payload={
                    "experiment_id": experiment.id,
                    "winner_variant_id": best.id,
                    "winner_model": best.model,
                    "win_rate": best.win_rate,
                },
            )
        )
        logger.info(
            "ab_experiment_concluded",
            experiment_id=experiment.id,
            winner_model=best.model,
            win_rate=best.win_rate,
            gap=gap,
        )
