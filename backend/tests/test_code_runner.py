"""Tests for code execution shared helpers and CodeRunnerTool."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


# --- Shared helpers ---


class TestSharedHelpers:
    def test_packageable_languages(self):
        from nobla.tools.code import PACKAGEABLE_LANGUAGES
        assert "python" in PACKAGEABLE_LANGUAGES
        assert "javascript" in PACKAGEABLE_LANGUAGES
        assert "bash" not in PACKAGEABLE_LANGUAGES

    def test_package_env(self):
        from nobla.tools.code import PACKAGE_ENV
        assert "PYTHONPATH" in PACKAGE_ENV["python"]
        assert "NODE_PATH" in PACKAGE_ENV["javascript"]
        assert "/packages/node/node_modules" in PACKAGE_ENV["javascript"]["NODE_PATH"]

    def test_get_volume_name(self):
        from nobla.tools.code import get_volume_name
        name = get_volume_name("nobla-pkg", "python", "abcdef1234567890")
        assert name == "nobla-pkg-python-abcdef12"

    def test_get_volume_name_truncates_connection_id(self):
        from nobla.tools.code import get_volume_name
        name = get_volume_name("prefix", "js", "short")
        assert name == "prefix-js-short"


# --- run_code free function ---


class TestRunCode:
    @pytest.fixture()
    def mock_sandbox(self):
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=100, timed_out=False,
            ))
            mock.return_value = sandbox
            yield sandbox

    @pytest.mark.asyncio
    async def test_run_code_python_with_volume(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        result = await run_code("print('hi')", "python", "conn12345678")
        mock_sandbox.execute.assert_awaited_once()
        call_kwargs = mock_sandbox.execute.call_args
        assert call_kwargs.kwargs.get("volumes") is not None
        assert "python" in list(call_kwargs.kwargs["volumes"].keys())[0]
        assert result.stdout == "hello\n"

    @pytest.mark.asyncio
    async def test_run_code_bash_no_volume(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        await run_code("echo hi", "bash", "conn12345678")
        call_kwargs = mock_sandbox.execute.call_args
        assert call_kwargs.kwargs.get("volumes") is None

    @pytest.mark.asyncio
    async def test_run_code_sets_environment(self, mock_sandbox):
        from nobla.tools.code.runner import run_code
        await run_code("print('hi')", "python", "conn12345678")
        call_kwargs = mock_sandbox.execute.call_args
        env = call_kwargs.kwargs.get("environment")
        assert env is not None
        assert "PYTHONPATH" in env


# --- CodeRunnerTool ---


class TestCodeRunnerTool:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value
        )

    @pytest.fixture()
    def mock_sandbox(self):
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="result\n", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox
            yield sandbox

    def test_tool_metadata(self):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        assert tool.name == "code.run"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_code(self, state):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        with pytest.raises(ValueError, match="[Cc]ode.*required|empty"):
            await tool.validate(ToolParams(args={"code": ""}, connection_state=state))

    @pytest.mark.asyncio
    async def test_validate_rejects_unsupported_language(self, state):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        with pytest.raises(ValueError, match="[Uu]nsupported|language"):
            await tool.validate(ToolParams(
                args={"code": "x", "language": "ruby"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_execute_returns_structured_result(self, state, mock_sandbox):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        params = ToolParams(
            args={"code": "print('hi')", "language": "python"},
            connection_state=state,
        )
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["stdout"] == "result\n"
        assert result.data["exit_code"] == 0
        assert result.data["language"] == "python"
        assert "truncated" in result.data

    @pytest.mark.asyncio
    async def test_validate_rejects_when_disabled(self, state):
        from nobla.tools.code.runner import CodeRunnerTool
        tool = CodeRunnerTool()
        with patch("nobla.tools.code.runner.get_settings") as mock_settings:
            settings = MagicMock()
            settings.code.enabled = False
            mock_settings.return_value = settings
            with pytest.raises(ValueError, match="[Dd]isabled"):
                await tool.validate(ToolParams(
                    args={"code": "print('hi')"}, connection_state=state,
                ))

    @pytest.mark.asyncio
    async def test_execute_truncates_long_output(self, state):
        long_output = "x" * 100000
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout=long_output, stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            from nobla.tools.code.runner import CodeRunnerTool
            tool = CodeRunnerTool()
            params = ToolParams(
                args={"code": "x", "language": "python"},
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.data["truncated"] is True
            assert len(result.data["stdout"]) == 50000
