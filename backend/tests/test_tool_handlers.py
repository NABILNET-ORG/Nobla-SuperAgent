from __future__ import annotations

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolResult


class FakeExecutor:
    def __init__(self, result=None):
        self._result = result or ToolResult(success=True, data="ok")

    async def execute(self, tool_name, params):
        return self._result


class FakeRegistry:
    def list_available(self, tier):
        return []

    def list_by_category(self, category):
        return []


class TestToolHandlers:
    async def test_handle_tool_execute_no_executor(self):
        import nobla.gateway.tool_handlers as th
        th._tool_executor = None
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_execute(
            {"tool_name": "test.echo", "args": {}}, state
        )
        assert "error" in result

    async def test_handle_tool_execute_with_executor(self):
        import nobla.gateway.tool_handlers as th
        th._tool_executor = FakeExecutor()
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_execute(
            {"tool_name": "test.echo", "args": {"x": 1}}, state
        )
        assert result["success"] is True

    async def test_handle_tool_list_empty(self):
        import nobla.gateway.tool_handlers as th
        th._tool_registry = FakeRegistry()
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_list({}, state)
        assert result == {"tools": []}

    async def test_handle_approval_response(self):
        import nobla.gateway.tool_handlers as th
        mock_mgr = MagicMock()
        th._approval_manager = mock_mgr
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_approval_response(
            {"request_id": "r1", "approved": True}, state
        )
        assert result["status"] == "acknowledged"
        mock_mgr.resolve.assert_called_once_with("r1", True)
