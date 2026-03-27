"""APScheduler wrapper — job lifecycle management (Phase 6).

Wraps ``AsyncIOScheduler`` to manage scheduled task execution.
Routes job callbacks through the tool executor or LLM router and
emits events on the event bus for observability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from nobla.automation.models import (
    ParsedSchedule,
    ScheduleType,
    ScheduledTask,
    TaskStatus,
)
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)


class NoblaScheduler:
    """Manages APScheduler jobs and maps them to ScheduledTask lifecycle.

    Args:
        event_bus: Event bus for emitting scheduler events.
        job_callback: Async function called when a job fires.
            Signature: ``async def callback(task: ScheduledTask) -> None``
        timezone: Default timezone for job scheduling.
        misfire_grace_seconds: Grace period for missed job fires.
    """

    def __init__(
        self,
        event_bus: NoblaEventBus | None = None,
        job_callback: Callable[[ScheduledTask], Awaitable[None]] | None = None,
        timezone: str = "UTC",
        misfire_grace_seconds: int = 300,
    ) -> None:
        self._event_bus = event_bus
        self._job_callback = job_callback
        self._timezone = timezone
        self._scheduler = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": misfire_grace_seconds,
            },
        )
        # {task_id: ScheduledTask}
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    async def start(self) -> None:
        """Start the APScheduler background loop."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started (timezone=%s)", self._timezone)

    async def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Task management ───────────────────────────────────

    async def add_task(self, task: ScheduledTask) -> str:
        """Register a scheduled task and create the APScheduler job.

        Returns the APScheduler job ID.
        """
        if not task.schedule:
            raise ValueError("Task has no schedule")

        schedule = task.schedule

        if schedule.schedule_type == ScheduleType.RECURRING:
            if not schedule.cron_expr:
                raise ValueError("Recurring task has no cron expression")
            trigger = CronTrigger.from_crontab(
                schedule.cron_expr, timezone=schedule.timezone
            )
        elif schedule.schedule_type == ScheduleType.ONE_SHOT:
            if not schedule.run_date:
                raise ValueError("One-shot task has no run_date")
            trigger = DateTrigger(
                run_date=schedule.run_date, timezone=schedule.timezone
            )
        else:
            raise ValueError(f"Unknown schedule type: {schedule.schedule_type}")

        job = self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=task.task_id,
            args=[task.task_id],
            name=task.interpretation.task_description
            if task.interpretation
            else task.raw_input,
        )

        task.job_id = job.id
        task.status = TaskStatus.ACTIVE
        self._tasks[task.task_id] = task

        await self._emit_event(
            "scheduler.task.created",
            {
                "task_id": task.task_id,
                "description": task.interpretation.task_description
                if task.interpretation
                else task.raw_input,
                "schedule": schedule.human_readable,
            },
            user_id=task.user_id,
        )

        logger.info(
            "Scheduled task %s: %s (%s)",
            task.task_id,
            task.raw_input,
            schedule.human_readable,
        )
        return job.id

    async def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task and its APScheduler job."""
        task = self._tasks.pop(task_id, None)
        if not task:
            return False

        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass  # Job may already have been removed (one-shot completed)

        task.status = TaskStatus.CANCELLED

        await self._emit_event(
            "scheduler.task.removed",
            {"task_id": task_id},
            user_id=task.user_id,
        )

        return True

    async def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.ACTIVE:
            return False

        try:
            self._scheduler.pause_job(task_id)
        except Exception:
            return False

        task.status = TaskStatus.PAUSED
        await self._emit_event(
            "scheduler.task.paused",
            {"task_id": task_id},
            user_id=task.user_id,
        )
        return True

    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return False

        try:
            self._scheduler.resume_job(task_id)
        except Exception:
            return False

        task.status = TaskStatus.ACTIVE
        await self._emit_event(
            "scheduler.task.resumed",
            {"task_id": task_id},
            user_id=task.user_id,
        )
        return True

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Look up a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, user_id: str | None = None) -> list[ScheduledTask]:
        """List tasks, optionally filtered by user."""
        tasks = list(self._tasks.values())
        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]
        return tasks

    # ── Job execution ─────────────────────────────────────

    async def _execute_job(self, task_id: str) -> None:
        """APScheduler job callback — executes the task."""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("Job fired for unknown task %s", task_id)
            return

        logger.info("Executing scheduled task %s", task_id)
        task.last_run_at = datetime.now(timezone.utc)
        task.run_count += 1

        try:
            if self._job_callback:
                await self._job_callback(task)

            await self._emit_event(
                "scheduler.task.executed",
                {
                    "task_id": task_id,
                    "run_count": task.run_count,
                    "description": task.interpretation.task_description
                    if task.interpretation
                    else task.raw_input,
                },
                user_id=task.user_id,
            )

            # One-shot tasks complete after execution
            if (
                task.schedule
                and task.schedule.schedule_type == ScheduleType.ONE_SHOT
            ):
                task.status = TaskStatus.COMPLETED
                self._tasks.pop(task_id, None)

        except Exception as exc:
            task.error_count += 1
            task.last_error = str(exc)
            logger.exception("Scheduled task %s failed", task_id)

            await self._emit_event(
                "scheduler.task.failed",
                {
                    "task_id": task_id,
                    "error": str(exc),
                    "error_count": task.error_count,
                },
                user_id=task.user_id,
            )

    # ── Events ────────────────────────────────────────────

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        if not self._event_bus:
            return
        event = NoblaEvent(
            event_type=event_type,
            source="scheduler",
            payload=payload,
            user_id=user_id,
        )
        await self._event_bus.emit(event)
