"""Tests for ssh.exec tool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from nobla.config.settings import RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com"],
        allowed_users=["deploy"],
        allowed_remote_dirs=["/home/deploy"],
        **rc_overrides,
    )
    return Settings(remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-exec-test", user_id="u1", tier=Tier.ADMIN.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset():
    RemoteControlGuard.reset()
    import nobla.tools.remote.pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


class TestSSHExecMetadata:
    def test_name(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.name == "ssh.exec"

    def test_category(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.tier == Tier.ADMIN


class TestSSHExecApproval:
    def test_safe_command_no_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="ls -la")
        assert tool.needs_approval(params) is False

    def test_unknown_command_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="deploy.sh")
        assert tool.needs_approval(params) is True

    def test_chained_command_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="ls; rm -rf /")
        assert tool.needs_approval(params) is True

    def test_pipe_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="cat file | grep secret")
        assert tool.needs_approval(params) is True

    def test_safe_command_with_args_no_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="whoami")
        assert tool.needs_approval(params) is False

    def test_env_prefix_safe_command(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="FOO=bar ls")
        assert tool.needs_approval(params) is False


class TestSSHExecValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(connection_id="abc", command="ls")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_connection_id_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(command="ls")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_command_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc")
        with pytest.raises(ValueError, match="command"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_timeout_exceeds_max_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings(max_command_timeout_s=60)
        params = _make_params(connection_id="abc", command="ls", timeout=120)
        with pytest.raises(ValueError, match="timeout"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_blocked_binary_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="mkfs /dev/sda1")
        with pytest.raises(ValueError, match="blocked"):
            await tool.validate(params)


class TestSSHExecExecute:
    @pytest.mark.asyncio
    async def test_run_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()

        # Mock the SSH process result
        mock_result = MagicMock()
        mock_result.stdout = "file1.txt\nfile2.txt\n"
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id=cid, command="ls")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["exit_code"] == 0
        assert "file1.txt" in result.data["stdout"]
        assert result.data["truncated"] is False

    @pytest.mark.asyncio
    async def test_run_with_nonzero_exit(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "No such file"
        mock_result.exit_status = 1
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id=cid, command="cat missing.txt")
        result = await tool.execute(params)

        assert result.success is True  # Command ran, just failed
        assert result.data["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_run_connection_not_found(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="nonexistent", command="ls")
        result = await tool.execute(params)
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = "x" * 2_000_000  # 2MB, over 1MB limit
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings(max_output_bytes=1000)
        params = _make_params(connection_id=cid, command="cat bigfile")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["truncated"] is True
        assert len(result.data["stdout"]) <= 1000


class TestSSHExecParamsSummary:
    def test_command_truncated_in_summary(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        long_cmd = "x" * 300
        params = _make_params(connection_id="abc", command=long_cmd)
        summary = tool.get_params_summary(params)
        assert len(summary["command"]) <= 203  # 200 + "..."
