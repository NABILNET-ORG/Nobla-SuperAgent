"""Automation data models — scheduled tasks, parsed schedules (Phase 6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Lifecycle status of a scheduled task."""

    PENDING_CONFIRMATION = "pending_confirmation"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"  # One-shot tasks after execution
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduleType(str, Enum):
    """Type of schedule trigger."""

    ONE_SHOT = "one_shot"  # Run once at a specific time
    RECURRING = "recurring"  # Cron-based recurring schedule


@dataclass(slots=True)
class ParsedSchedule:
    """Result of NL time parsing.

    Attributes:
        schedule_type: One-shot or recurring.
        cron_expr: Cron expression for APScheduler (recurring only).
        run_date: Specific datetime for one-shot tasks.
        human_readable: User-friendly description, e.g. "Daily at 9:00 AM".
        next_runs: Preview of upcoming execution times.
        timezone: Timezone for the schedule.
    """

    schedule_type: ScheduleType
    human_readable: str
    cron_expr: str | None = None
    run_date: datetime | None = None
    next_runs: list[datetime] = field(default_factory=list)
    timezone: str = "UTC"


@dataclass(slots=True)
class TaskInterpretation:
    """Result of LLM task interpretation.

    Attributes:
        task_description: What the user wants done, cleaned up.
        time_expression: The time/schedule part extracted from input.
        tool_name: Matched Nobla tool name if applicable (e.g. "code.run").
        tool_params: Parameters for the tool, if detected.
        is_tool_task: Whether this maps to an existing tool.
        raw_input: Original user input.
    """

    task_description: str
    time_expression: str
    raw_input: str
    tool_name: str | None = None
    tool_params: dict[str, Any] = field(default_factory=dict)
    is_tool_task: bool = False


@dataclass(slots=True)
class ScheduledTask:
    """A user's scheduled task — stored in memory, executed by APScheduler.

    Attributes:
        task_id: Unique identifier.
        user_id: Nobla user who created this task.
        raw_input: Original natural language input.
        interpretation: LLM-parsed task details.
        schedule: Parsed schedule details.
        status: Current lifecycle status.
        job_id: APScheduler job ID (set after confirmation).
        created_at: When the task was created.
        last_run_at: When the task last executed.
        run_count: How many times the task has run.
        error_count: How many times execution failed.
        last_error: Most recent error message.
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    raw_input: str = ""
    interpretation: TaskInterpretation | None = None
    schedule: ParsedSchedule | None = None
    status: TaskStatus = TaskStatus.PENDING_CONFIRMATION
    job_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_run_at: datetime | None = None
    run_count: int = 0
    error_count: int = 0
    last_error: str | None = None


@dataclass(slots=True)
class ConfirmationRequest:
    """Confirmation prompt shown to user before scheduling.

    Attributes:
        task_id: Which task this confirms.
        user_id: Who must confirm.
        task_description: What will be done.
        schedule_description: When it will run.
        next_runs: Preview of next 3 execution times.
        expires_at: When this confirmation expires.
    """

    task_id: str
    user_id: str
    task_description: str
    schedule_description: str
    next_runs: list[datetime] = field(default_factory=list)
    expires_at: datetime | None = None
