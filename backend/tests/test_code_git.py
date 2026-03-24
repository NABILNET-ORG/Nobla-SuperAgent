"""Tests for GitTool — subcommands, conditional approval, URL validation."""
from __future__ import annotations

import shlex
from unittest.mock import AsyncMock, patch

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.security.sandbox import SandboxResult
from nobla.tools.models import ToolCategory, ToolParams


class TestGitToolMetadata:
    def test_metadata(self):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        assert tool.name == "git.ops"
        assert tool.category == ToolCategory.GIT
        assert tool.tier == Tier.ELEVATED
        assert tool.requires_approval is False


class TestGitNeedsApproval:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    def test_clone_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "clone"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_status_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "status"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_commit_no_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "commit"}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_push_requires_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "push"}, connection_state=state)
        assert tool.needs_approval(params) is True

    def test_create_pr_requires_approval(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(args={"operation": "create_pr"}, connection_state=state)
        assert tool.needs_approval(params) is True


class TestGitValidation:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    @pytest.mark.asyncio
    async def test_rejects_invalid_operation(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Ii]nvalid|operation"):
            await tool.validate(ToolParams(
                args={"operation": "rebase"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_requires_repo_url(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="repo_url"):
            await tool.validate(ToolParams(
                args={"operation": "clone"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_rejects_local_path(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Hh]ost|allowed"):
            await tool.validate(ToolParams(
                args={"operation": "clone", "repo_url": "/tmp/evil-repo"},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_rejects_disallowed_host(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="[Hh]ost|allowed"):
            await tool.validate(ToolParams(
                args={"operation": "clone", "repo_url": "https://evil.com/repo.git"},
                connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_clone_accepts_allowed_host(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        # Should not raise
        await tool.validate(ToolParams(
            args={"operation": "clone", "repo_url": "https://github.com/user/repo.git"},
            connection_state=state,
        ))

    @pytest.mark.asyncio
    async def test_commit_requires_message(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="message"):
            await tool.validate(ToolParams(
                args={"operation": "commit"}, connection_state=state,
            ))

    @pytest.mark.asyncio
    async def test_create_pr_requires_title(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with pytest.raises(ValueError, match="title"):
            await tool.validate(ToolParams(
                args={"operation": "create_pr"}, connection_state=state,
            ))


class TestGitExecution:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn12345678", user_id="u1", tier=Tier.ELEVATED.value,
        )

    @pytest.mark.asyncio
    async def test_status_executes(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="On branch main\nnothing to commit", stderr="",
                exit_code=0, execution_time_ms=100, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"operation": "status"},
                connection_state=state,
            )
            result = await tool.execute(params)
            assert result.success is True
            assert result.data["operation"] == "status"
            assert "branch main" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_clone_uses_network(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="Cloning...", stderr="", exit_code=0,
                execution_time_ms=5000, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"operation": "clone", "repo_url": "https://github.com/user/repo.git"},
                connection_state=state,
            )
            await tool.execute(params)
            call_kwargs = sandbox.execute_command.call_args.kwargs
            assert call_kwargs.get("network") is True

    @pytest.mark.asyncio
    async def test_commit_uses_sh(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        with patch("nobla.tools.code.git.get_sandbox") as mock_gs:
            sandbox = AsyncMock()
            sandbox.execute_command = AsyncMock(return_value=SandboxResult(
                stdout="[main abc1234] test commit", stderr="",
                exit_code=0, execution_time_ms=200, timed_out=False,
            ))
            mock_gs.return_value = sandbox

            params = ToolParams(
                args={"operation": "commit", "message": "test commit"},
                connection_state=state,
            )
            await tool.execute(params)
            cmd = sandbox.execute_command.call_args.kwargs.get("cmd")
            if cmd is None:
                cmd = sandbox.execute_command.call_args[0][0]
            assert cmd[0] == "sh"
            assert cmd[1] == "-c"


class TestGitDescribeAction:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn123", user_id="u1", tier=Tier.ELEVATED.value,
        )

    def test_push_description(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(
            args={"operation": "push", "branch": "feature-x"},
            connection_state=state,
        )
        desc = tool.describe_action(params)
        assert "Push" in desc
        assert "feature-x" in desc

    def test_create_pr_description(self, state):
        from nobla.tools.code.git import GitTool
        tool = GitTool()
        params = ToolParams(
            args={"operation": "create_pr", "title": "Add feature"},
            connection_state=state,
        )
        desc = tool.describe_action(params)
        assert "PR" in desc
        assert "Add feature" in desc
