"""ClipboardManageTool -- read, write, clear the system clipboard.

Security model:
- read does not require approval.
- write and clear require user approval (modifies clipboard state).
- Content is truncated in audit logs to audit_clipboard_preview_length.
- Primary backend: pyperclip.  Fallback: pyautogui.  Neither: clear error.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nobla.config.settings import ComputerControlSettings, Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.control.safety import ToolExecutionError
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_ACTIONS = {"read", "write", "clear"}
_APPROVAL_ACTIONS = {"write", "clear"}

# Lazy settings cache
_settings_cache: ComputerControlSettings | None = None


def _get_settings() -> ComputerControlSettings:
    """Return (and cache) the ComputerControlSettings singleton."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_clipboard_backend() -> Any:
    """Return a clipboard backend with copy() and paste() methods.

    Tries pyperclip first, then pyautogui.  Raises ToolExecutionError
    if neither is available.
    """
    import importlib

    # Try pyperclip (primary)
    try:
        mod = importlib.import_module("pyperclip")
        if mod is not None:
            return mod
    except (ImportError, ModuleNotFoundError):
        pass

    # Try pyautogui (fallback)
    try:
        mod = importlib.import_module("pyautogui")
        if mod is not None:
            return mod
    except (ImportError, ModuleNotFoundError):
        pass

    raise ToolExecutionError(
        "No clipboard backend available. "
        "Install pyperclip (`pip install pyperclip`) "
        "or pyautogui (`pip install pyautogui`)."
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@register_tool
class ClipboardManageTool(BaseTool):
    """Manage the system clipboard: read, write, clear."""

    name = "clipboard.manage"
    description = (
        "Manage the system clipboard: read current content, "
        "write new content, or clear it"
    )
    category = ToolCategory.CLIPBOARD
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional -- overridden by needs_approval()

    # Injected by tests; None means use global settings.
    _settings_override: ComputerControlSettings | None = None

    def _settings(self) -> ComputerControlSettings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    # -- conditional approval -----------------------------------------------

    def needs_approval(self, params: ToolParams) -> bool:
        """Write and clear require user approval; read does not."""
        return params.args.get("action") in _APPROVAL_ACTIONS

    # -- validation ---------------------------------------------------------

    async def validate(self, params: ToolParams) -> None:
        """Validate action name and content size for write."""
        args = params.args
        action = args.get("action", "")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. "
                f"Valid: {sorted(_VALID_ACTIONS)}"
            )

        if action == "write":
            content = args.get("content", "")
            max_size = self._settings().max_clipboard_size
            if len(content) > max_size:
                raise ValueError(
                    f"Content length ({len(content)}) exceeds maximum "
                    f"clipboard size ({max_size})"
                )

    # -- execution ----------------------------------------------------------

    async def execute(self, params: ToolParams) -> ToolResult:
        """Dispatch to the appropriate clipboard action."""
        args = params.args
        action = args["action"]

        try:
            backend = _get_clipboard_backend()

            if action == "read":
                content = await asyncio.to_thread(backend.paste)
                data = {"action": "read", "content": content}

            elif action == "write":
                content = args.get("content", "")
                await asyncio.to_thread(backend.copy, content)
                data = {"action": "write", "length": len(content)}

            elif action == "clear":
                await asyncio.to_thread(backend.copy, "")
                data = {"action": "clear"}

            else:
                return ToolResult(
                    success=False, data={},
                    error=f"Unknown action: {action}",
                )

        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        return ToolResult(success=True, data=data)

    # -- display helpers ----------------------------------------------------

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        action = params.args.get("action", "unknown")

        if action == "read":
            return "Read clipboard content"
        if action == "write":
            return "Write to clipboard"
        if action == "clear":
            return "Clear clipboard"
        return f"Clipboard {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for audit -- truncates content to preview length."""
        args = params.args
        summary: dict = {"action": args.get("action", "")}

        if "content" in args and args.get("action") == "write":
            content = args["content"]
            max_len = self._settings().audit_clipboard_preview_length
            if len(content) > max_len:
                summary["content_preview"] = content[:max_len] + "..."
            else:
                summary["content_preview"] = content

        return summary
