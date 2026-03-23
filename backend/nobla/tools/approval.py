"""Approval flow for tools requiring user confirmation."""
from __future__ import annotations

import asyncio

import structlog

from nobla.tools.models import ApprovalRequest, ApprovalStatus

logger = structlog.get_logger(__name__)


class ApprovalManager:
    """Sends approval requests to Flutter and awaits user response."""

    def __init__(self, connection_manager):
        self._cm = connection_manager
        self._pending: dict[str, asyncio.Future[ApprovalStatus]] = {}

    async def request_approval(
        self, request: ApprovalRequest, connection_id: str
    ) -> ApprovalStatus:
        """Send approval request via WebSocket, wait for response or timeout."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalStatus] = loop.create_future()
        self._pending[request.request_id] = future

        await self._cm.send_to(connection_id, {
            "jsonrpc": "2.0",
            "method": "tool.approval_request",
            "params": {
                "request_id": request.request_id,
                "tool_name": request.tool_name,
                "description": request.description,
                "params_summary": request.params_summary,
                "screenshot_b64": request.screenshot_b64,
                "timeout_seconds": request.timeout_seconds,
            },
        })

        try:
            return await asyncio.wait_for(
                future, timeout=request.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.info("approval_timed_out", request_id=request.request_id)
            return ApprovalStatus.TIMED_OUT
        finally:
            self._pending.pop(request.request_id, None)

    def resolve(self, request_id: str, approved: bool) -> None:
        """Called when Flutter sends back the user's decision."""
        future = self._pending.get(request_id)
        if future and not future.done():
            status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
            future.set_result(status)

    def deny_all(self) -> None:
        """Deny all pending approvals. Called by kill switch."""
        for future in self._pending.values():
            if not future.done():
                future.set_result(ApprovalStatus.DENIED)
        self._pending.clear()
