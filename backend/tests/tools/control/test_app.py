"""Tests for AppControlTool — allow-list, PID tracking, conditional approval."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from nobla.config.settings import ComputerControlSettings
from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _params(args: dict) -> ToolParams:
    return ToolParams(args=args, connection_state=ConnectionState())


def _make_tool(settings: ComputerControlSettings | None = None):
    """Create a fresh AppControlTool with injected settings."""
    from nobla.tools.control.app import AppControlTool, _launched_pids

    # Clear module-level PID registry between tests
    _launched_pids.clear()

    tool = AppControlTool()
    if settings is not None:
        tool._settings_override = settings
    return tool


def _app_settings(
    allowed_apps: list[str] | None = None,
) -> ComputerControlSettings:
    """Build a ComputerControlSettings with an allowed_apps list."""
    return ComputerControlSettings(
        allowed_apps=["notepad", "chrome", "code"] if allowed_apps is None else allowed_apps,
    )


# ===================================================================
# Validation tests
# ===================================================================


class TestValidation:
    """Validate action names and allow-list checks."""

    def test_valid_launch(self):
        """Launch of an allowed app should pass validation."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "notepad"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_app_not_in_allowed(self):
        """Launching an app not in allowed_apps must raise ValueError."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "malware"})
        with pytest.raises(ValueError, match="not in allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_case_insensitive_allowed(self):
        """Allow-list check should be case-insensitive."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "Notepad"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_case_insensitive_mixed_case(self):
        """Allow-list check works for upper-case allowed and lower-case input."""
        settings = _app_settings(allowed_apps=["Chrome", "VSCode"])
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "chrome"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    @pytest.mark.asyncio
    async def test_empty_allowed_apps_raises(self):
        """Empty allowed_apps should raise ValueError with config hint."""
        settings = _app_settings(allowed_apps=[])
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "notepad"})
        with pytest.raises(ValueError, match="allowed_apps"):
            await tool.validate(params)

    def test_invalid_action(self):
        """An unknown action must raise ValueError."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "uninstall", "app_name": "notepad"})
        with pytest.raises(ValueError, match="Invalid action"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_close_validates_app_name(self):
        """Close action also validates app_name against allow-list."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "close", "app_name": "malware"})
        with pytest.raises(ValueError, match="not in allowed"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_list_no_app_name_required(self):
        """List action should pass validation without app_name."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "list"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_switch_validates_title(self):
        """Switch action should require a window title."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "switch"})
        with pytest.raises(ValueError, match="title"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_switch_with_title_passes(self):
        """Switch action with title should pass validation."""
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "switch", "title": "Untitled - Notepad"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))


# ===================================================================
# Execution tests
# ===================================================================


