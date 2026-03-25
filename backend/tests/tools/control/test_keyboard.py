"""Tests for KeyboardControlTool — type, shortcut, key_press."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from nobla.config.settings import ComputerControlSettings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.control.safety import InputSafetyGuard, ToolExecutionError
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-kb-test", user_id="u1", tier=Tier.ELEVATED.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset_guard():
    """Reset safety guard and module-level settings cache before each test."""
    InputSafetyGuard.reset()
    import nobla.tools.control.keyboard as mod
    mod._settings_cache = None
    yield
    InputSafetyGuard.reset()
    mod._settings_cache = None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestKeyboardMetadata:
    def test_name(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        assert tool.name == "keyboard.control"

    def test_category(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        assert tool.category == ToolCategory.INPUT

    def test_tier(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        assert tool.tier == Tier.ELEVATED

    def test_requires_approval_default_false(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestKeyboardValidation:
    @pytest.mark.asyncio
    async def test_valid_type(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hello world")
        await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_type_empty_text(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="")
        with pytest.raises(ValueError, match="[Tt]ext.*empty|[Ee]mpty.*text|non-empty"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_type_missing_text(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type")
        with pytest.raises(ValueError, match="[Tt]ext.*empty|[Ee]mpty.*text|non-empty"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_blocked_shortcut(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "alt", "delete"])
        with pytest.raises(ValueError, match="[Bb]locked"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_blocked_shortcut_case_insensitive(self):
        """Blocking works regardless of case: Ctrl+Alt+Delete == ctrl+alt+delete."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["Ctrl", "Alt", "Delete"])
        with pytest.raises(ValueError, match="[Bb]locked"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_blocked_shortcut_order_insensitive(self):
        """Blocking works regardless of key order: delete+ctrl+alt == ctrl+alt+delete."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["delete", "ctrl", "alt"])
        with pytest.raises(ValueError, match="[Bb]locked"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_allowed_shortcut_passes(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "c"])
        await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_shortcut_missing_keys(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut")
        with pytest.raises(ValueError, match="[Kk]eys.*list|[Ll]ist"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_shortcut_keys_not_a_list(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys="ctrl+c")
        with pytest.raises(ValueError, match="[Kk]eys.*list|[Ll]ist"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_valid_key_press(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="enter")
        await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_key_press_missing_key(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press")
        with pytest.raises(ValueError, match="[Kk]ey.*required|[Rr]equired.*key|must.*provide"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="swipe")
        with pytest.raises(ValueError, match="Invalid action"):
            await tool.validate(params)


# ---------------------------------------------------------------------------
# Approval (conditional)
# ---------------------------------------------------------------------------


class TestKeyboardApproval:
    def test_type_no_approval(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hello")
        assert tool.needs_approval(params) is False

    def test_key_press_no_approval(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="enter")
        assert tool.needs_approval(params) is False

    def test_shortcut_requires_approval(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "c"])
        assert tool.needs_approval(params) is True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestKeyboardExecution:
    @pytest.mark.asyncio
    async def test_execute_type_short(self, mock_pyautogui, control_settings):
        """Short text (< chunk_size) should result in a single write() call."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hello")
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch("nobla.tools.control.keyboard.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "type"
        mock_pyautogui.write.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_execute_type_long_chunked(self, mock_pyautogui, control_settings):
        """Text longer than chunk_size should be split into multiple write() calls."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        # control_settings has type_chunk_size=50 by default
        long_text = "a" * 120  # 120 chars, should be 3 chunks (50+50+20)
        params = _make_params(action="type", text=long_text)
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch("nobla.tools.control.keyboard.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "type"
        assert result.data["chunks"] == 3
        assert mock_pyautogui.write.call_count == 3
        # Verify chunk content
        calls = mock_pyautogui.write.call_args_list
        assert calls[0] == call("a" * 50)
        assert calls[1] == call("a" * 50)
        assert calls[2] == call("a" * 20)

    @pytest.mark.asyncio
    async def test_execute_shortcut(self, mock_pyautogui, control_settings):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "c"])
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch("nobla.tools.control.keyboard.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "shortcut"
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")

    @pytest.mark.asyncio
    async def test_execute_key_press(self, mock_pyautogui, control_settings):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="enter")
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch("nobla.tools.control.keyboard.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "key_press"
        assert result.data["key"] == "enter"
        mock_pyautogui.press.assert_called_once_with("enter")

    @pytest.mark.asyncio
    async def test_halt_between_type_chunks(self, mock_pyautogui, control_settings):
        """Safety guard is checked between type chunks; halt mid-type returns failure."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        long_text = "a" * 120
        params = _make_params(action="type", text=long_text)
        call_count = 0

        def check_side_effect(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise ToolExecutionError("halted mid-type")

        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch(
                "nobla.tools.control.keyboard.InputSafetyGuard.check",
                side_effect=check_side_effect,
            ),
        ):
            result = await tool.execute(params)
        assert result.success is False
        assert "halted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_safety_guard_halted(self, mock_pyautogui, control_settings):
        """If guard is halted before execution, returns failure immediately."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hello")
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch(
                "nobla.tools.control.keyboard.InputSafetyGuard.check",
                side_effect=ToolExecutionError("halted"),
            ),
        ):
            result = await tool.execute(params)
        assert result.success is False
        assert "halted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_failsafe_caught(self, mock_pyautogui, control_settings):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="enter")
        mock_pyautogui.press.side_effect = mock_pyautogui.FailSafeException("triggered")
        with (
            patch("nobla.tools.control.keyboard._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.keyboard._get_settings", return_value=control_settings),
            patch("nobla.tools.control.keyboard.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is False
        assert "fail-safe" in result.error.lower() or "failsafe" in result.error.lower()


# ---------------------------------------------------------------------------
# describe_action / get_params_summary
# ---------------------------------------------------------------------------


class TestKeyboardDescribe:
    def test_describe_type(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hello world")
        desc = tool.describe_action(params)
        assert "type" in desc.lower()
        assert "hello world" in desc

    def test_describe_shortcut(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "c"])
        desc = tool.describe_action(params)
        assert "shortcut" in desc.lower()

    def test_describe_key_press(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="enter")
        desc = tool.describe_action(params)
        assert "enter" in desc.lower()

    def test_params_summary_type_truncated(self):
        """Text longer than 100 chars should be truncated in summary."""
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        long_text = "x" * 200
        params = _make_params(action="type", text=long_text)
        summary = tool.get_params_summary(params)
        assert summary["action"] == "type"
        assert len(summary["text"]) <= 103  # 100 chars + "..."
        assert summary["text"].endswith("...")

    def test_params_summary_type_short_not_truncated(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="type", text="hi")
        summary = tool.get_params_summary(params)
        assert summary["text"] == "hi"

    def test_params_summary_shortcut(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="shortcut", keys=["ctrl", "v"])
        summary = tool.get_params_summary(params)
        assert summary["action"] == "shortcut"
        assert summary["keys"] == ["ctrl", "v"]

    def test_params_summary_key_press(self):
        from nobla.tools.control.keyboard import KeyboardControlTool
        tool = KeyboardControlTool()
        params = _make_params(action="key_press", key="tab")
        summary = tool.get_params_summary(params)
        assert summary["action"] == "key_press"
        assert summary["key"] == "tab"
