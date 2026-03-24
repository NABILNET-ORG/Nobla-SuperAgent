"""Tests for CodeGenerationTool and _extract_code helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams


class TestExtractCode:
    def test_strips_python_fences(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```python\nprint('hello')\n```"
        assert _extract_code(raw) == "print('hello')"

    def test_strips_generic_fences(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```\nsome code\n```"
        assert _extract_code(raw) == "some code"

    def test_no_fences_returns_stripped(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "  print('hello')  "
        assert _extract_code(raw) == "print('hello')"

    def test_multiple_blocks_returns_first(self):
        from nobla.tools.code.codegen import _extract_code
        raw = "```python\nfirst()\n```\ntext\n```python\nsecond()\n```"
        assert _extract_code(raw) == "first()"


class TestCodeGenerationTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value,
        )

    def test_tool_metadata(self):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()
        assert tool.name == "code.generate"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_description(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool
        tool = CodeGenerationTool()
        with pytest.raises(ValueError, match="[Dd]escription|empty"):
            await tool.validate(ToolParams(
                args={"description": ""}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_generate_only(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool, set_router
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "```python\nprint('hello')\n```"

        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        params = ToolParams(
            args={"description": "print hello", "language": "python"},
            connection_state=state,
        )
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["code"] == "print('hello')"
        assert result.data["language"] == "python"
        assert result.data["execution"] is None

    @pytest.mark.asyncio
    async def test_execute_generate_and_run(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool, set_router
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "print('hello')"

        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        with patch("nobla.tools.code.codegen.run_code") as mock_run:
            mock_run.return_value = SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            )

            params = ToolParams(
                args={"description": "print hello", "language": "python", "run": True},
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.success is True
            assert result.data["code"] == "print('hello')"
            assert result.data["execution"] is not None
            assert result.data["execution"]["stdout"] == "hello\n"
            assert "execution_time_ms" in result.data["execution"]
            mock_run.assert_awaited_once_with(
                "print('hello')", "python", "conn12345678",
            )

    @pytest.mark.asyncio
    async def test_execute_passes_max_tokens(self, state):
        from nobla.tools.code.codegen import CodeGenerationTool, set_router
        tool = CodeGenerationTool()

        mock_response = MagicMock()
        mock_response.content = "x = 1"

        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        params = ToolParams(
            args={"description": "assign x"},
            connection_state=state,
        )
        await tool.execute(params)
        call_kwargs = mock_router.route.call_args.kwargs
        assert "max_tokens" in call_kwargs
