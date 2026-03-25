"""Tests for ClipboardManageTool -- read, write, clear with audit sanitization."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from nobla.config.settings import ComputerControlSettings
from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolCategory, ToolParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _params(args: dict) -> ToolParams:
    return ToolParams(args=args, connection_state=ConnectionState())


def _make_tool(settings: ComputerControlSettings | None = None):
    """Create a fresh ClipboardManageTool with injected settings."""
    from nobla.tools.control.clipboard import ClipboardManageTool

    tool = ClipboardManageTool()
    if settings is not None:
        tool._settings_override = settings
    return tool


def _clip_settings(
    max_clipboard_size: int = 1_048_576,
    audit_clipboard_preview_length: int = 50,
) -> ComputerControlSettings:
    """Build ComputerControlSettings with clipboard-relevant fields."""
    return ComputerControlSettings(
        max_clipboard_size=max_clipboard_size,
        audit_clipboard_preview_length=audit_clipboard_preview_length,
    )


# ===================================================================
# Validation tests
# ===================================================================


class TestValidation:
    """Validate action names and content size limits."""

    def test_valid_read(self):
        """Read action should pass validation."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "read"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_valid_write(self):
        """Write action with content should pass validation."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "write", "content": "hello"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_valid_clear(self):
        """Clear action should pass validation."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "clear"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_invalid_action(self):
        """An unknown action must raise ValueError."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "paste"})
        with pytest.raises(ValueError, match="Invalid action"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_write_exceeds_max_size(self):
        """Write with content exceeding max_clipboard_size must raise ValueError."""
        tool = _make_tool(_clip_settings(max_clipboard_size=10))
        params = _params({"action": "write", "content": "x" * 20})
        with pytest.raises(ValueError, match="exceeds maximum"):
            asyncio.get_event_loop().run_until_complete(tool.validate(params))

    def test_write_at_max_size_passes(self):
        """Write with content exactly at max_clipboard_size should pass."""
        tool = _make_tool(_clip_settings(max_clipboard_size=5))
        params = _params({"action": "write", "content": "abcde"})
        asyncio.get_event_loop().run_until_complete(tool.validate(params))


# ===================================================================
# Execution tests
# ===================================================================


class TestExecution:
    """Test read, write, clear actions via mocked backends."""

    @pytest.mark.asyncio
    async def test_read_returns_content(self, mock_pyperclip):
        """Read should return the clipboard content via pyperclip.paste()."""
        tool = _make_tool(_clip_settings())

        with patch(
            "nobla.tools.control.clipboard._get_clipboard_backend",
            return_value=mock_pyperclip,
        ):
            params = _params({"action": "read"})
            result = await tool.execute(params)

        assert result.success is True
        assert result.data["content"] == "test clipboard content"
        mock_pyperclip.paste.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_calls_copy(self, mock_pyperclip):
        """Write should call backend.copy(content)."""
        tool = _make_tool(_clip_settings())

        with patch(
            "nobla.tools.control.clipboard._get_clipboard_backend",
            return_value=mock_pyperclip,
        ):
            params = _params({"action": "write", "content": "new text"})
            result = await tool.execute(params)

        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("new text")

    @pytest.mark.asyncio
    async def test_clear_calls_copy_empty(self, mock_pyperclip):
        """Clear should call backend.copy(\"\")."""
        tool = _make_tool(_clip_settings())

        with patch(
            "nobla.tools.control.clipboard._get_clipboard_backend",
            return_value=mock_pyperclip,
        ):
            params = _params({"action": "clear"})
            result = await tool.execute(params)

        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_read_backend_error(self, mock_pyperclip):
        """Read should return error result when backend raises."""
        tool = _make_tool(_clip_settings())
        mock_pyperclip.paste.side_effect = RuntimeError("clipboard unavailable")

        with patch(
            "nobla.tools.control.clipboard._get_clipboard_backend",
            return_value=mock_pyperclip,
        ):
            params = _params({"action": "read"})
            result = await tool.execute(params)

        assert result.success is False
        assert "clipboard unavailable" in result.error


# ===================================================================
# Approval tests
# ===================================================================


class TestApproval:
    """Verify conditional approval based on action type."""

    def test_read_no_approval(self):
        """Read action should NOT require approval."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "read"})
        assert tool.needs_approval(params) is False

    def test_write_needs_approval(self):
        """Write action should require approval."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "write", "content": "data"})
        assert tool.needs_approval(params) is True

    def test_clear_needs_approval(self):
        """Clear action should require approval."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "clear"})
        assert tool.needs_approval(params) is True


# ===================================================================
# Audit / params summary tests
# ===================================================================


class TestAuditSummary:
    """get_params_summary should truncate content for audit logs."""

    def test_short_content_not_truncated(self):
        """Content shorter than preview length should appear in full."""
        tool = _make_tool(_clip_settings(audit_clipboard_preview_length=50))
        params = _params({"action": "write", "content": "short"})
        summary = tool.get_params_summary(params)
        assert summary["action"] == "write"
        assert summary["content_preview"] == "short"

    def test_long_content_truncated(self):
        """Content longer than preview length should be truncated with ellipsis."""
        tool = _make_tool(_clip_settings(audit_clipboard_preview_length=10))
        params = _params({"action": "write", "content": "abcdefghijklmnop"})
        summary = tool.get_params_summary(params)
        assert summary["content_preview"] == "abcdefghij..."
        assert len(summary["content_preview"]) == 13  # 10 + len("...")

    def test_read_has_no_content_in_summary(self):
        """Read action summary should not include content_preview."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "read"})
        summary = tool.get_params_summary(params)
        assert summary["action"] == "read"
        assert "content_preview" not in summary

    def test_clear_has_no_content_in_summary(self):
        """Clear action summary should not include content_preview."""
        tool = _make_tool(_clip_settings())
        params = _params({"action": "clear"})
        summary = tool.get_params_summary(params)
        assert summary["action"] == "clear"
        assert "content_preview" not in summary


# ===================================================================
# Backend degradation tests
# ===================================================================


class TestBackendDegradation:
    """Both backends unavailable should give a clear error."""

    def test_no_backends_raises(self):
        """When neither pyperclip nor pyautogui is available, raise ToolExecutionError."""
        from nobla.tools.control.safety import ToolExecutionError

        with patch.dict("sys.modules", {"pyperclip": None, "pyautogui": None}):
            from nobla.tools.control import clipboard as cb_mod

            # Force re-evaluation by calling the function directly
            with pytest.raises(ToolExecutionError, match="No clipboard backend"):
                cb_mod._get_clipboard_backend()

    def test_pyperclip_primary(self):
        """When pyperclip is available, it should be used as the primary backend."""
        mock_pp = MagicMock()
        mock_pp.copy = MagicMock()
        mock_pp.paste = MagicMock()

        with patch.dict("sys.modules", {"pyperclip": mock_pp}):
            from nobla.tools.control import clipboard as cb_mod
            backend = cb_mod._get_clipboard_backend()

        assert backend is mock_pp

    def test_pyautogui_fallback(self):
        """When pyperclip is unavailable, pyautogui should be the fallback."""
        mock_pag = MagicMock()
        mock_pag.copy = MagicMock()
        mock_pag.paste = MagicMock()

        with patch.dict("sys.modules", {"pyperclip": None, "pyautogui": mock_pag}):
            from nobla.tools.control import clipboard as cb_mod
            backend = cb_mod._get_clipboard_backend()

        # pyautogui doesn't have copy/paste natively -- the wrapper should adapt
        assert backend is not None


# ===================================================================
# Metadata tests
# ===================================================================


class TestMetadata:
    """Tool metadata constants."""

    def test_tool_name(self):
        tool = _make_tool(_clip_settings())
        assert tool.name == "clipboard.manage"

    def test_tool_category(self):
        tool = _make_tool(_clip_settings())
        assert tool.category == ToolCategory.CLIPBOARD

    def test_describe_read(self):
        tool = _make_tool(_clip_settings())
        params = _params({"action": "read"})
        desc = tool.describe_action(params)
        assert "read" in desc.lower()

    def test_describe_write(self):
        tool = _make_tool(_clip_settings())
        params = _params({"action": "write", "content": "data"})
        desc = tool.describe_action(params)
        assert "write" in desc.lower()

    def test_describe_clear(self):
        tool = _make_tool(_clip_settings())
        params = _params({"action": "clear"})
        desc = tool.describe_action(params)
        assert "clear" in desc.lower()
