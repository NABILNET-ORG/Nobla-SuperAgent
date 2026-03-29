"""LearningService — orchestrates all learning components."""
from __future__ import annotations
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


class LearningService:
    def __init__(self, event_bus, settings, feedback, patterns, generator, ab_testing, proactive):
        self._event_bus = event_bus
        self._settings = settings
        self._feedback = feedback
        self._patterns = patterns
        self._generator = generator
        self._ab_testing = ab_testing
        self._proactive = proactive
        self._subscriptions: list = []
        self._started = False

    async def start(self) -> None:
        if not self._settings.enabled:
            logger.info("learning_service_disabled")
            return
        self._subscriptions.append(
            self._event_bus.subscribe("tool.executed", self._on_tool_executed)
        )
        self._subscriptions.append(
            self._event_bus.subscribe("tool.failed", self._feedback.on_tool_executed)
        )
        self._started = True
        logger.info("learning_service_started")

    async def stop(self) -> None:
        for sub_id in self._subscriptions:
            self._event_bus.unsubscribe(sub_id)
        self._subscriptions.clear()
        self._started = False
        logger.info("learning_service_stopped")

    async def _on_tool_executed(self, event) -> None:
        await self._feedback.on_tool_executed(event)
        await self._patterns.on_tool_executed(event)

    # --- Feedback delegation ---
    async def submit_feedback(self, feedback):
        return await self._feedback.submit_feedback(feedback)

    async def get_feedback_for_conversation(self, conversation_id: str):
        return await self._feedback.get_feedback_for_conversation(conversation_id)

    async def get_feedback_stats(self, user_id: str):
        return await self._feedback.get_feedback_stats(user_id)

    # --- Pattern delegation ---
    async def get_patterns(self, user_id: str, status=None):
        return await self._patterns.get_patterns(user_id, status=status)

    async def dismiss_pattern(self, pattern_id: str):
        return await self._patterns.dismiss_pattern(pattern_id)

    # --- Generator delegation ---
    async def create_macro(self, pattern):
        return await self._generator.create_macro(pattern)

    async def promote_to_skill(self, macro_id: str):
        return await self._generator.promote_to_skill(macro_id)

    async def mark_publishable(self, macro_id: str, metadata: dict):
        return await self._generator.mark_publishable(macro_id, metadata)

    async def get_macros(self, user_id: str, tier=None):
        return await self._generator.get_macros(user_id, tier=tier)

    async def delete_macro(self, macro_id: str):
        return await self._generator.delete_macro(macro_id)

    # --- A/B testing delegation ---
    async def create_experiment(self, task_category: str, variants: list):
        return await self._ab_testing.create_experiment(task_category, variants)

    async def get_experiments(self, status=None):
        return await self._ab_testing.get_experiments(status=status)

    async def pause_experiment(self, experiment_id: str):
        return await self._ab_testing.pause_experiment(experiment_id)

    # --- Proactive delegation ---
    async def evaluate_suggestions(self, user_id: str):
        return await self._proactive.evaluate_suggestions(user_id)

    async def accept_suggestion(self, suggestion_id: str):
        return await self._proactive.accept_suggestion(suggestion_id)

    async def dismiss_suggestion(self, suggestion_id: str, reason: str | None = None):
        return await self._proactive.dismiss_suggestion(suggestion_id, reason=reason)

    async def snooze_suggestion(self, suggestion_id: str, days: int):
        return await self._proactive.snooze_suggestion(suggestion_id, days=days)

    async def get_suggestions(self, user_id: str, status=None):
        return await self._proactive.get_suggestions(user_id, status=status)

    # --- Settings ---
    def get_settings(self) -> dict:
        return {"enabled": self._settings.enabled, "proactive_level": self._settings.proactive_level}

    async def update_settings(self, updates: dict) -> None:
        for k, v in updates.items():
            if hasattr(self._settings, k):
                setattr(self._settings, k, v)

    async def clear_data(self) -> None:
        self._feedback._feedback.clear()
        self._feedback._tool_chains.clear()
        self._patterns._patterns.clear()
        self._patterns._fingerprint_occurrences.clear()
        self._generator._macros.clear()
        self._ab_testing._experiments.clear()
        self._proactive._suggestions.clear()