class TestExecution:
    """Test launch, close, list, switch actions."""

    @pytest.mark.asyncio
    async def test_launch_tracks_pid(self):
        """Launching an app should track the process in _launched_pids."""
        from nobla.tools.control.app import _launched_pids

        settings = _app_settings()
        tool = _make_tool(settings)

        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_proc.poll.return_value = None  # process is running

        with patch("nobla.tools.control.app._launch_app", return_value=mock_proc):
            params = _params({"action": "launch", "app_name": "notepad"})
            result = await tool.execute(params)

        assert result.success is True
        assert result.data["pid"] == 42
        assert "notepad" in _launched_pids

    @pytest.mark.asyncio
    async def test_close_nobla_launched(self):
        """Closing an app that Nobla launched should succeed."""
        from nobla.tools.control.app import _launched_pids

        settings = _app_settings()
        tool = _make_tool(settings)

        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_proc.poll.return_value = None  # still running
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        _launched_pids["notepad"] = mock_proc

        params = _params({"action": "close", "app_name": "notepad"})
        result = await tool.execute(params)

        assert result.success is True
        mock_proc.terminate.assert_called_once()
        assert "notepad" not in _launched_pids

    @pytest.mark.asyncio
    async def test_close_non_launched_denied(self):
        """Closing an app that Nobla did NOT launch must fail."""
        settings = _app_settings()
        tool = _make_tool(settings)

        params = _params({"action": "close", "app_name": "notepad"})
        result = await tool.execute(params)

        assert result.success is False
        assert "not launched by nobla" in result.error.lower()

    @pytest.mark.asyncio
    async def test_close_stale_pid(self):
        """If tracked process already exited, close should clean up and report."""
        from nobla.tools.control.app import _launched_pids

        settings = _app_settings()
        tool = _make_tool(settings)

        mock_proc = MagicMock()
        mock_proc.pid = 101
        mock_proc.poll.return_value = 0  # already exited
        _launched_pids["notepad"] = mock_proc

        params = _params({"action": "close", "app_name": "notepad"})
        result = await tool.execute(params)

        assert result.success is True
        assert "already exited" in result.data.get("status", "").lower()
        assert "notepad" not in _launched_pids

    @pytest.mark.asyncio
    async def test_list_with_psutil(self, mock_psutil):
        """List action should return running processes via psutil."""
        settings = _app_settings()
        tool = _make_tool(settings)

        with patch("nobla.tools.control.app._get_psutil", return_value=mock_psutil):
            params = _params({"action": "list"})
            result = await tool.execute(params)

        assert result.success is True
        procs = result.data["processes"]
        assert len(procs) >= 1
        assert procs[0]["name"] == "notepad.exe"

    @pytest.mark.asyncio
    async def test_list_fallback_subprocess(self):
        """List should fall back to subprocess when psutil unavailable."""
        settings = _app_settings()
        tool = _make_tool(settings)

        def _no_psutil():
            raise ImportError("no psutil")

        mock_output = "  PID  Name\n  123  notepad.exe\n"
        with patch("nobla.tools.control.app._get_psutil", side_effect=ImportError):
            with patch(
                "nobla.tools.control.app._list_via_subprocess",
                return_value=[{"name": "notepad.exe", "pid": 123}],
            ):
                params = _params({"action": "list"})
                result = await tool.execute(params)

        assert result.success is True
        assert len(result.data["processes"]) >= 1

    @pytest.mark.asyncio
    async def test_switch_window(self):
        """Switch action should call the platform focus helper."""
        settings = _app_settings()
        tool = _make_tool(settings)

        with patch(
            "nobla.tools.control.app._focus_window",
            return_value=True,
        ):
            params = _params({"action": "switch", "title": "Untitled - Notepad"})
            result = await tool.execute(params)

        assert result.success is True
        assert "untitled" in result.data.get("title", "").lower()

    @pytest.mark.asyncio
    async def test_switch_window_not_found(self):
        """Switch should report failure when window not found."""
        settings = _app_settings()
        tool = _make_tool(settings)

        with patch(
            "nobla.tools.control.app._focus_window",
            return_value=False,
        ):
            params = _params({"action": "switch", "title": "NonExistent Window"})
            result = await tool.execute(params)

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_launch_failure(self):
        """Launch should return error when subprocess fails."""
        settings = _app_settings()
        tool = _make_tool(settings)

        with patch(
            "nobla.tools.control.app._launch_app",
            side_effect=FileNotFoundError("notepad not found"),
        ):
            params = _params({"action": "launch", "app_name": "notepad"})
            result = await tool.execute(params)

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_launch_replaces_stale_entry(self):
        """Launching an app with stale PID should replace the old entry."""
        from nobla.tools.control.app import _launched_pids

        settings = _app_settings()
        tool = _make_tool(settings)

        # Stale process
        old_proc = MagicMock()
        old_proc.pid = 10
        old_proc.poll.return_value = 0  # already exited
        _launched_pids["notepad"] = old_proc

        new_proc = MagicMock()
        new_proc.pid = 50
        new_proc.poll.return_value = None

        with patch("nobla.tools.control.app._launch_app", return_value=new_proc):
            params = _params({"action": "launch", "app_name": "notepad"})
            result = await tool.execute(params)

        assert result.success is True
        assert _launched_pids["notepad"].pid == 50


# ===================================================================
# Approval tests
# ===================================================================


class TestApproval:
    """Verify conditional approval based on action type."""

    def test_list_no_approval(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "list"})
        assert tool.needs_approval(params) is False

    def test_switch_no_approval(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "switch", "title": "Window"})
        assert tool.needs_approval(params) is False

    def test_launch_needs_approval(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "notepad"})
        assert tool.needs_approval(params) is True

    def test_close_needs_approval(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "close", "app_name": "notepad"})
        assert tool.needs_approval(params) is True


# ===================================================================
# Metadata tests
# ===================================================================


class TestMetadata:
    """Tool metadata, describe_action, get_params_summary."""

    def test_tool_name(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        assert tool.name == "app.control"

    def test_tool_category(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        assert tool.category == ToolCategory.APP_CONTROL

    def test_describe_launch(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "notepad"})
        desc = tool.describe_action(params)
        assert "launch" in desc.lower()
        assert "notepad" in desc.lower()

    def test_describe_close(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "close", "app_name": "chrome"})
        desc = tool.describe_action(params)
        assert "close" in desc.lower()
        assert "chrome" in desc.lower()

    def test_describe_list(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "list"})
        desc = tool.describe_action(params)
        assert "list" in desc.lower()

    def test_describe_switch(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "switch", "title": "My Window"})
        desc = tool.describe_action(params)
        assert "switch" in desc.lower() or "focus" in desc.lower()

    def test_get_params_summary(self):
        settings = _app_settings()
        tool = _make_tool(settings)
        params = _params({"action": "launch", "app_name": "notepad"})
        summary = tool.get_params_summary(params)
        assert summary["action"] == "launch"
        assert summary["app_name"] == "notepad"
