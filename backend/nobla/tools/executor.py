# backend/nobla/tools/executor.py
"""Tool execution pipeline: permission -> approval -> execute -> audit."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

import structlog

from nobla.events.models import NoblaEvent
from nobla.security.audit import AuditEntry
from nobla.security.permissions import InsufficientPermissions, PermissionChecker, Tier
from nobla.tools.approval import ApprovalManager
from nobla.tools.models import ApprovalRequest, ApprovalStatus, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class ToolExecutor:
    """Runs tools through the 5-step execution pipeline."""

    def __init__(
        self,
        registry: ToolRegistry,
        permission_checker: PermissionChecker,
        audit_logger: Callable[[AuditEntry], Awaitable[None]],
        approval_manager: ApprovalManager,
        connection_manager=None,
        max_concurrent: int = 5,
        event_bus=None,
    ):
        self.registry = registry
        self.checker = permission_checker
        self.audit = audit_logger
        self.approvals = approval_manager
        self._cm = connection_manager
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: set[asyncio.Task] = set()
        self._event_bus = event_bus

    async def execute(self, tool_name: str, params: ToolParams) -> ToolResult:
        start = time.monotonic()

        # 1. Tool exists?
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # 2. Permission check
        try:
            self.checker.check(
                Tier(params.connection_state.tier), tool.tier
            )
        except InsufficientPermissions as exc:
            await self._audit(tool, params, "permission_denied", start)
            return ToolResult(success=False, error=str(exc))

        # 3. Validate params
        try:
            await tool.validate(params)
        except ValueError as exc:
            await self._audit(tool, params, "validation_failed", start)
            return ToolResult(success=False, error=f"Invalid params: {exc}")

        # 4. Approval (if required)
        approval_required = False
        if tool.needs_approval(params):
            approval_required = True
            request = ApprovalRequest(
                request_id=str(uuid.uuid4()),
                tool_name=tool.name,
                description=tool.describe_action(params),
                params_summary=tool.get_params_summary(params),
                timeout_seconds=tool.approval_timeout,
            )
            status = await self.approvals.request_approval(
                request, params.connection_state.connection_id,
            )
            if status != ApprovalStatus.APPROVED:
                await self._audit(
                    tool, params, f"approval_{status.value}", start,
                )
                return ToolResult(
                    success=False,
                    error=f"Action {status.value} by user",
                    approval_was_required=True,
                )

        # 5. Execute (with concurrency control and task tracking)
        correlation_id = str(uuid.uuid4())
        async with self._semaphore:
            task = asyncio.current_task()
            if task:
                self._running_tasks.add(task)
            try:
                result = await tool.execute(params)
                result.approval_was_required = approval_required
                result.execution_time_ms = int(
                    (time.monotonic() - start) * 1000
                )
                await self._audit(tool, params, "success", start)
                await self._emit_tool_event(
                    "tool.executed", tool, params, result, correlation_id,
                )
                return result
            except asyncio.CancelledError:
                await self._audit(tool, params, "killed", start)
                result = ToolResult(
                    success=False,
                    error="Tool execution cancelled by kill switch",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )
                await self._emit_tool_event(
                    "tool.failed", tool, params, result, correlation_id,
                )
                return result
            except Exception as exc:
                await self._audit(tool, params, "execution_error", start)
                result = ToolResult(
                    success=False,
                    error=f"Tool execution failed: {exc}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )
                await self._emit_tool_event(
                    "tool.failed", tool, params, result, correlation_id,
                )
                return result
            finally:
                if task:
                    self._running_tasks.discard(task)

    def handle_kill(self) -> None:
        """Kill switch callback: deny approvals + cancel in-flight tasks."""
        self.approvals.deny_all()
        for task in self._running_tasks:
            task.cancel()
        self._running_tasks.clear()
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def _emit_tool_event(
        self, event_type: str, tool, params: ToolParams,
        result: ToolResult, correlation_id: str,
    ) -> None:
        """Emit a tool.executed or tool.failed event on the event bus."""
        if self._event_bus is None:
            return
        event = NoblaEvent(
            event_type=event_type,
            source=f"tool.{tool.name}",
            payload={
                "tool_name": tool.name,
                "category": tool.category.value,
                "success": result.success,
                "execution_time_ms": result.execution_time_ms,
                "error": result.error,
            },
            user_id=params.connection_state.user_id,
            correlation_id=correlation_id,
        )
        try:
            await self._event_bus.emit(event)
        except Exception:
            logger.warning("Failed to emit %s event for %s", event_type, tool.name)

    async def _audit(self, tool, params: ToolParams, status: str, start: float):
        latency = int((time.monotonic() - start) * 1000)
        entry = AuditEntry(
            user_id=params.connection_state.user_id,
            action=f"tool.{tool.name}",
            method="tool.execute",
            tier=params.connection_state.tier,
            status=status,
            latency_ms=latency,
            metadata={
                "category": tool.category.value,
                "params": tool.get_params_summary(params),
            },
        )
        await self.audit(entry)

        # Broadcast activity feed notification
        if self._cm:
            conn_id = params.connection_state.connection_id
            await self._cm.send_to(conn_id, {
                "jsonrpc": "2.0",
                "method": "tool.activity",
                "params": {
                    "tool_name": tool.name,
                    "category": tool.category.value,
                    "description": tool.describe_action(params),
                    "status": status,
                    "execution_time_ms": latency,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
