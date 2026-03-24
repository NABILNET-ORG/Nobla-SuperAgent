"""Tests for DebugAssistantTool and _parse_error helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams


class TestParseError:
    def test_python_traceback(self):
        from nobla.tools.code.debug import _parse_error
        error = 'File "main.py", line 42, in <module>\nValueError: invalid literal'
        result = _parse_error(error, "python")
        assert result["type"] == "ValueError"
        assert "invalid literal" in result["message"]
        assert result["file"] == "main.py"
        assert result["line"] == 42

    def test_javascript_error(self):
        from nobla.tools.code.debug import _parse_error
        error = "TypeError: Cannot read properties of undefined\n    at main.js:15"
        result = _parse_error(error, "javascript")
        assert result["type"] == "TypeError"
        assert "undefined" in result["message"]

    def test_bash_error(self):
        from nobla.tools.code.debug import _parse_error
        error = "script.sh: line 10: syntax error near unexpected token"
        result = _parse_error(error, "bash")
        assert result["line"] == 10

    def test_unknown_format_fallback(self):
        from nobla.tools.code.debug import _parse_error
        error = "something went wrong with no pattern"
        result = _parse_error(error, "python")
        assert result["type"] is None
        assert result["message"] is not None
        assert result["file"] is None
        assert result["line"] is None


class TestDebugAssistantTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value,
        )

    def test_tool_metadata(self):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()
        assert tool.name == "code.debug"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_error(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()
        with pytest.raises(ValueError, match="[Ee]rror.*required|empty"):
            await tool.validate(ToolParams(
                args={"error": ""}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_returns_suggestion(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()

        mock_response = MagicMock()
        mock_response.content = "The error is caused by... Fix: change X to Y."

        with patch("nobla.tools.code.debug.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            params = ToolParams(
                args={
                    "error": 'File "app.py", line 5\nValueError: invalid literal',
                    "code": "x = int('abc')",
                    "language": "python",
                },
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.success is True
            assert result.data["parsed_error"]["type"] == "ValueError"
            assert result.data["suggestion"] is not None
            assert len(result.data["suggestion"]) > 0

    @pytest.mark.asyncio
    async def test_execute_truncates_long_error(self, state):
        from nobla.tools.code.debug import DebugAssistantTool
        tool = DebugAssistantTool()

        mock_response = MagicMock()
        mock_response.content = "Fix it."

        with patch("nobla.tools.code.debug.get_router") as mock_router:
            router = AsyncMock()
            router.route = AsyncMock(return_value=mock_response)
            mock_router.return_value = router

            long_error = "E" * 100000
            params = ToolParams(
                args={"error": long_error},
                connection_state=state,
            )
            result = await tool.execute(params)
            call_args = router.route.call_args[0][0]  # messages list
            user_msg = [m for m in call_args if m.role == "user"][0]
            assert len(user_msg.content) < 100000
