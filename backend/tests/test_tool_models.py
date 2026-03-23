from __future__ import annotations

import pytest

from nobla.tools.models import (
    ApprovalRequest,
    ApprovalStatus,
    ToolCategory,
    ToolParams,
    ToolResult,
)


class TestToolCategory:
    def test_all_categories_exist(self):
        expected = {"vision", "input", "file_system", "app_control",
                    "code", "git", "ssh", "clipboard", "search"}
        assert {c.value for c in ToolCategory} == expected

    def test_category_is_string(self):
        assert ToolCategory.VISION == "vision"
        assert isinstance(ToolCategory.VISION, str)


class TestToolParams:
    def test_creation_with_defaults(self):
        from nobla.gateway.websocket import ConnectionState

        state = ConnectionState()
        params = ToolParams(args={"key": "value"}, connection_state=state)
        assert params.args == {"key": "value"}
        assert params.context is None

    def test_creation_with_context(self):
        from nobla.gateway.websocket import ConnectionState

        state = ConnectionState(user_id="u1", tier=2)
        params = ToolParams(
            args={"code": "print(1)"},
            connection_state=state,
            context={"conversation_id": "c1"},
        )
        assert params.context["conversation_id"] == "c1"
        assert params.connection_state.tier == 2


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"output": "hello"})
        assert result.success is True
        assert result.error is None
        assert result.execution_time_ms == 0
        assert result.approval_was_required is False

    def test_error_result(self):
        result = ToolResult(success=False, error="Permission denied")
        assert result.success is False
        assert result.error == "Permission denied"


class TestApprovalRequest:
    def test_creation_with_defaults(self):
        req = ApprovalRequest(
            request_id="abc-123",
            tool_name="mouse.click",
            description="Click at (100, 200)",
            params_summary={"x": 100, "y": 200},
        )
        assert req.timeout_seconds == 30
        assert req.status == ApprovalStatus.PENDING
        assert req.screenshot_b64 is None

    def test_all_approval_statuses(self):
        expected = {"pending", "approved", "denied", "timed_out"}
        assert {s.value for s in ApprovalStatus} == expected
