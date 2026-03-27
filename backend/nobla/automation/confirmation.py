"""Confirmation flow — user must approve before tasks are scheduled (Phase 6).

No task is ever created without explicit user confirmation. The flow:
1. Build a ConfirmationRequest with task details and next runs.
2. Emit ``scheduler.confirmation.requested`` on the event bus.
3. Wait for approval/denial via ``scheduler.confirmation.response``.
4. Return the decision to the caller (service.py).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from nobla.automation.models import (
    ConfirmationRequest,
    ParsedSchedule,
    ScheduledTask,
    TaskInterpretation,
    TaskStatus,
)
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)


class ConfirmationManager:
    """Manages the confirmation flow for scheduled tasks.

    Publishes confirmation requests on the event bus and waits for
    user responses. Times out after ``timeout_seconds``.
    """

    def __init__(
        self,
        event_bus: NoblaEventBus | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self._event_bus = event_bus
        self._timeout = timeout_seconds
        # {task_id: asyncio.Future}
        self._pending: dict[str, asyncio.Future[bool]] = {}

    def build_confirmation(
        self, task: ScheduledTask
    ) -> ConfirmationRequest:
        """Build a ConfirmationRequest from a ScheduledTask."""
        interp = task.interpretation
        sched = task.schedule

        return ConfirmationRequest(
            task_id=task.task_id,
            user_id=task.user_id,
            task_description=interp.task_description if interp else task.raw_input,
            schedule_description=sched.human_readable if sched else "Unknown schedule",
            next_runs=sched.next_runs[:3] if sched else [],
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self._timeout),
        )

    async def request_confirmation(
        self, task: ScheduledTask
    ) -> bool:
        """Request user confirmation and wait for response.

        Emits a ``scheduler.confirmation.requested`` event and blocks
        until the user responds or the timeout expires.

        Returns True if approved, False if denied or timed out.
        """
        confirmation = self.build_confirmation(task)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[task.task_id] = future

        # Emit confirmation request event
        await self._emit_event(
            "scheduler.confirmation.requested",
            {
                "task_id": confirmation.task_id,
                "user_id": confirmation.user_id,
                "task_description": confirmation.task_description,
                "schedule_description": confirmation.schedule_description,
                "next_runs": [
                    r.isoformat() for r in confirmation.next_runs
                ],
                "expires_at": confirmation.expires_at.isoformat()
                if confirmation.expires_at
                else None,
            },
            user_id=task.user_id,
        )

        try:
            approved = await asyncio.wait_for(future, timeout=self._timeout)
            return approved
        except asyncio.TimeoutError:
            logger.info(
                "Confirmation timed out for task %s", task.task_id
            )
            return False
        finally:
            self._pending.pop(task.task_id, None)

    def respond(self, task_id: str, approved: bool) -> bool:
        """Deliver a user's confirmation response.

        Called when the user approves or denies via UI/channel callback.
        Returns True if a pending confirmation was found.
        """
        future = self._pending.get(task_id)
        if not future or future.done():
            return False

        future.set_result(approved)
        return True

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def cancel_all(self) -> None:
        """Cancel all pending confirmations (e.g. on shutdown)."""
        for task_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(False)
        self._pending.clear()

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
