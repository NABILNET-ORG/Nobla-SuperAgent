"""MouseControlTool — compound tool with move, click, double_click, drag, scroll."""
from __future__ import annotations

import asyncio
import math

from nobla.config.settings import ComputerControlSettings, Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.control.safety import InputSafetyGuard, ToolExecutionError
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_ACTIONS = {"move", "click", "double_click", "drag", "scroll"}
_VALID_BUTTONS = {"left", "right", "middle"}
_APPROVAL_ACTIONS = {"drag"}

# Lazy settings cache -- avoids re-reading config on every call.
_settings_cache: ComputerControlSettings | None = None

_DRAG_CHUNK_PX = 20


def _get_settings() -> ComputerControlSettings:
    """Return (and cache) the ComputerControlSettings singleton."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_pyautogui():
    """Lazy-import pyautogui; raise ToolExecutionError if unavailable."""
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        raise ToolExecutionError(
            "pyautogui is not installed. "
            "Install it with: pip install pyautogui"
        )


def _validate_coords(x: int, y: int, screen_w: int, screen_h: int) -> None:
    """Raise ValueError if (x, y) is outside screen bounds."""
    if x < 0 or y < 0 or x >= screen_w or y >= screen_h:
        raise ValueError(
            f"Coordinates ({x}, {y}) out of bounds for screen "
            f"{screen_w}x{screen_h}"
        )


@register_tool
class MouseControlTool(BaseTool):
    """Control the mouse: move, click, double-click, drag, scroll."""

    name = "mouse.control"
    description = "Control mouse: move, click, double-click, drag, scroll"
    category = ToolCategory.INPUT
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional -- overridden by needs_approval()

    def needs_approval(self, params: ToolParams) -> bool:
        """Only drag actions require user approval."""
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def validate(self, params: ToolParams) -> None:
        """Validate action, coordinates, button, and duration."""
        args = params.args
        action = args.get("action", "")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
            )

        pag = _get_pyautogui()
        screen_w, screen_h = pag.size()

        # Validate coordinates for actions that need them
        if action in ("move", "click", "double_click", "drag"):
            x = args.get("x", 0)
            y = args.get("y", 0)
            _validate_coords(x, y, screen_w, screen_h)

        # scroll with x/y is optional -- validate only if provided
        if action == "scroll" and "x" in args and "y" in args:
            _validate_coords(args["x"], args["y"], screen_w, screen_h)

        # Validate button for click actions
        if action in ("click", "double_click"):
            button = args.get("button", "left")
            if button not in _VALID_BUTTONS:
                raise ValueError(
                    f"Invalid button '{button}'. Valid: {sorted(_VALID_BUTTONS)}"
                )

        # Validate duration
        duration = args.get("duration", 0.0)
        if duration < 0:
            raise ValueError(
                f"duration must be >= 0, got {duration}"
            )

        # Validate drag end coordinates
        if action == "drag":
            if "end_x" not in args or "end_y" not in args:
                raise ValueError("Drag requires end_x and end_y coordinates")
            _validate_coords(args["end_x"], args["end_y"], screen_w, screen_h)

    async def execute(self, params: ToolParams) -> ToolResult:
        """Execute the mouse action via pyautogui (in a thread)."""
        pag = _get_pyautogui()
        settings = _get_settings()
        args = params.args
        action = args["action"]

        try:
            InputSafetyGuard.check("mouse", settings)
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        try:
            data = await asyncio.to_thread(
                self._execute_action, pag, action, args, settings,
            )
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            # Catch pyautogui.FailSafeException and any other errors
            exc_name = type(exc).__name__
            if "FailSafe" in exc_name:
                return ToolResult(
                    success=False, data={},
                    error=f"PyAutoGUI fail-safe triggered: {exc}",
                )
            return ToolResult(success=False, data={}, error=str(exc))

        return ToolResult(success=True, data=data)

    def _execute_action(
        self,
        pag,
        action: str,
        args: dict,
        settings: ComputerControlSettings,
    ) -> dict:
        """Synchronous action dispatch -- runs inside asyncio.to_thread."""
        if action == "move":
            x, y = args["x"], args["y"]
            duration = args.get("duration", 0.0)
            pag.moveTo(x, y, duration=duration)
            return {"action": "move", "x": x, "y": y, "duration": duration}

        if action == "click":
            x, y = args["x"], args["y"]
            button = args.get("button", "left")
            pag.click(x, y, button=button)
            return {"action": "click", "x": x, "y": y, "button": button}

        if action == "double_click":
            x, y = args["x"], args["y"]
            button = args.get("button", "left")
            pag.doubleClick(x, y, button=button)
            return {"action": "double_click", "x": x, "y": y, "button": button}

        if action == "scroll":
            clicks = args.get("clicks", 3)
            if "x" in args and "y" in args:
                pag.scroll(clicks, x=args["x"], y=args["y"])
                return {
                    "action": "scroll", "clicks": clicks,
                    "x": args["x"], "y": args["y"],
                }
            pag.scroll(clicks)
            return {"action": "scroll", "clicks": clicks}

        if action == "drag":
            return self._execute_drag(pag, args, settings)

        return {"action": action, "error": "unknown action"}

    def _execute_drag(
        self,
        pag,
        args: dict,
        settings: ComputerControlSettings,
    ) -> dict:
        """Chunked drag in 20px increments with halt checks between steps."""
        start_x, start_y = args["x"], args["y"]
        end_x, end_y = args["end_x"], args["end_y"]
        duration = args.get("duration", 0.5)

        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.hypot(dx, dy)

        if distance == 0:
            return {
                "action": "drag",
                "start": (start_x, start_y),
                "end": (end_x, end_y),
                "chunks": 0,
            }

        num_chunks = max(1, int(distance / _DRAG_CHUNK_PX))
        chunk_duration = duration / num_chunks
        step_x = dx / num_chunks
        step_y = dy / num_chunks

        # Move to start position
        pag.moveTo(start_x, start_y, duration=0)
        pag.mouseDown()

        try:
            for i in range(num_chunks):
                # Halt check between chunks
                InputSafetyGuard.check("mouse", settings)
                target_x = int(start_x + step_x * (i + 1))
                target_y = int(start_y + step_y * (i + 1))
                pag.moveTo(target_x, target_y, duration=chunk_duration)
        except ToolExecutionError:
            pag.mouseUp()
            raise
        finally:
            pag.mouseUp()

        return {
            "action": "drag",
            "start": (start_x, start_y),
            "end": (end_x, end_y),
            "chunks": num_chunks,
        }

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        args = params.args
        action = args.get("action", "unknown")

        if action == "move":
            return f"Move mouse to ({args.get('x')}, {args.get('y')})"

        if action == "click":
            button = args.get("button", "left")
            return f"Click {button} at ({args.get('x')}, {args.get('y')})"

        if action == "double_click":
            button = args.get("button", "left")
            return f"Double-click {button} at ({args.get('x')}, {args.get('y')})"

        if action == "scroll":
            clicks = args.get("clicks", 0)
            direction = "up" if clicks > 0 else "down"
            return f"Scroll {direction} {abs(clicks)} clicks"

        if action == "drag":
            return (
                f"Drag from ({args.get('x')}, {args.get('y')}) "
                f"to ({args.get('end_x')}, {args.get('end_y')})"
            )

        return f"Mouse {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display -- exposes only safe fields."""
        args = params.args
        summary: dict = {"action": args.get("action", "")}

        if "x" in args:
            summary["x"] = args["x"]
        if "y" in args:
            summary["y"] = args["y"]
        if "button" in args:
            summary["button"] = args["button"]
        if "clicks" in args:
            summary["clicks"] = args["clicks"]
        if "duration" in args:
            summary["duration"] = args["duration"]
        if "end_x" in args:
            summary["end_x"] = args["end_x"]
        if "end_y" in args:
            summary["end_y"] = args["end_y"]

        return summary
