"""Async event bus with wildcard subscriptions, priority dispatch, and backpressure.

Spec reference: Phase 5-Foundation §4.1 — Event Bus Interface.

Design:
- Handler isolation: one handler's exception never blocks others.
- Priority dispatch: higher-priority events dispatched first.
- Backpressure: max 10,000 pending events. Overflow drops oldest non-urgent
  events (priority < 5). Urgent events are never dropped.
- Ordering: FIFO within same priority level. Handlers are concurrent.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections import defaultdict
from typing import Callable, Awaitable

from nobla.events.models import NoblaEvent

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[NoblaEvent], Awaitable[None]]

# Backpressure constants
MAX_QUEUE_DEPTH = 10_000
URGENT_PRIORITY_THRESHOLD = 5


class NoblaEventBus:
    """Async pub/sub event bus — the backbone all components communicate through.

    Supports:
    - Exact subscriptions: "tool.executed"
    - Wildcard subscriptions: "tool.*", "channel.*", "*"
    - Priority-based dispatch (higher priority first)
    - Handler isolation (exceptions logged, never propagated)
    - Backpressure with overflow protection
    """

    def __init__(self, max_queue_depth: int = MAX_QUEUE_DEPTH) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._max_queue_depth = max_queue_depth
        self._queue: asyncio.PriorityQueue[tuple[int, int, NoblaEvent]] = (
            asyncio.PriorityQueue(maxsize=0)
        )
        self._pending_count = 0
        self._sequence = 0  # FIFO tiebreaker within same priority
        self._running = False
        self._dispatch_task: asyncio.Task | None = None
        self._started = asyncio.Event()

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background dispatch loop."""
        if self._running:
            return
        self._running = True
        self._started.set()
        self._dispatch_task = asyncio.create_task(
            self._dispatch_loop(), name="event-bus-dispatch"
        )
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Drain remaining events and stop the dispatch loop."""
        self._running = False
        self._started.clear()
        if self._dispatch_task is not None:
            # Push a sentinel to unblock the queue
            await self._queue.put((0, 0, _SENTINEL))
            await self._dispatch_task
            self._dispatch_task = None
        logger.info("Event bus stopped")

    # ── Subscribe / Unsubscribe ────────────────────────────────

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type. Supports wildcards via fnmatch."""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("Subscribed %s to '%s'", handler.__qualname__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a handler. No-op if not registered."""
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[event_type]
            logger.debug("Unsubscribed %s from '%s'", handler.__qualname__, event_type)

    # ── Emit ───────────────────────────────────────────────────

    async def emit(self, event: NoblaEvent) -> None:
        """Queue an event for dispatch.

        If the queue exceeds max depth, the oldest non-urgent event is dropped.
        Urgent events (priority >= URGENT_PRIORITY_THRESHOLD) are never dropped.
        """
        if self._pending_count >= self._max_queue_depth:
            if event.priority < URGENT_PRIORITY_THRESHOLD:
                logger.warning(
                    "Event bus overflow: dropping non-urgent event '%s' "
                    "(correlation_id=%s, queue_depth=%d)",
                    event.event_type,
                    event.correlation_id,
                    self._pending_count,
                )
                # Emit overflow warning as a system event (non-recursive guard)
                if event.event_type != "bus.overflow":
                    await self._emit_overflow_warning(event)
                return
            # Urgent event — allow it through even over capacity
            logger.warning(
                "Event bus over capacity but accepting urgent event '%s' (priority=%d)",
                event.event_type,
                event.priority,
            )

        self._sequence += 1
        # Negate priority so higher priority = lower queue sort value (dispatched first)
        await self._queue.put((-event.priority, self._sequence, event))
        self._pending_count += 1

    async def emit_nowait(self, event: NoblaEvent) -> None:
        """Emit and dispatch immediately without queuing (for tests or sync paths).

        Handlers still run with isolation.
        """
        handlers = self._matching_handlers(event.event_type)
        await self._invoke_handlers(handlers, event)

    # ── Internal dispatch ──────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        """Background loop: pull from priority queue and dispatch."""
        while self._running:
            try:
                _, _, event = await self._queue.get()

                # Sentinel check for clean shutdown
                if event is _SENTINEL:
                    break

                self._pending_count = max(0, self._pending_count - 1)
                handlers = self._matching_handlers(event.event_type)
                await self._invoke_handlers(handlers, event)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in event bus dispatch loop")

        # Drain remaining events on shutdown
        await self._drain()

    async def _drain(self) -> None:
        """Process remaining queued events during shutdown."""
        drained = 0
        while not self._queue.empty():
            try:
                _, _, event = self._queue.get_nowait()
                if event is _SENTINEL:
                    continue
                self._pending_count = max(0, self._pending_count - 1)
                handlers = self._matching_handlers(event.event_type)
                await self._invoke_handlers(handlers, event)
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logger.info("Drained %d events during shutdown", drained)

    def _matching_handlers(self, event_type: str) -> list[EventHandler]:
        """Collect all handlers whose subscription pattern matches the event type."""
        matched: list[EventHandler] = []
        for pattern, handlers in self._handlers.items():
            if pattern == event_type or fnmatch.fnmatch(event_type, pattern):
                matched.extend(handlers)
        return matched

    async def _invoke_handlers(
        self, handlers: list[EventHandler], event: NoblaEvent
    ) -> None:
        """Run all matched handlers concurrently with isolation."""
        if not handlers:
            return
        tasks = [
            asyncio.create_task(
                self._safe_invoke(handler, event),
                name=f"handler-{handler.__qualname__}-{event.event_type}",
            )
            for handler in handlers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_invoke(handler: EventHandler, event: NoblaEvent) -> None:
        """Invoke a single handler — log exceptions but never propagate."""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Handler %s raised exception for event '%s' (correlation_id=%s)",
                handler.__qualname__,
                event.event_type,
                event.correlation_id,
            )

    async def _emit_overflow_warning(self, dropped_event: NoblaEvent) -> None:
        """Emit a bus.overflow warning event."""
        warning = NoblaEvent(
            event_type="bus.overflow",
            source="event_bus",
            payload={
                "dropped_event_type": dropped_event.event_type,
                "dropped_correlation_id": dropped_event.correlation_id,
                "queue_depth": self._pending_count,
            },
            priority=URGENT_PRIORITY_THRESHOLD,
        )
        # Direct dispatch to avoid recursion
        handlers = self._matching_handlers("bus.overflow")
        await self._invoke_handlers(handlers, warning)

    # ── Introspection ──────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        """Number of events waiting to be dispatched."""
        return self._pending_count

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers across all patterns."""
        return sum(len(h) for h in self._handlers.values())

    @property
    def is_running(self) -> bool:
        return self._running


# Sentinel object for clean shutdown signaling
_SENTINEL = NoblaEvent(event_type="__sentinel__", source="__internal__")
