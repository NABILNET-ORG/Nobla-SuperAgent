"""Tests for sftp.manage tool."""

from __future__ import annotations

import os
import posixpath
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import ComputerControlSettings, RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    cc = ComputerControlSettings(
        allowed_read_dirs=["/tmp/test-read"],
        allowed_write_dirs=["/tmp/test-read/write"],
    )
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com"],
        allowed_users=["deploy"],
        allowed_remote_dirs=["/home/deploy", "/var/www"],
        **rc_overrides,
    )
    return Settings(computer_control=cc, remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-sftp-test", user_id="u1", tier=Tier.ADMIN.value,
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


class TestSFTPManageMetadata:
    def test_name(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.name == "sftp.manage"

    def test_category(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.tier == Tier.ADMIN


class TestSFTPManageApproval:
    def test_upload_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="upload", connection_id="x",
                              local_path="/tmp/f", remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is True

    def test_delete_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="delete", connection_id="x",
                              remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is True

    def test_list_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy")
        assert tool.needs_approval(params) is False

    def test_stat_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="stat", connection_id="x",
                              remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is False

    def test_small_download_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(sftp_approval_threshold=1000)
        params = _make_params(action="download", connection_id="x",
                              remote_path="/home/deploy/small.txt",
                              local_path="/tmp/test-read/write/small.txt",
                              file_size=500)
        assert tool.needs_approval(params) is False

    def test_large_download_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(sftp_approval_threshold=1000)
        params = _make_params(action="download", connection_id="x",
                              remote_path="/home/deploy/big.tar",
                              local_path="/tmp/test-read/write/big.tar",
                              file_size=1500)
        assert tool.needs_approval(params) is True


class TestSFTPManageValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="hack", connection_id="x")
        with pytest.raises(ValueError, match="Invalid action"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_relative_remote_path_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="../../etc/passwd")
        with pytest.raises(ValueError, match="absolute"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_remote_path_outside_allowed_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/etc/shadow")
        with pytest.raises(ValueError, match="not within"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_path_traversal_normalised(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy/../../../etc/passwd")
        with pytest.raises(ValueError, match="not within"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_connection_id_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", remote_path="/home/deploy")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)


class TestSFTPManageExecute:
    @pytest.mark.asyncio
    async def test_list_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()

        mock_entry = MagicMock()
        mock_entry.filename = "test.txt"
        mock_entry.attrs.size = 1024
        mock_entry.attrs.mtime = 1700000000
        mock_entry.attrs.permissions = 0o644
        mock_sftp.readdir = AsyncMock(return_value=[mock_entry])
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id=cid,
                              remote_path="/home/deploy")
        result = await tool.execute(params)

        assert result.success is True
        assert len(result.data["entries"]) == 1

    @pytest.mark.asyncio
    async def test_stat_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()

        mock_attrs = MagicMock()
        mock_attrs.size = 2048
        mock_attrs.mtime = 1700000000
        mock_attrs.permissions = 0o644
        mock_attrs.uid = 1000
        mock_attrs.gid = 1000
        mock_sftp.stat = AsyncMock(return_value=mock_attrs)
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="stat", connection_id=cid,
                              remote_path="/home/deploy/file.txt")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["size"] == 2048

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()
        mock_sftp.remove = AsyncMock()
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="delete", connection_id=cid,
                              remote_path="/home/deploy/old.log")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["deleted"] is True
        mock_sftp.remove.assert_called_once()


class TestSFTPManageParamsSummary:
    def test_summary_has_paths(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        params = _make_params(action="upload", connection_id="x",
                              local_path="/tmp/f.txt",
                              remote_path="/home/deploy/f.txt")
        summary = tool.get_params_summary(params)
        assert summary["local_path"] == "/tmp/f.txt"
        assert summary["remote_path"] == "/home/deploy/f.txt"
