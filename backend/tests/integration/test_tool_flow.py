# backend/tests/integration/test_tool_flow.py
"""End-to-end tool execution via WebSocket."""
from __future__ import annotations

import pytest

from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestToolFlow:
    async def test_tool_list_returns_tools(self, authenticated_client: RpcClient):
        """Authenticated user can list available tools."""
        result = await authenticated_client.call_expect_result("tool.list", {})
        assert "tools" in result
        assert isinstance(result["tools"], list)

    async def test_tool_list_filtered_by_category(self, authenticated_client: RpcClient):
        """Can filter tool list by category."""
        result = await authenticated_client.call_expect_result(
            "tool.list", {"category": "code"}
        )
        assert "tools" in result
        for tool in result["tools"]:
            assert tool["category"] == "code"

    async def test_tool_execute_unknown_tool(self, authenticated_client: RpcClient):
        """Unknown tool returns error."""
        result = await authenticated_client.call_expect_result(
            "tool.execute", {"tool_name": "nonexistent.tool", "args": {}}
        )
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    async def test_tool_execute_permission_denied(self, ws_client: RpcClient):
        """Unauthenticated user (SAFE tier) denied access to ELEVATED+ tools."""
        await ws_client.call_expect_result(
            "system.register",
            {"passphrase": "testpassphrase123"},
        )
        result = await ws_client.call_expect_result(
            "tool.execute",
            {"tool_name": "test.admin_action", "args": {}},
        )
        assert result["success"] is False

    async def test_approval_response_acknowledged(self, authenticated_client: RpcClient):
        """Approval response returns acknowledged even if no pending request."""
        result = await authenticated_client.call_expect_result(
            "tool.approval_response",
            {"request_id": "nonexistent", "approved": True},
        )
        assert result["status"] == "acknowledged"
