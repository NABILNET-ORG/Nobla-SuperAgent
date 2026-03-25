"""AppControlTool — launch, close, switch, list applications.

Security model:
- Only apps in the allowed_apps list can be launched or closed.
- Allow-list is checked case-insensitively.
- Only processes that Nobla launched (tracked in _launched_pids) can be closed.
- Stale PIDs are cleaned up automatically when the tracked process has exited.
- Window focus uses platform-specific helpers (Windows/macOS/Linux).
- Process listing uses psutil with a subprocess fallback.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

from nobla.config.settings import ComputerControlSettings, Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.control.safety import ToolExecutionError
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

_VALID_ACTIONS = {"launch", "close", "switch", "list"}
_APPROVAL_ACTIONS = {"launch", "close"}

# Module-level registry: app_name (lower-case) -> Popen process object.
_launched_pids: dict[str, Any] = {}

# Lazy settings cache
_settings_cache: ComputerControlSettings | None = None


def _get_settings() -> ComputerControlSettings:
    """Return (and cache) the ComputerControlSettings singleton."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings().computer_control
    return _settings_cache


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------


def _launch_app(app_name: str) -> subprocess.Popen:
    """Launch an application by name. Returns the Popen process object.

    Raises FileNotFoundError if the application cannot be found.
    """
    if sys.platform == "win32":
        proc = subprocess.Popen(
            ["cmd", "/c", "start", "", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform == "darwin":
        proc = subprocess.Popen(
            ["open", "-a", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # Linux — try launching directly
        proc = subprocess.Popen(
            [app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return proc


def _focus_window(title: str) -> bool:
    """Attempt to bring a window with *title* (substring match) to the foreground.

    Returns True if a matching window was found and focused, False otherwise.
    Platform-specific:
    - Windows: ctypes EnumWindows + SetForegroundWindow
    - macOS: osascript
    - Linux: wmctrl, fallback to xdotool
    """
    if sys.platform == "win32":
        return _focus_window_windows(title)
    elif sys.platform == "darwin":
        return _focus_window_macos(title)
    else:
        return _focus_window_linux(title)


def _focus_window_windows(title: str) -> bool:
    """Windows: use ctypes to enumerate windows and set foreground."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        SetForegroundWindow = user32.SetForegroundWindow
        IsWindowVisible = user32.IsWindowVisible

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
        )

        found_hwnd = None
        title_lower = title.lower()

        def enum_callback(hwnd, _lparam):
            nonlocal found_hwnd
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            if title_lower in buf.value.lower():
                found_hwnd = hwnd
                return False  # stop enumeration
            return True

        EnumWindows(WNDENUMPROC(enum_callback), 0)

        if found_hwnd is not None:
            SetForegroundWindow(found_hwnd)
            return True
        return False
    except Exception:
        return False


def _focus_window_macos(title: str) -> bool:
    """macOS: use osascript to bring window to front."""
    try:
        script = (
            f'tell application "System Events" to set frontmost of '
            f'(first process whose name contains "{title}") to true'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _focus_window_linux(title: str) -> bool:
    """Linux: try wmctrl, fallback to xdotool."""
    try:
        result = subprocess.run(
            ["wmctrl", "-a", title],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception:
        return False

    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title, "windowactivate"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Process listing helpers
# ---------------------------------------------------------------------------


def _get_psutil():
    """Lazy-import psutil; raise ImportError if unavailable."""
    import psutil
    return psutil


def _list_via_psutil() -> list[dict]:
    """List running processes via psutil.process_iter()."""
    psutil = _get_psutil()
    processes: list[dict] = []
    for proc in psutil.process_iter(["name", "pid"]):
        info = proc.info
        processes.append({"name": info["name"], "pid": info["pid"]})
    return processes


def _list_via_subprocess() -> list[dict]:
    """Fallback: list processes via tasklist (Windows) or ps (Unix)."""
    processes: list[dict] = []
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    processes.append({
                        "name": parts[0],
                        "pid": int(parts[1]) if parts[1].isdigit() else 0,
                    })
        else:
            result = subprocess.run(
                ["ps", "-eo", "pid,comm", "--no-headers"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    pid_str, name = parts
                    processes.append({
                        "name": name,
                        "pid": int(pid_str) if pid_str.isdigit() else 0,
                    })
    except Exception:
        pass
    return processes


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@register_tool
class AppControlTool(BaseTool):
    """Manage applications: launch, close, switch focus, list processes."""

    name = "app.control"
    description = (
        "Manage applications: launch from allow-list, close Nobla-launched "
        "processes, switch window focus, list running processes"
    )
    category = ToolCategory.APP_CONTROL
    tier = Tier.ELEVATED
    requires_approval = False  # Conditional — overridden by needs_approval()

    # Injected by tests; None means use global settings.
    _settings_override: ComputerControlSettings | None = None

    def _settings(self) -> ComputerControlSettings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    # -- conditional approval -----------------------------------------------

    def needs_approval(self, params: ToolParams) -> bool:
        """Launch and close require user approval; list and switch do not."""
        return params.args.get("action") in _APPROVAL_ACTIONS

    # -- validation ---------------------------------------------------------

    async def validate(self, params: ToolParams) -> None:
        """Validate action name, allow-list, and required parameters."""
        args = params.args
        action = args.get("action", "")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. "
                f"Valid: {sorted(_VALID_ACTIONS)}"
            )

        settings = self._settings()

        # launch and close require an allowed app_name
        if action in ("launch", "close"):
            app_name = args.get("app_name", "")
            allowed = settings.allowed_apps

            if not allowed:
                raise ValueError(
                    "No allowed_apps configured. "
                    "Set computer_control.allowed_apps in your settings."
                )

            allowed_lower = {a.lower() for a in allowed}
            if app_name.lower() not in allowed_lower:
                raise ValueError(
                    f"App '{app_name}' is not in allowed apps: "
                    f"{sorted(allowed)}"
                )

        # switch requires a window title
        if action == "switch":
            title = args.get("title", "")
            if not title:
                raise ValueError(
                    "title must be provided for 'switch' action"
                )

    # -- execution ----------------------------------------------------------

    async def execute(self, params: ToolParams) -> ToolResult:
        """Dispatch to the appropriate app action."""
        args = params.args
        action = args["action"]

        try:
            if action == "launch":
                data = await self._do_launch(args)
            elif action == "close":
                data = await self._do_close(args)
            elif action == "list":
                data = await asyncio.to_thread(self._do_list)
            elif action == "switch":
                data = await asyncio.to_thread(self._do_switch, args)
            else:
                return ToolResult(
                    success=False, data={},
                    error=f"Unknown action: {action}",
                )
        except ToolExecutionError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except FileNotFoundError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except OSError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        if data.get("_error"):
            return ToolResult(
                success=False, data={},
                error=data.pop("_error"),
            )

        return ToolResult(success=True, data=data)

    # -- individual actions -------------------------------------------------

    async def _do_launch(self, args: dict) -> dict:
        """Launch an application and track its PID."""
        app_name = args["app_name"]
        key = app_name.lower()

        # If there's a stale entry, clean it up
        if key in _launched_pids:
            existing = _launched_pids[key]
            if existing.poll() is not None:
                # Process already exited — remove stale entry
                del _launched_pids[key]
            else:
                # Process is still running
                return {
                    "action": "launch",
                    "app_name": app_name,
                    "pid": existing.pid,
                    "status": "already running",
                }

        proc = await asyncio.to_thread(_launch_app, app_name)
        _launched_pids[key] = proc

        return {
            "action": "launch",
            "app_name": app_name,
            "pid": proc.pid,
            "status": "launched",
        }

    async def _do_close(self, args: dict) -> dict:
        """Close an application, but only if Nobla launched it."""
        app_name = args["app_name"]
        key = app_name.lower()

        if key not in _launched_pids:
            return {
                "_error": (
                    f"App '{app_name}' was not launched by Nobla. "
                    f"Only Nobla-launched processes can be closed."
                ),
            }

        proc = _launched_pids[key]

        # Check if process already exited (stale PID)
        if proc.poll() is not None:
            del _launched_pids[key]
            return {
                "action": "close",
                "app_name": app_name,
                "pid": proc.pid,
                "status": "already exited — cleaned up",
            }

        # Terminate the process
        await asyncio.to_thread(proc.terminate)
        try:
            await asyncio.to_thread(proc.wait, timeout=5)
        except subprocess.TimeoutExpired:
            await asyncio.to_thread(proc.kill)

        del _launched_pids[key]

        return {
            "action": "close",
            "app_name": app_name,
            "pid": proc.pid,
            "status": "terminated",
        }

    @staticmethod
    def _do_list() -> dict:
        """List running processes via psutil or subprocess fallback."""
        try:
            processes = _list_via_psutil()
        except ImportError:
            processes = _list_via_subprocess()
        except Exception:
            processes = _list_via_subprocess()

        return {"action": "list", "processes": processes}

    @staticmethod
    def _do_switch(args: dict) -> dict:
        """Switch window focus to the given title."""
        title = args["title"]
        found = _focus_window(title)

        if not found:
            return {
                "_error": (
                    f"Window with title '{title}' not found."
                ),
            }

        return {
            "action": "switch",
            "title": title,
            "status": "focused",
        }

    # -- display helpers ----------------------------------------------------

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        args = params.args
        action = args.get("action", "unknown")

        if action == "launch":
            return f"Launch application: {args.get('app_name', '?')}"
        if action == "close":
            return f"Close application: {args.get('app_name', '?')}"
        if action == "list":
            return "List running processes"
        if action == "switch":
            return f"Switch focus to window: {args.get('title', '?')}"
        return f"App {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display — exposes only safe fields."""
        args = params.args
        summary: dict = {"action": args.get("action", "")}

        if "app_name" in args:
            summary["app_name"] = args["app_name"]
        if "title" in args:
            summary["title"] = args["title"]

        return summary
