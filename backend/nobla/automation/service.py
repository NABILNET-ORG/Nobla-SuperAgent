"""Scheduler service — orchestrates parse, interpret, confirm, schedule (Phase 6).

High-level entry point for the NL Scheduled Tasks feature. Ties the
NL parser, LLM interpreter, confirmation manager, and APScheduler
wrapper into a single cohesive API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nobla.automation.confirmation import ConfirmationManager
from nobla.automation.interpreter import interpret_task
from nobla.automation.models import (
    ScheduledTask,
    TaskInterpretation,
    TaskStatus,
)
from nobla.automation.parser import parse_time_expression
from nobla.automation.scheduler import NoblaScheduler

if TYPE_CHECKING:
    from nobla.brain.router import LLMRouter
    from nobla.events.bus import NoblaEventBus
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class SchedulerService:
    """Orchestrates the full NL scheduling pipeline.

    Pipeline: user_input → interpret (LLM) → parse time (NLP)
              → confirm (user) → schedule (APScheduler).

    Args:
        scheduler: APScheduler wrapper for job management.
        confirmation: Confirmation manager for user approval.
        router: LLM router for task interpretation.
        tool_registry: Tool registry for mapping tasks to tools.
        event_bus: Event bus for notifications.
        default_timezone: Default timezone for schedules.
        max_tasks_per_user: Maximum tasks a user can have.
    """

    def __init__(
        self,
        scheduler: NoblaScheduler,
        confirmation: ConfirmationManager,
        router: LLMRouter | None = None,
        tool_registry: ToolRegistry | None = None,
        event_bus: NoblaEventBus | None = None,
        default_timezone: str = "UTC",
        max_tasks_per_user: int = 50,
    ) -> None:
        self._scheduler = scheduler
        self._confirmation = confirmation
        self._router = router
        self._tool_registry = tool_registry
        self._event_bus = event_bus
        self._default_tz = default_timezone
        self._max_tasks = max_tasks_per_user

    async def start(self) -> None:
        """Start the scheduler."""
        await self._scheduler.start()

    async def stop(self) -> None:
        """Stop the scheduler and cancel pending confirmations."""
        self._confirmation.cancel_all()
        await self._scheduler.stop()

    # ── Main pipeline ─────────────────────────────────────

    async def parse_and_schedule(
        self,
        user_input: str,
        user_id: str,
    ) -> ScheduledTask:
        """Full pipeline: interpret → parse → confirm → schedule.

        Returns the ScheduledTask with its final status:
        - ACTIVE if confirmed and scheduled.
        - CANCELLED if user denied or confirmation timed out.
        - PENDING_CONFIRMATION should not be returned (transient state).

        Raises:
            ValueError: If input cannot be parsed or user limit reached.
        """
        # Check user task limit
        user_tasks = self._scheduler.list_tasks(user_id=user_id)
        active = [
            t for t in user_tasks
            if t.status in (TaskStatus.ACTIVE, TaskStatus.PAUSED)
        ]
        if len(active) >= self._max_tasks:
            raise ValueError(
                f"Task limit reached ({self._max_tasks}). "
                f"Cancel existing tasks before creating new ones."
            )

        # Step 1: Interpret the task with LLM
        interpretation = await self._interpret(user_input)

        # Step 2: Parse the time expression
        schedule = parse_time_expression(
            interpretation.time_expression,
            default_timezone=self._default_tz,
        )
        if not schedule:
            raise ValueError(
                f"Could not understand the schedule: "
                f"'{interpretation.time_expression}'. "
                f"Try something like 'every day at 9am' or 'tomorrow at 3pm'."
            )

        # Step 3: Build the task
        task = ScheduledTask(
            user_id=user_id,
            raw_input=user_input,
            interpretation=interpretation,
            schedule=schedule,
            status=TaskStatus.PENDING_CONFIRMATION,
        )

        # Step 4: Request confirmation
        approved = await self._confirmation.request_confirmation(task)

        if not approved:
            task.status = TaskStatus.CANCELLED
            logger.info("Task %s cancelled by user", task.task_id)
            return task

        # Step 5: Schedule the task
        await self._scheduler.add_task(task)
        logger.info("Task %s scheduled: %s", task.task_id, schedule.human_readable)
        return task

    # ── Task management ───────────────────────────────────

    def list_tasks(self, user_id: str) -> list[ScheduledTask]:
        """List all tasks for a user."""
        return self._scheduler.list_tasks(user_id=user_id)

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a task. Returns False if not found or not owned."""
        task = self._scheduler.get_task(task_id)
        if not task or task.user_id != user_id:
            return False
        return await self._scheduler.remove_task(task_id)

    async def pause_task(self, task_id: str, user_id: str) -> bool:
        """Pause a task. Returns False if not found or not owned."""
        task = self._scheduler.get_task(task_id)
        if not task or task.user_id != user_id:
            return False
        return await self._scheduler.pause_task(task_id)

    async def resume_task(self, task_id: str, user_id: str) -> bool:
        """Resume a paused task. Returns False if not found or not owned."""
        task = self._scheduler.get_task(task_id)
        if not task or task.user_id != user_id:
            return False
        return await self._scheduler.resume_task(task_id)

    def respond_to_confirmation(
        self, task_id: str, approved: bool
    ) -> bool:
        """Deliver a user's confirmation response."""
        return self._confirmation.respond(task_id, approved)

    # ── Private ───────────────────────────────────────────

    async def _interpret(self, user_input: str) -> TaskInterpretation:
        """Interpret user input via LLM with fallback."""
        if self._router:
            return await interpret_task(
                user_input, self._router, self._tool_registry
            )
        # No router available — use fallback directly
        from nobla.automation.interpreter import _fallback_interpret

        return _fallback_interpret(user_input)
