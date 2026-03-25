"""InputSafetyGuard — centralised pre-execution safety checks.

Every computer-control tool calls ``InputSafetyGuard.check(tool_type, settings)``
before performing any action.  The guard enforces:

* **Halt flag** — an emergency stop set by the kill-switch or user.
* **Platform sanity** — rejects Wayland and headless Linux (no DISPLAY).
* **Rate limiting** — per-tool-type counter, ``max_actions_per_minute``.
* **Minimum delay** — enforces ``min_action_delay_ms`` between actions of the
  same tool type.

All state is class-level so that ``reset()`` can wipe it for tests.
"""
from __future__ import annotations

import os
import sys
import time

from nobla.config.settings import ComputerControlSettings


class ToolExecutionError(Exception):
    """Raised when a safety check blocks tool execution."""


# ---------------------------------------------------------------------------
# Free function
# ---------------------------------------------------------------------------


def _normalize_shortcut(keys: str) -> str:
    """Lower-case, strip, sort, and rejoin a ``+``-delimited shortcut.

    >>> _normalize_shortcut("Ctrl+Alt+Delete")
    'alt+ctrl+delete'
    """
    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    parts.sort()
    return "+".join(parts)


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class InputSafetyGuard:
    """Class-level (singleton) safety gate for all computer-control tools.

    Usage::

        InputSafetyGuard.check("mouse", settings)
    """

    _halted: bool = False
    # {tool_type: (count, window_start_timestamp)}
    _counters: dict[str, tuple[int, float]] = {}
    # {tool_type: last_action_timestamp}
    _last_action: dict[str, float] = {}
    _platform_checked: bool = False

    # -- public API ---------------------------------------------------------

    @classmethod
    def check(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        """Run all safety checks.  Raises ``ToolExecutionError`` on failure."""
        cls._check_halt()
        cls._check_platform()
        cls._check_min_delay(tool_type, settings)
        cls._check_rate_limit(tool_type, settings)

    @classmethod
    def halt(cls) -> None:
        """Emergency stop — block all subsequent tool executions."""
        cls._halted = True

    @classmethod
    def resume(cls) -> None:
        """Clear the halt flag, allowing tools to run again."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Wipe all state (for tests)."""
        cls._halted = False
        cls._counters.clear()
        cls._last_action.clear()
        cls._platform_checked = False

    # -- internal checks ----------------------------------------------------

    @classmethod
    def _check_halt(cls) -> None:
        if cls._halted:
            raise ToolExecutionError(
                "Computer control is halted. Call resume() to re-enable."
            )

    @classmethod
    def _check_platform(cls) -> None:
        """Reject Wayland and headless Linux (no DISPLAY).

        The result is cached in ``_platform_checked`` so the check only
        runs once per process (or until ``reset()``).
        """
        if cls._platform_checked:
            return

        if sys.platform == "linux":
            if os.environ.get("WAYLAND_DISPLAY"):
                raise ToolExecutionError(
                    "Wayland is not supported for computer-control tools. "
                    "Use X11 or run under XWayland."
                )
            if not os.environ.get("DISPLAY"):
                raise ToolExecutionError(
                    "No display server found (DISPLAY is unset). "
                    "Computer-control tools require a graphical session."
                )

        cls._platform_checked = True

    @classmethod
    def _check_rate_limit(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        now = time.time()
        count, window_start = cls._counters.get(tool_type, (0, now))

        # Reset window if more than 60 seconds have elapsed
        if now - window_start >= 60:
            count = 0
            window_start = now

        if count >= settings.max_actions_per_minute:
            raise ToolExecutionError(
                f"Rate limit exceeded for '{tool_type}': "
                f"{settings.max_actions_per_minute} actions/minute."
            )

        cls._counters[tool_type] = (count + 1, window_start)

    @classmethod
    def _check_min_delay(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        if settings.min_action_delay_ms <= 0:
            return

        now = time.time()
        last = cls._last_action.get(tool_type)

        if last is not None:
            elapsed_ms = (now - last) * 1000
            if elapsed_ms < settings.min_action_delay_ms:
                raise ToolExecutionError(
                    f"Minimum delay of {settings.min_action_delay_ms}ms "
                    f"not met for '{tool_type}' (elapsed: {elapsed_ms:.0f}ms)."
                )

        cls._last_action[tool_type] = now
