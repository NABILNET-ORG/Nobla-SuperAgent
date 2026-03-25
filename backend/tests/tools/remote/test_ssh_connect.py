"""Tests for ssh.connect tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com", "staging.example.com"],
        allowed_users=["deploy", "admin"],
        allowed_remote_dirs=["/home/deploy"],
        **rc_overrides,
    )
    return Settings(remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-ssh-test", user_id="u1", tier=Tier.ADMIN.value,
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


class TestSSHConnectMetadata:
    def test_name(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.name == "ssh.connect"

    def test_category(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.tier == Tier.ADMIN

    def test_requires_approval_false(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.requires_approval is False


class TestSSHConnectApproval:
    def test_connect_needs_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="connect", host="prod.example.com", user="deploy")
        assert tool.needs_approval(params) is True

    def test_disconnect_no_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="disconnect", connection_id="abc")
        assert tool.needs_approval(params) is False

    def test_list_no_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="list")
        assert tool.needs_approval(params) is False


class TestSSHConnectValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(action="connect", host="prod.example.com", user="deploy")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="hack")
        with pytest.raises(ValueError, match="Invalid action"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_missing_host_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", user="deploy")
        with pytest.raises(ValueError, match="host"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_missing_user_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="prod.example.com")
        with pytest.raises(ValueError, match="user"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_host_not_allowed_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="evil.com", user="deploy")
        with pytest.raises(ValueError, match="not in allowed_hosts"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_user_not_allowed_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="prod.example.com", user="root")
        with pytest.raises(ValueError, match="not in allowed_users"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_invalid_port_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy", port=99999
        )
        with pytest.raises(ValueError, match="port"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_password_without_opt_in_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings(allow_password_auth=False)
        params = _make_params(
            action="connect", host="prod.example.com",
            user="deploy", password="secret",
        )
        with pytest.raises(ValueError, match="password"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_disconnect_missing_connection_id_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="disconnect")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)


class TestSSHConnectExecute:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()

        mock_conn = AsyncMock()
        mock_conn.get_extra_info = MagicMock(return_value=b"sha256:abc123")

        with patch(
            "nobla.tools.remote.ssh_connect._async_connect",
            new=AsyncMock(return_value=mock_conn),
        ):
            params = _make_params(
                action="connect", host="prod.example.com", user="deploy",
            )
            result = await tool.execute(params)

        assert result.success is True
        assert "connection_id" in result.data

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_connect import SSHConnectTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()
        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="disconnect", connection_id=cid)
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["disconnected"] is True

    @pytest.mark.asyncio
    async def test_list_returns_connections(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_connect import SSHConnectTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        pool.add("prod.example.com", "deploy", 22, mock_conn, label="prod")

        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list")
        result = await tool.execute(params)
        assert result.success is True
        assert len(result.data["connections"]) == 1


class TestSSHConnectGracefulDegradation:
    @pytest.mark.asyncio
    async def test_connect_without_asyncssh_returns_error(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()

        with patch(
            "nobla.tools.remote.ssh_connect._async_connect",
            side_effect=RuntimeError("asyncssh is not installed"),
        ):
            params = _make_params(
                action="connect", host="prod.example.com", user="deploy",
            )
            result = await tool.execute(params)

        assert result.success is False
        assert "asyncssh" in result.error


class TestSSHConnectDescribeAction:
    def test_connect_description(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy", port=22,
        )
        desc = tool.describe_action(params)
        assert "deploy@prod.example.com:22" in desc

    def test_connect_password_warning(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy",
            password="secret",
        )
        desc = tool.describe_action(params)
        assert "password" in desc.lower()


class TestSSHConnectParamsSummary:
    def test_password_not_in_summary(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com",
            user="deploy", password="secret123", passphrase="key-pass",
        )
        summary = tool.get_params_summary(params)
        assert "secret123" not in str(summary)
        assert "key-pass" not in str(summary)
        assert summary["auth_method"] == "password"
