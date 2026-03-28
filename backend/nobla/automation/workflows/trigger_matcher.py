"""Trigger matcher — subscribe to event bus, match workflows, fire executions (Phase 6).

Architecture:
    TriggerMatcher subscribes to the NoblaEventBus with a configurable
    event prefix (default ``*``).  For each incoming event it:

    1. Matches the event_type against all active WorkflowTrigger.event_pattern
       using ``fnmatch``.
    2. Evaluates the trigger's TriggerConditions against the event payload
       (AND logic — all conditions must pass).
    3. Deduplicates: same (trigger_id, correlation_id) within a configurable
       window (default 5s) is dropped.
    4. Calls the registered callback with (workflow_id, trigger, event).

    The callback is set by WorkflowService/WorkflowExecutor to start a
    WorkflowExecution.
"""

from __future__ import annotations

import fnmatch
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from nobla.automation.workflows.models import (
    WorkflowTrigger,
    evaluate_conditions,
)

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus
    from nobla.events.models import NoblaEvent

logger = logging.getLogger(__name__)

# Type for the callback that fires when a trigger matches
TriggerCallback = Callable[[str, WorkflowTrigger, "NoblaEvent"], Awaitable[None]]


class TriggerMatcher:
    """Matches incoming events against registered workflow triggers.

    Args:
        event_bus: NoblaEventBus to subscribe to.
        dedup_window_seconds: Ignore duplicate (trigger_id, correlation_id)
            pairs within this time window.
        event_prefix: Event bus subscription pattern (default ``*``).
    """

    def __init__(
        self,
        event_bus: NoblaEventBus,
        dedup_window_seconds: float = 5.0,
        event_prefix: str = "*",
    ) -> None:
        self._event_bus = event_bus
        self._dedup_window = dedup_window_seconds
        self._event_prefix = event_prefix
        self._subscription_id: str | None = None

        # trigger_id → WorkflowTrigger
        self._triggers: dict[str, WorkflowTrigger] = {}
        # trigger_id → workflow_id mapping
        self._trigger_workflows: dict[str, str] = {}

        # Dedup: (trigger_id, correlation_id) → timestamp
        self._recent: dict[tuple[str, str], float] = {}

        # Callback for matched triggers
        self._callback: TriggerCallback | None = None

        # Stats
        self.events_received: int = 0
        self.events_matched: int = 0
        self.events_deduplicated: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to the event bus."""
        self._subscription_id = await self._event_bus.subscribe(
            self._event_prefix, self._on_event
        )
        logger.info("trigger_matcher_started prefix=%s", self._event_prefix)

    async def stop(self) -> None:
        """Unsubscribe from the event bus."""
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        logger.info("trigger_matcher_stopped")

    # ------------------------------------------------------------------
    # Trigger registration
    # ------------------------------------------------------------------

    def register_trigger(self, workflow_id: str, trigger: WorkflowTrigger) -> None:
        """Register a trigger for matching.

        Args:
            workflow_id: The workflow this trigger belongs to.
            trigger: The trigger definition.
        """
        self._triggers[trigger.trigger_id] = trigger
        self._trigger_workflows[trigger.trigger_id] = workflow_id
        logger.debug(
            "trigger_registered id=%s workflow=%s pattern=%s",
            trigger.trigger_id, workflow_id, trigger.event_pattern,
        )

    def unregister_trigger(self, trigger_id: str) -> None:
        """Remove a trigger from matching."""
        self._triggers.pop(trigger_id, None)
        self._trigger_workflows.pop(trigger_id, None)

    def register_workflow_triggers(
        self, workflow_id: str, triggers: list[WorkflowTrigger]
    ) -> None:
        """Register all triggers for a workflow (convenience)."""
        for t in triggers:
            self.register_trigger(workflow_id, t)

    def unregister_workflow(self, workflow_id: str) -> None:
        """Remove all triggers for a workflow."""
        to_remove = [
            tid for tid, wid in self._trigger_workflows.items()
            if wid == workflow_id
        ]
        for tid in to_remove:
            self.unregister_trigger(tid)

    def set_callback(self, callback: TriggerCallback) -> None:
        """Set the callback invoked when a trigger matches."""
        self._callback = callback

    def list_triggers(self) -> list[tuple[str, WorkflowTrigger]]:
        """Return all registered (workflow_id, trigger) pairs."""
        return [
            (self._trigger_workflows[tid], t)
            for tid, t in self._triggers.items()
        ]

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _on_event(self, event: NoblaEvent) -> None:
        """Handle an incoming event — match against all triggers."""
        self.events_received += 1
        self._cleanup_dedup()

        for trigger_id, trigger in self._triggers.items():
            if not trigger.active:
                continue

            # 1. Pattern match
            if not fnmatch.fnmatch(event.event_type, trigger.event_pattern):
                continue

            # 2. Evaluate conditions
            context = self._build_context(event)
            if not evaluate_conditions(trigger.conditions, context):
                continue

            # 3. Dedup check
            dedup_key = (trigger_id, event.correlation_id)
            if self._is_duplicate(dedup_key):
                self.events_deduplicated += 1
                logger.debug(
                    "trigger_deduplicated trigger=%s correlation=%s",
                    trigger_id, event.correlation_id,
                )
                continue

            # 4. Record and fire
            self._recent[dedup_key] = time.monotonic()
            self.events_matched += 1

            workflow_id = self._trigger_workflows.get(trigger_id, "")
            logger.info(
                "trigger_matched trigger=%s workflow=%s event=%s",
                trigger_id, workflow_id, event.event_type,
            )

            if self._callback:
                try:
                    await self._callback(workflow_id, trigger, event)
                except Exception:
                    logger.exception(
                        "trigger_callback_failed trigger=%s workflow=%s",
                        trigger_id, workflow_id,
                    )

    @staticmethod
    def _build_context(event: NoblaEvent) -> dict[str, Any]:
        """Build evaluation context from an event."""
        return {
            "event_type": event.event_type,
            "source": event.source,
            "user_id": event.user_id,
            "correlation_id": event.correlation_id,
            "payload": event.payload,
            **event.payload,  # Flatten payload for convenience
        }

    def _is_duplicate(self, key: tuple[str, str]) -> bool:
        """Check if this (trigger_id, correlation_id) was seen recently."""
        if key not in self._recent:
            return False
        elapsed = time.monotonic() - self._recent[key]
        return elapsed < self._dedup_window

    def _cleanup_dedup(self) -> None:
        """Remove expired entries from the dedup cache."""
        now = time.monotonic()
        expired = [
            k for k, ts in self._recent.items()
            if now - ts >= self._dedup_window
        ]
        for k in expired:
            del self._recent[k]
