"""Tests for MouseControlTool — move, click, double_click, drag, scroll."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        connection_id="conn-mouse-test", user_id="u1", tier=Tier.ELEVATED.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset_guard():
    """Reset safety guard and module-level settings cache before each test."""
    InputSafetyGuard.reset()
    import nobla.tools.control.mouse as mod
    mod._settings_cache = None
    yield
    InputSafetyGuard.reset()
    mod._settings_cache = None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMouseMetadata:
    def test_name(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        assert tool.name == "mouse.control"

    def test_category(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        assert tool.category == ToolCategory.INPUT

    def test_tier(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        assert tool.tier == Tier.ELEVATED

    def test_requires_approval_default_false(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        assert tool.requires_approval is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestMouseValidation:
    @pytest.mark.asyncio
    async def test_valid_move(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=100, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            await tool.validate(params)  # should not raise

    @pytest.mark.asyncio
    async def test_invalid_action(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="teleport", x=100, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="Invalid action"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_action(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(x=100, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="Invalid action"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_coords_out_of_bounds_x(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=2000, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="out of bounds"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_coords_out_of_bounds_y(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=100, y=1200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="out of bounds"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_negative_coords(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=-10, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="out of bounds"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_button(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200, button="back")
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="Invalid button"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_negative_duration(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=100, y=200, duration=-1.0)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="duration"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_drag_requires_end_coords(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="drag", x=100, y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="end_x.*end_y"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_drag_end_coords_out_of_bounds(self, mock_pyautogui):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="drag", x=100, y=200, end_x=2000, end_y=200)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            with pytest.raises(ValueError, match="out of bounds"):
                await tool.validate(params)

    @pytest.mark.asyncio
    async def test_scroll_no_coords_ok(self, mock_pyautogui):
        """scroll can work without x/y (scrolls at current position)."""
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="scroll", clicks=3)
        with patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui):
            await tool.validate(params)  # should not raise


# ---------------------------------------------------------------------------
# Approval (conditional)
# ---------------------------------------------------------------------------


class TestMouseApproval:
    def test_move_no_approval(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=100, y=200)
        assert tool.needs_approval(params) is False

    def test_click_no_approval(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200)
        assert tool.needs_approval(params) is False

    def test_double_click_no_approval(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="double_click", x=100, y=200)
        assert tool.needs_approval(params) is False

    def test_scroll_no_approval(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="scroll", clicks=3)
        assert tool.needs_approval(params) is False

    def test_drag_requires_approval(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="drag", x=100, y=200, end_x=300, end_y=400)
        assert tool.needs_approval(params) is True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestMouseExecution:
    @pytest.mark.asyncio
    async def test_execute_move(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=500, y=300, duration=0.1)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "move"
        mock_pyautogui.moveTo.assert_called_once_with(500, 300, duration=0.1)

    @pytest.mark.asyncio
    async def test_execute_click_default_left(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "click"
        mock_pyautogui.click.assert_called_once_with(100, 200, button="left")

    @pytest.mark.asyncio
    async def test_execute_click_right(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200, button="right")
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(100, 200, button="right")

    @pytest.mark.asyncio
    async def test_execute_double_click(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="double_click", x=400, y=500)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "double_click"
        mock_pyautogui.doubleClick.assert_called_once_with(400, 500, button="left")

    @pytest.mark.asyncio
    async def test_execute_scroll(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="scroll", clicks=5)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "scroll"
        mock_pyautogui.scroll.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_scroll_at_position(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="scroll", clicks=-3, x=200, y=300)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        mock_pyautogui.scroll.assert_called_once_with(-3, x=200, y=300)

    @pytest.mark.asyncio
    async def test_execute_drag(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(
            action="drag", x=100, y=200, end_x=120, end_y=220, duration=0.5,
        )
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is True
        assert result.data["action"] == "drag"
        # moveTo called first, then one or more moveRel for chunked drag
        assert mock_pyautogui.moveTo.called

    @pytest.mark.asyncio
    async def test_failsafe_caught(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200)
        mock_pyautogui.click.side_effect = mock_pyautogui.FailSafeException("Fail-safe triggered")
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch("nobla.tools.control.mouse.InputSafetyGuard") as mock_guard,
        ):
            mock_guard.check = MagicMock()
            result = await tool.execute(params)
        assert result.success is False
        assert "fail-safe" in result.error.lower() or "failsafe" in result.error.lower()

    @pytest.mark.asyncio
    async def test_safety_guard_halted(self, mock_pyautogui, control_settings):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200)
        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch(
                "nobla.tools.control.mouse.InputSafetyGuard.check",
                side_effect=ToolExecutionError("halted"),
            ),
        ):
            result = await tool.execute(params)
        assert result.success is False
        assert "halted" in result.error.lower()

    @pytest.mark.asyncio
    async def test_drag_halt_mid_chunk(self, mock_pyautogui, control_settings):
        """If safety guard raises mid-drag, the tool returns failure."""
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(
            action="drag", x=100, y=100, end_x=200, end_y=200, duration=0.5,
        )
        call_count = 0

        def check_side_effect(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise ToolExecutionError("halted mid-drag")

        with (
            patch("nobla.tools.control.mouse._get_pyautogui", return_value=mock_pyautogui),
            patch("nobla.tools.control.mouse._get_settings", return_value=control_settings),
            patch(
                "nobla.tools.control.mouse.InputSafetyGuard.check",
                side_effect=check_side_effect,
            ),
        ):
            result = await tool.execute(params)
        assert result.success is False
        assert "halted" in result.error.lower()


# ---------------------------------------------------------------------------
# describe_action / get_params_summary
# ---------------------------------------------------------------------------


class TestMouseDescribe:
    def test_describe_move(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="move", x=100, y=200)
        desc = tool.describe_action(params)
        assert "move" in desc.lower()
        assert "100" in desc
        assert "200" in desc

    def test_describe_click(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=50, y=75, button="right")
        desc = tool.describe_action(params)
        assert "click" in desc.lower()
        assert "right" in desc.lower()

    def test_describe_drag(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="drag", x=10, y=20, end_x=30, end_y=40)
        desc = tool.describe_action(params)
        assert "drag" in desc.lower()

    def test_describe_scroll(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="scroll", clicks=5)
        desc = tool.describe_action(params)
        assert "scroll" in desc.lower()

    def test_params_summary_includes_action(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="click", x=100, y=200, button="left")
        summary = tool.get_params_summary(params)
        assert summary["action"] == "click"
        assert summary["x"] == 100
        assert summary["y"] == 200

    def test_params_summary_drag(self):
        from nobla.tools.control.mouse import MouseControlTool
        tool = MouseControlTool()
        params = _make_params(action="drag", x=10, y=20, end_x=30, end_y=40)
        summary = tool.get_params_summary(params)
        assert summary["action"] == "drag"
        assert "end_x" in summary
        assert "end_y" in summary
