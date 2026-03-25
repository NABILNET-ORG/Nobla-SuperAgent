"""KeyboardControlTool — compound tool with type, shortcut, key_press."""
from __future__ import annotations

import asyncio

from nobla.config.settings import ComputerControlSettings, Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.control.safety import (
    InputSafetyGuard,
    ToolExecutionError,
    _normalize_shortcut,
)
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_ACTIONS = {"type", "shortcut", "key_press"}
_APPROVAL_ACTIONS = {"shortcut"}

# Lazy settings cache -- avoids re-reading config on every call.
_settings_cache: ComputerControlSettings | None = None


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


@register_tool
class KeyboardControlTool(BaseTool):
    """Control the keyboard: type text, press shortcuts, press single keys."""

    name = "keyboard.control"
    description = "Control keyboard: type text, shortcuts, key presses"
    category = ToolCategory.INPUT
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional -- overridden by needs_approval()

    def needs_approval(self, params: ToolParams) -> bool:
        """Only shortcut actions require user approval."""
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def validate(self, params: ToolParams) -> None:
        """Validate action and action-specific parameters."""
        args = params.args
        action = args.get("action", "")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
            )

        if action == "type":
            text = args.get("text", "")
            if not text:
                raise ValueError(
                    "text must be non-empty for 'type' action"
                )

        if action == "shortcut":
            keys = args.get("keys")
            if not isinstance(keys, list):
                raise ValueError(
                    "keys must be a list of key names for 'shortcut' action"
                )
            # Normalize and check against blocked shortcuts
            normalized = _normalize_shortcut("+".join(keys))
            settings = _get_settings()
            blocked_normalized = {
                _normalize_shortcut(s) for s in settings.blocked_shortcuts
            }
            if normalized in blocked_normalized:
                raise ValueError(
                    f"Blocked shortcut: '{normalized}'. "
                    f"This shortcut is not allowed."
                )

        if action == "key_press":
            key = args.get("key")
            if not key:
                raise ValueError(
                    "key must be provided for 'key_press' action"
                )

    async def execute(self, params: ToolParams) -> ToolResult:
        """Execute the keyboard action via pyautogui (in a thread)."""
        pag = _get_pyautogui()
        settings = _get_settings()
        args = params.args
        action = args["action"]

        try:
            InputSafetyGuard.check("keyboard", settings)
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        try:
            if action == "type":
                data = await self._execute_type(pag, args, settings)
            else:
                data = await asyncio.to_thread(
                    self._execute_action, pag, action, args,
                )
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            exc_name = type(exc).__name__
            if "FailSafe" in exc_name:
                return ToolResult(
                    success=False, data={},
                    error=f"PyAutoGUI fail-safe triggered: {exc}",
                )
            return ToolResult(success=False, data={}, error=str(exc))

        return ToolResult(success=True, data=data)

    async def _execute_type(
        self,
        pag,
        args: dict,
        settings: ComputerControlSettings,
    ) -> dict:
        """Type text in chunks with halt checks between each chunk."""
        text = args["text"]
        chunk_size = settings.type_chunk_size
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        for chunk in chunks:
            InputSafetyGuard.check("keyboard", settings)
            await asyncio.to_thread(pag.write, chunk)

        return {
            "action": "type",
            "length": len(text),
            "chunks": len(chunks),
        }

    def _execute_action(self, pag, action: str, args: dict) -> dict:
        """Synchronous action dispatch -- runs inside asyncio.to_thread."""
        if action == "shortcut":
            keys = args["keys"]
            pag.hotkey(*keys)
            return {"action": "shortcut", "keys": keys}

        if action == "key_press":
            key = args["key"]
            pag.press(key)
            return {"action": "key_press", "key": key}

        return {"action": action, "error": "unknown action"}

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        args = params.args
        action = args.get("action", "unknown")

        if action == "type":
            text = args.get("text", "")
            preview = text[:100] + "..." if len(text) > 100 else text
            return f"Type text: {preview}"

        if action == "shortcut":
            keys = args.get("keys", [])
            return f"Press shortcut: {'+'.join(keys)}"

        if action == "key_press":
            key = args.get("key", "")
            return f"Press key: {key}"

        return f"Keyboard {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display -- truncates text to 100 chars."""
        args = params.args
        summary: dict = {"action": args.get("action", "")}

        if "text" in args:
            text = args["text"]
            summary["text"] = text[:100] + "..." if len(text) > 100 else text
        if "keys" in args:
            summary["keys"] = args["keys"]
        if "key" in args:
            summary["key"] = args["key"]

        return summary
