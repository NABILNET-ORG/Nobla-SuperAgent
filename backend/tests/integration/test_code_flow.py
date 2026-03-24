"""Integration tests for Phase 4C code execution tools."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import PermissionChecker, Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.approval import ApprovalManager
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ToolParams
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY

# Ensure all code tools are imported so @register_tool fires at module level.
import nobla.tools.code.runner     # noqa: F401
import nobla.tools.code.packages   # noqa: F401
import nobla.tools.code.codegen    # noqa: F401
import nobla.tools.code.debug      # noqa: F401
import nobla.tools.code.git        # noqa: F401


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset registry between tests.

    ``_TOOL_REGISTRY.clear()`` restores module-level (baseline) tools
    automatically, so all 5 Phase 4C tools remain available after each reset.
    """
    _TOOL_REGISTRY.clear()
    yield
    _TOOL_REGISTRY.clear()


@pytest.fixture()
def executor():
    """Build a ToolExecutor wired to the live registry."""
    registry = ToolRegistry()
    checker = PermissionChecker()
    audit = AsyncMock()
    cm = AsyncMock()
    approvals = ApprovalManager(cm)
    return ToolExecutor(registry, checker, audit, approvals)


@pytest.fixture()
def standard_state():
    return ConnectionState(
        connection_id="conn12345678", user_id="u1", tier=Tier.STANDARD.value,
    )


@pytest.fixture()
def elevated_state():
    return ConnectionState(
        connection_id="conn12345678", user_id="u1", tier=Tier.ELEVATED.value,
    )


class TestToolRegistration:
    def test_all_tools_registered(self, executor):
        """All 5 Phase 4C tools should be in the registry."""
        expected = {
            "code.run", "code.install_package", "code.generate",
            "code.debug", "git.ops",
        }
        registered = set(_TOOL_REGISTRY.keys())
        for name in expected:
            assert name in registered, f"{name} not registered"


class TestPermissionTiers:
    @pytest.mark.asyncio
    async def test_standard_can_run_code(self, executor, standard_state):
        """STANDARD tier can use code.run."""
        with patch("nobla.tools.code.runner.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute = AsyncMock(return_value=SandboxResult(
                stdout="hi\n", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            params = ToolParams(
                args={"code": "print('hi')", "language": "python"},
                connection_state=standard_state,
            )
            result = await executor.execute("code.run", params)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_standard_cannot_install_packages(self, executor, standard_state):
        """STANDARD tier lacks ELEVATED permission for code.install_package."""
        params = ToolParams(
            args={"packages": ["numpy"]},
            connection_state=standard_state,
        )
        result = await executor.execute("code.install_package", params)
        assert result.success is False
        assert "permission" in result.error.lower() or "tier" in result.error.lower()

    @pytest.mark.asyncio
    async def test_standard_cannot_use_git(self, executor, standard_state):
        """STANDARD tier lacks ELEVATED permission for git.ops."""
        params = ToolParams(
            args={"operation": "status"},
            connection_state=standard_state,
        )
        result = await executor.execute("git.ops", params)
        assert result.success is False


class TestGitApprovalFlow:
    @pytest.mark.asyncio
    async def test_git_push_triggers_approval(self, executor, elevated_state):
        """git push requires user approval; timing out returns failure."""
        params = ToolParams(
            args={"operation": "push"},
            connection_state=elevated_state,
        )
        tool = _TOOL_REGISTRY.get("git.ops")
        if tool:
            tool.approval_timeout = 1
        result = await executor.execute("git.ops", params)
        assert result.success is False
        assert result.approval_was_required is True

    @pytest.mark.asyncio
    async def test_git_status_no_approval(self, executor, elevated_state):
        """git status does not require approval and runs directly."""
        with patch("nobla.tools.code.git.get_sandbox") as mock:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="On branch main", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            ))
            mock.return_value = sandbox

            params = ToolParams(
                args={"operation": "status"},
                connection_state=elevated_state,
            )
            result = await executor.execute("git.ops", params)
            assert result.success is True
            assert result.approval_was_required is False


class TestCodeGenerateIntegration:
    @pytest.mark.asyncio
    async def test_generate_and_run(self, executor, elevated_state):
        """Integration: code.generate with run=True through executor."""
        from nobla.tools.code.codegen import set_router
        mock_router = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "print('hello')"
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        with patch("nobla.tools.code.codegen.run_code") as mock_run:
            mock_run.return_value = SandboxResult(
                stdout="hello\n", stderr="", exit_code=0,
                execution_time_ms=50, timed_out=False,
            )

            params = ToolParams(
                args={
                    "description": "print hello",
                    "language": "python",
                    "run": True,
                },
                connection_state=elevated_state,
            )
            result = await executor.execute("code.generate", params)
            assert result.success is True
            assert result.data["code"] == "print('hello')"
            assert result.data["execution"] is not None
            assert result.data["execution"]["stdout"] == "hello\n"


class TestCodeDebugIntegration:
    @pytest.mark.asyncio
    async def test_debug_through_executor(self, executor, elevated_state):
        """Integration: code.debug returns parsed error + suggestion."""
        from nobla.tools.code.codegen import set_router
        mock_router = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Change int('abc') to int('123')."
        mock_router.route = AsyncMock(return_value=mock_response)
        set_router(mock_router)

        params = ToolParams(
            args={
                "error": 'File "app.py", line 5\nValueError: invalid literal',
                "code": "x = int('abc')",
                "language": "python",
            },
            connection_state=elevated_state,
        )
        result = await executor.execute("code.debug", params)
        assert result.success is True
        assert result.data["parsed_error"]["type"] == "ValueError"
        assert len(result.data["suggestion"]) > 0
