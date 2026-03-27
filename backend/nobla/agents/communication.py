"""A2A Protocol — task-based agent messaging over event bus (Phase 6).

All agent communication flows through this protocol. Uses asyncio.Future
for wait_for_result (same pattern as ConfirmationManager in automation/).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from nobla.agents.models import AgentMessage, AgentTask, MessageType, TaskStatus
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

EVENT_PREFIX = "agent.a2a"


class A2AProtocol:
    """Routes agent-to-agent communication through the event bus."""

    def __init__(self, event_bus: NoblaEventBus) -> None:
        self._event_bus = event_bus
        self._pending: dict[str, asyncio.Future[AgentTask]] = {}

        # Subscribe to result/error events to resolve futures
        self._event_bus.subscribe(
            f"{EVENT_PREFIX}.task.result", self._on_task_complete,
        )
        self._event_bus.subscribe(
            f"{EVENT_PREFIX}.task.error", self._on_task_complete,
        )

    async def send_task(
        self, sender: str, recipient: str, task: AgentTask,
    ) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.assign",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "recipient": recipient,
                "task": task.model_dump(),
            },
            correlation_id=task.task_id,
        ))

    async def send_result(self, sender: str, task: AgentTask) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.result",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "task": task.model_dump(),
            },
            correlation_id=task.task_id,
        ))

    async def send_status(self, sender: str, task: AgentTask) -> None:
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.status",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "status": task.status.value,
            },
            correlation_id=task.task_id,
        ))

    async def send_error(
        self, sender: str, task: AgentTask, error: str,
    ) -> None:
        task.status = TaskStatus.FAILED
        await self._event_bus.emit(NoblaEvent(
            event_type=f"{EVENT_PREFIX}.task.error",
            source=f"agent.{sender}",
            payload={
                "sender": sender,
                "task_id": task.task_id,
                "task": task.model_dump(),
                "error": error,
            },
            correlation_id=task.task_id,
        ))

    async def query_capabilities(
        self, sender: str, recipient: str,
    ) -> dict:
        """Query an agent's capabilities. Deferred to Phase 6 v2.

        TODO(phase6-v2): Implement request/response via Future pattern
        using agent.a2a.capability.query / agent.a2a.capability.response events.
        """
        raise NotImplementedError("Capability discovery deferred to v2")

    async def wait_for_result(
        self, task_id: str, timeout: float = 300,
    ) -> AgentTask:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AgentTask] = loop.create_future()
        self._pending[task_id] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(task_id, None)

    async def _on_task_complete(self, event: NoblaEvent) -> None:
        task_id = event.payload.get("task_id")
        if not task_id:
            return
        future = self._pending.get(task_id)
        if future is None or future.done():
            return
        task_data = event.payload.get("task", {})
        task = AgentTask.model_validate(task_data)
        future.set_result(task)
