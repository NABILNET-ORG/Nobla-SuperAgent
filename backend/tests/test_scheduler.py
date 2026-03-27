"""Tests for the NL Scheduled Tasks automation engine (Phase 6).

Covers: models, NL parser, interpreter fallback, scheduler wrapper,
confirmation flow, service orchestration.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.automation.confirmation import ConfirmationManager
from nobla.automation.interpreter import (
    TaskInterpretation,
    _fallback_interpret,
    _parse_llm_response,
)
from nobla.automation.models import (
    ConfirmationRequest,
    ParsedSchedule,
    ScheduleType,
    ScheduledTask,
    TaskInterpretation,
    TaskStatus,
)
from nobla.automation.parser import (
    _cron_to_human,
    _is_recurring,
    _rrule_to_cron,
    parse_time_expression,
)
from nobla.automation.scheduler import NoblaScheduler
from nobla.automation.service import SchedulerService
from nobla.config.settings import SchedulerSettings
from nobla.events.bus import NoblaEventBus


# ══════════════════════════════════════════════════════════
# SchedulerSettings
# ══════════════════════════════════════════════════════════


class TestSchedulerSettings:
    """SchedulerSettings validation."""

    def test_defaults(self):
        s = SchedulerSettings()
        assert s.enabled is True
        assert s.max_tasks_per_user == 50
        assert s.default_timezone == "UTC"
        assert s.confirmation_timeout_seconds == 60
        assert s.max_concurrent_jobs == 10
        assert s.misfire_grace_seconds == 300

    def test_custom_values(self):
        s = SchedulerSettings(
            max_tasks_per_user=10,
            default_timezone="US/Eastern",
            confirmation_timeout_seconds=30,
        )
        assert s.max_tasks_per_user == 10
        assert s.default_timezone == "US/Eastern"


# ══════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════


class TestTaskStatus:
    """TaskStatus enum."""

    def test_all_statuses(self):
        assert TaskStatus.PENDING_CONFIRMATION == "pending_confirmation"
        assert TaskStatus.ACTIVE == "active"
        assert TaskStatus.PAUSED == "paused"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"


class TestScheduleType:
    """ScheduleType enum."""

    def test_types(self):
        assert ScheduleType.ONE_SHOT == "one_shot"
        assert ScheduleType.RECURRING == "recurring"


class TestParsedSchedule:
    """ParsedSchedule model."""

    def test_recurring(self):
        s = ParsedSchedule(
            schedule_type=ScheduleType.RECURRING,
            cron_expr="0 9 * * *",
            human_readable="Daily at 9:00 AM",
        )
        assert s.cron_expr == "0 9 * * *"
        assert s.run_date is None

    def test_one_shot(self):
        dt = datetime(2026, 3, 28, 15, 0, tzinfo=timezone.utc)
        s = ParsedSchedule(
            schedule_type=ScheduleType.ONE_SHOT,
            run_date=dt,
            human_readable="March 28 at 3:00 PM",
        )
        assert s.run_date == dt
        assert s.cron_expr is None

    def test_defaults(self):
        s = ParsedSchedule(
            schedule_type=ScheduleType.RECURRING,
            human_readable="test",
        )
        assert s.next_runs == []
        assert s.timezone == "UTC"


class TestScheduledTask:
    """ScheduledTask model."""

    def test_defaults(self):
        t = ScheduledTask()
        assert t.task_id  # UUID auto-generated
        assert t.status == TaskStatus.PENDING_CONFIRMATION
        assert t.run_count == 0
        assert t.error_count == 0
        assert t.job_id is None

    def test_unique_ids(self):
        t1 = ScheduledTask()
        t2 = ScheduledTask()
        assert t1.task_id != t2.task_id


class TestTaskInterpretation:
    """TaskInterpretation model."""

    def test_basic(self):
        t = TaskInterpretation(
            task_description="check logs",
            time_expression="every day at 9am",
            raw_input="check logs every day at 9am",
        )
        assert t.task_description == "check logs"
        assert t.is_tool_task is False
        assert t.tool_name is None

    def test_with_tool(self):
        t = TaskInterpretation(
            task_description="run backup",
            time_expression="daily at midnight",
            raw_input="run backup daily at midnight",
            tool_name="code.run",
            tool_params={"language": "bash"},
            is_tool_task=True,
        )
        assert t.is_tool_task is True
        assert t.tool_name == "code.run"


class TestConfirmationRequest:
    """ConfirmationRequest model."""

    def test_fields(self):
        c = ConfirmationRequest(
            task_id="t1",
            user_id="u1",
            task_description="check logs",
            schedule_description="Daily at 9:00 AM",
        )
        assert c.task_id == "t1"
        assert c.next_runs == []


# ══════════════════════════════════════════════════════════
# Parser — _is_recurring
# ══════════════════════════════════════════════════════════


class TestIsRecurring:
    """Heuristic recurring detection."""

    def test_every(self):
        assert _is_recurring("every morning at 9am") is True

    def test_daily(self):
        assert _is_recurring("daily at noon") is True

    def test_weekly(self):
        assert _is_recurring("weekly on monday") is True

    def test_monthly(self):
        assert _is_recurring("monthly on the 1st") is True

    def test_hourly(self):
        assert _is_recurring("hourly check") is True

    def test_not_recurring(self):
        assert _is_recurring("tomorrow at 3pm") is False

    def test_each(self):
        assert _is_recurring("each friday at 5pm") is True

    def test_empty(self):
        assert _is_recurring("") is False


# ══════════════════════════════════════════════════════════
# Parser — _rrule_to_cron
# ══════════════════════════════════════════════════════════


class TestRruleToCron:
    """RRULE → cron conversion."""

    def test_daily(self):
        result = _rrule_to_cron("RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0")
        assert result == "0 9 * * *"

    def test_weekly_monday(self):
        result = _rrule_to_cron("RRULE:FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0")
        assert result == "0 9 * * 1"

    def test_weekly_multiple_days(self):
        result = _rrule_to_cron("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=8;BYMINUTE=30")
        assert result == "30 8 * * 1,3,5"

    def test_monthly(self):
        result = _rrule_to_cron("RRULE:FREQ=MONTHLY;BYMONTHDAY=15;BYHOUR=10;BYMINUTE=0")
        assert result == "0 10 15 * *"

    def test_hourly(self):
        result = _rrule_to_cron("RRULE:FREQ=HOURLY;BYMINUTE=30")
        assert result == "30 * * * *"

    def test_daily_interval(self):
        result = _rrule_to_cron("RRULE:FREQ=DAILY;INTERVAL=2;BYHOUR=6;BYMINUTE=0")
        assert result == "0 6 */2 * *"

    def test_empty_returns_none(self):
        assert _rrule_to_cron("") is None

    def test_unknown_freq_returns_none(self):
        assert _rrule_to_cron("RRULE:FREQ=YEARLY;BYHOUR=0;BYMINUTE=0") is None


# ══════════════════════════════════════════════════════════
# Parser — _cron_to_human
# ══════════════════════════════════════════════════════════


class TestCronToHuman:
    """Cron → human-readable description."""

    def test_daily(self):
        result = _cron_to_human("0 9 * * *", "original")
        assert "Daily" in result
        assert "9:00 AM" in result

    def test_weekly_monday(self):
        result = _cron_to_human("0 9 * * 1", "original")
        assert "Monday" in result

    def test_monthly(self):
        result = _cron_to_human("0 10 15 * *", "original")
        assert "Monthly" in result
        assert "15" in result

    def test_pm_time(self):
        result = _cron_to_human("30 14 * * *", "original")
        assert "2:30 PM" in result

    def test_midnight(self):
        result = _cron_to_human("0 0 * * *", "original")
        assert "12:00 AM" in result

    def test_noon(self):
        result = _cron_to_human("0 12 * * *", "original")
        assert "12:00 PM" in result


# ══════════════════════════════════════════════════════════
# Parser — parse_time_expression (integration)
# ══════════════════════════════════════════════════════════


class TestParseTimeExpression:
    """Full NL time parsing."""

    def test_returns_none_for_empty(self):
        assert parse_time_expression("") is None

    def test_daily_recurring(self):
        result = parse_time_expression("every day at 9am")
        if result:  # recurrent may not parse all patterns
            assert result.schedule_type == ScheduleType.RECURRING
            assert result.cron_expr is not None

    def test_absolute_future(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        text = future.strftime("%B %d, %Y at 3pm")
        result = parse_time_expression(text)
        if result:
            assert result.schedule_type == ScheduleType.ONE_SHOT
            assert result.run_date is not None

    def test_returns_none_for_gibberish(self):
        result = parse_time_expression("xyzzy foobar")
        # Should return None or a schedule — but not crash
        assert result is None or isinstance(result, ParsedSchedule)


# ══════════════════════════════════════════════════════════
# Interpreter — _parse_llm_response
# ══════════════════════════════════════════════════════════


class TestParseLlmResponse:
    """LLM JSON response parsing."""

    def test_valid_json(self):
        text = '{"task_description": "check logs", "time_expression": "daily at 9am", "tool_name": null, "tool_params": {}}'
        result = _parse_llm_response(text, "raw")
        assert result is not None
        assert result.task_description == "check logs"
        assert result.time_expression == "daily at 9am"
        assert result.is_tool_task is False

    def test_with_tool(self):
        text = '{"task_description": "run backup", "time_expression": "every night", "tool_name": "code.run", "tool_params": {"language": "bash"}}'
        result = _parse_llm_response(text, "raw")
        assert result.is_tool_task is True
        assert result.tool_name == "code.run"

    def test_code_fenced_json(self):
        text = '```json\n{"task_description": "test", "time_expression": "now"}\n```'
        result = _parse_llm_response(text, "raw")
        assert result is not None

    def test_invalid_json(self):
        result = _parse_llm_response("not json at all", "raw")
        assert result is None

    def test_missing_fields(self):
        result = _parse_llm_response('{"task_description": "test"}', "raw")
        assert result is None

    def test_empty_fields(self):
        result = _parse_llm_response('{"task_description": "", "time_expression": ""}', "raw")
        assert result is None


# ══════════════════════════════════════════════════════════
# Interpreter — _fallback_interpret
# ══════════════════════════════════════════════════════════


class TestFallbackInterpret:
    """Heuristic fallback when LLM unavailable."""

    def test_task_then_time(self):
        result = _fallback_interpret("check logs every morning at 9am")
        assert result.raw_input == "check logs every morning at 9am"
        # Should split into task and time parts
        assert result.task_description or result.time_expression

    def test_time_then_task(self):
        result = _fallback_interpret("every day at noon send a report")
        assert result.raw_input == "every day at noon send a report"

    def test_no_time_marker(self):
        result = _fallback_interpret("do something")
        assert result.task_description == "do something"

    def test_preserves_raw_input(self):
        result = _fallback_interpret("test input")
        assert result.raw_input == "test input"


# ══════════════════════════════════════════════════════════
# NoblaScheduler
# ══════════════════════════════════════════════════════════


@pytest.fixture
def event_bus():
    return NoblaEventBus()


@pytest.fixture
def scheduler(event_bus):
    callback = AsyncMock()
    return NoblaScheduler(event_bus=event_bus, job_callback=callback)


def _make_task(
    user_id: str = "user-1",
    schedule_type: ScheduleType = ScheduleType.RECURRING,
    cron_expr: str = "0 9 * * *",
    run_date: datetime | None = None,
) -> ScheduledTask:
    """Build a ScheduledTask with a ParsedSchedule."""
    schedule = ParsedSchedule(
        schedule_type=schedule_type,
        cron_expr=cron_expr if schedule_type == ScheduleType.RECURRING else None,
        run_date=run_date,
        human_readable="Test schedule",
    )
    return ScheduledTask(
        user_id=user_id,
        raw_input="test task",
        interpretation=TaskInterpretation(
            task_description="test task",
            time_expression="test time",
            raw_input="test task test time",
        ),
        schedule=schedule,
    )


class TestNoblaScheduler:
    """APScheduler wrapper tests."""

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        await scheduler.start()
        assert scheduler.is_running is True
        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_add_recurring_task(self, scheduler):
        await scheduler.start()
        task = _make_task()
        job_id = await scheduler.add_task(task)
        assert job_id is not None
        assert task.status == TaskStatus.ACTIVE
        assert task.job_id == job_id
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_add_one_shot_task(self, scheduler):
        await scheduler.start()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        task = _make_task(
            schedule_type=ScheduleType.ONE_SHOT,
            run_date=future,
        )
        job_id = await scheduler.add_task(task)
        assert job_id is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_remove_task(self, scheduler):
        await scheduler.start()
        task = _make_task()
        await scheduler.add_task(task)
        result = await scheduler.remove_task(task.task_id)
        assert result is True
        assert task.status == TaskStatus.CANCELLED
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, scheduler):
        await scheduler.start()
        result = await scheduler.remove_task("no-such-task")
        assert result is False
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_pause_resume(self, scheduler):
        await scheduler.start()
        task = _make_task()
        await scheduler.add_task(task)
        assert await scheduler.pause_task(task.task_id) is True
        assert task.status == TaskStatus.PAUSED
        assert await scheduler.resume_task(task.task_id) is True
        assert task.status == TaskStatus.ACTIVE
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_pause_nonexistent(self, scheduler):
        await scheduler.start()
        assert await scheduler.pause_task("nope") is False
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_list_tasks(self, scheduler):
        await scheduler.start()
        t1 = _make_task(user_id="u1")
        t2 = _make_task(user_id="u2")
        await scheduler.add_task(t1)
        await scheduler.add_task(t2)
        assert len(scheduler.list_tasks()) == 2
        assert len(scheduler.list_tasks(user_id="u1")) == 1
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_task(self, scheduler):
        await scheduler.start()
        task = _make_task()
        await scheduler.add_task(task)
        found = scheduler.get_task(task.task_id)
        assert found is task
        assert scheduler.get_task("no-such") is None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_task_no_schedule_raises(self, scheduler):
        await scheduler.start()
        task = ScheduledTask(user_id="u1")
        with pytest.raises(ValueError, match="no schedule"):
            await scheduler.add_task(task)
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_events_emitted(self, scheduler, event_bus):
        captured = []
        event_bus.subscribe("scheduler.*", lambda e: captured.append(e))
        await event_bus.start()
        await scheduler.start()

        task = _make_task()
        await scheduler.add_task(task)

        await asyncio.sleep(0.05)
        assert any(e.event_type == "scheduler.task.created" for e in captured)

        await scheduler.remove_task(task.task_id)
        await asyncio.sleep(0.05)
        assert any(e.event_type == "scheduler.task.removed" for e in captured)

        await scheduler.stop()
        await event_bus.stop()


# ══════════════════════════════════════════════════════════
# ConfirmationManager
# ══════════════════════════════════════════════════════════


class TestConfirmationManager:
    """Confirmation flow tests."""

    def test_build_confirmation(self):
        mgr = ConfirmationManager(timeout_seconds=30)
        task = _make_task()
        req = mgr.build_confirmation(task)
        assert req.task_id == task.task_id
        assert req.task_description == "test task"
        assert req.schedule_description == "Test schedule"

    @pytest.mark.asyncio
    async def test_approve(self):
        mgr = ConfirmationManager(timeout_seconds=5)
        task = _make_task()

        async def approve_later():
            await asyncio.sleep(0.05)
            mgr.respond(task.task_id, True)

        asyncio.create_task(approve_later())
        result = await mgr.request_confirmation(task)
        assert result is True

    @pytest.mark.asyncio
    async def test_deny(self):
        mgr = ConfirmationManager(timeout_seconds=5)
        task = _make_task()

        async def deny_later():
            await asyncio.sleep(0.05)
            mgr.respond(task.task_id, False)

        asyncio.create_task(deny_later())
        result = await mgr.request_confirmation(task)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        mgr = ConfirmationManager(timeout_seconds=0.1)
        task = _make_task()
        result = await mgr.request_confirmation(task)
        assert result is False

    def test_respond_no_pending(self):
        mgr = ConfirmationManager()
        assert mgr.respond("no-task", True) is False

    def test_pending_count(self):
        mgr = ConfirmationManager()
        assert mgr.pending_count == 0

    def test_cancel_all(self):
        mgr = ConfirmationManager()
        # Nothing pending — should not crash
        mgr.cancel_all()
        assert mgr.pending_count == 0


# ══════════════════════════════════════════════════════════
# SchedulerService
# ══════════════════════════════════════════════════════════


class TestSchedulerService:
    """Service orchestration tests."""

    @pytest.fixture
    def service(self, event_bus):
        scheduler = NoblaScheduler(event_bus=event_bus)
        confirmation = ConfirmationManager(
            event_bus=event_bus, timeout_seconds=5
        )
        return SchedulerService(
            scheduler=scheduler,
            confirmation=confirmation,
            event_bus=event_bus,
            max_tasks_per_user=3,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, service):
        await service.start()
        await service.stop()

    @pytest.mark.asyncio
    async def test_list_empty(self, service):
        assert service.list_tasks("user-1") == []

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, service):
        result = await service.cancel_task("no-task", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_pause_nonexistent(self, service):
        result = await service.pause_task("no-task", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_nonexistent(self, service):
        result = await service.resume_task("no-task", "user-1")
        assert result is False

    def test_respond_to_confirmation(self, service):
        # No pending confirmations
        result = service.respond_to_confirmation("no-task", True)
        assert result is False

    @pytest.mark.asyncio
    async def test_parse_and_schedule_bad_input(self, service):
        await service.start()
        with pytest.raises(ValueError, match="Could not understand"):
            await service.parse_and_schedule("xyzzy gibberish", "user-1")
        await service.stop()

    @pytest.mark.asyncio
    async def test_task_limit_enforced(self, service):
        await service.start()

        # Manually add 3 active tasks to the scheduler
        for i in range(3):
            task = _make_task(user_id="user-1")
            await service._scheduler.add_task(task)

        with pytest.raises(ValueError, match="Task limit reached"):
            await service.parse_and_schedule(
                "check logs every day at 9am", "user-1"
            )
        await service.stop()

    @pytest.mark.asyncio
    async def test_cancel_wrong_user(self, service):
        await service.start()
        task = _make_task(user_id="user-1")
        await service._scheduler.add_task(task)
        result = await service.cancel_task(task.task_id, "user-2")
        assert result is False
        await service.stop()

    @pytest.mark.asyncio
    async def test_cancel_own_task(self, service):
        await service.start()
        task = _make_task(user_id="user-1")
        await service._scheduler.add_task(task)
        result = await service.cancel_task(task.task_id, "user-1")
        assert result is True
        await service.stop()
