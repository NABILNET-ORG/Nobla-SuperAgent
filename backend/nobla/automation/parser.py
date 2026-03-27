"""NL time parser — extracts schedule from natural language (Phase 6).

Uses ``dateparser`` for absolute times ("March 28 at 3pm") and
``recurrent`` for recurring patterns ("every Monday at 9am").
Returns a ``ParsedSchedule`` with cron expression and human-readable text.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import dateparser
import recurrent
from recurrent import RecurringEvent

from nobla.automation.models import ParsedSchedule, ScheduleType

logger = logging.getLogger(__name__)

# Common NL patterns that signal recurring schedules
_RECURRING_KEYWORDS = (
    "every", "daily", "weekly", "monthly", "hourly",
    "each", "twice", "biweekly", "fortnightly",
)


def _is_recurring(text: str) -> bool:
    """Heuristic: does the text describe a recurring schedule?"""
    lower = text.lower().strip()
    return any(lower.startswith(kw) or f" {kw} " in f" {lower} " for kw in _RECURRING_KEYWORDS)


def _rrule_to_cron(rrule_str: str) -> str | None:
    """Convert an RFC 5545 RRULE to a cron expression (best-effort).

    Handles common cases: DAILY, WEEKLY (with BYDAY), MONTHLY, HOURLY.
    Falls back to None for unsupported patterns.
    """
    if not rrule_str:
        return None

    parts: dict[str, str] = {}
    for segment in rrule_str.replace("RRULE:", "").split(";"):
        if "=" in segment:
            key, val = segment.split("=", 1)
            parts[key.strip()] = val.strip()

    freq = parts.get("FREQ", "").upper()
    byhour = parts.get("BYHOUR", "0")
    byminute = parts.get("BYMINUTE", "0")
    byday = parts.get("BYDAY", "")
    bymonthday = parts.get("BYMONTHDAY", "")
    interval = int(parts.get("INTERVAL", "1"))

    minute = byminute
    hour = byhour

    if freq == "DAILY":
        if interval == 1:
            return f"{minute} {hour} * * *"
        return f"{minute} {hour} */{interval} * *"

    if freq == "WEEKLY":
        day_map = {
            "MO": "1", "TU": "2", "WE": "3", "TH": "4",
            "FR": "5", "SA": "6", "SU": "0",
        }
        if byday:
            days = ",".join(
                day_map.get(d.strip(), "*") for d in byday.split(",")
            )
        else:
            days = "*"
        return f"{minute} {hour} * * {days}"

    if freq == "MONTHLY":
        day = bymonthday if bymonthday else "1"
        return f"{minute} {hour} {day} * *"

    if freq == "HOURLY":
        if interval == 1:
            return f"{minute} * * * *"
        return f"{minute} */{interval} * * *"

    if freq == "MINUTELY":
        if interval == 1:
            return "* * * * *"
        return f"*/{interval} * * * *"

    return None


def _compute_next_runs(
    cron_expr: str,
    count: int = 3,
    after: datetime | None = None,
    tz: str = "UTC",
) -> list[datetime]:
    """Compute the next N run times from a cron expression.

    Uses a simple cron field parser for preview purposes.
    """
    from apscheduler.triggers.cron import CronTrigger

    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
    except Exception:
        return []

    now = after or datetime.now(timezone.utc)
    runs: list[datetime] = []
    current = now

    for _ in range(count):
        next_fire = trigger.get_next_fire_time(None, current)
        if next_fire is None:
            break
        runs.append(next_fire)
        current = next_fire + timedelta(seconds=1)

    return runs


def parse_time_expression(
    text: str,
    default_timezone: str = "UTC",
    reference_time: datetime | None = None,
) -> ParsedSchedule | None:
    """Parse a natural language time expression into a ParsedSchedule.

    Handles both one-shot ("tomorrow at 3pm") and recurring
    ("every Monday at 9am") patterns.

    Returns None if the text cannot be parsed as a time expression.
    """
    text = text.strip()
    if not text:
        return None

    ref = reference_time or datetime.now(timezone.utc)

    # Try recurring first
    if _is_recurring(text):
        schedule = _parse_recurring(text, default_timezone, ref)
        if schedule:
            return schedule

    # Try absolute/relative date
    schedule = _parse_absolute(text, default_timezone, ref)
    if schedule:
        return schedule

    # Final fallback: try recurring even without keywords
    return _parse_recurring(text, default_timezone, ref)


def _parse_recurring(
    text: str,
    tz: str,
    ref: datetime,
) -> ParsedSchedule | None:
    """Parse a recurring time expression using recurrent."""
    try:
        r = RecurringEvent()
        rrule = r.parse(text)
    except Exception:
        logger.debug("recurrent failed to parse: %s", text)
        return None

    if not rrule:
        return None

    cron = _rrule_to_cron(rrule)
    if not cron:
        logger.debug("Could not convert RRULE to cron: %s", rrule)
        return None

    next_runs = _compute_next_runs(cron, count=3, after=ref, tz=tz)

    # Build human-readable description from recurrent
    human = _cron_to_human(cron, text)

    return ParsedSchedule(
        schedule_type=ScheduleType.RECURRING,
        cron_expr=cron,
        human_readable=human,
        next_runs=next_runs,
        timezone=tz,
    )


def _parse_absolute(
    text: str,
    tz: str,
    ref: datetime,
) -> ParsedSchedule | None:
    """Parse an absolute or relative time using dateparser."""
    settings: dict[str, Any] = {
        "TIMEZONE": tz,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": ref.replace(tzinfo=None),
    }

    try:
        parsed = dateparser.parse(text, settings=settings)
    except Exception:
        logger.debug("dateparser failed to parse: %s", text)
        return None

    if not parsed:
        return None

    # Ensure the date is in the future
    if parsed <= ref:
        return None

    human = parsed.strftime("%B %d, %Y at %I:%M %p %Z")

    return ParsedSchedule(
        schedule_type=ScheduleType.ONE_SHOT,
        run_date=parsed,
        human_readable=human,
        next_runs=[parsed],
        timezone=tz,
    )


def _cron_to_human(cron: str, original: str) -> str:
    """Generate a human-readable description from a cron expression.

    Uses the original text as a hint for a better description.
    """
    parts = cron.split()
    if len(parts) != 5:
        return original.capitalize()

    minute, hour, dom, month, dow = parts

    # Simple cases
    try:
        h = int(hour)
        m = int(minute)
        time_str = f"{h:d}:{m:02d} {'AM' if h < 12 else 'PM'}"
        if h > 12:
            time_str = f"{h - 12}:{m:02d} PM"
        elif h == 0:
            time_str = f"12:{m:02d} AM"
        elif h == 12:
            time_str = f"12:{m:02d} PM"
    except ValueError:
        time_str = f"{hour}:{minute}"

    if dom == "*" and month == "*" and dow == "*":
        return f"Daily at {time_str}"

    if dom == "*" and month == "*" and dow != "*":
        day_names = {
            "0": "Sunday", "1": "Monday", "2": "Tuesday",
            "3": "Wednesday", "4": "Thursday", "5": "Friday",
            "6": "Saturday",
        }
        days = ", ".join(day_names.get(d, d) for d in dow.split(","))
        return f"Every {days} at {time_str}"

    if dow == "*" and month == "*" and dom != "*":
        return f"Monthly on day {dom} at {time_str}"

    return original.capitalize()
