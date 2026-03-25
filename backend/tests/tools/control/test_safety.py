"""Tests for InputSafetyGuard — rate limiting, halt, platform checks."""
from __future__ import annotations

import sys
import time
from unittest.mock import patch

import pytest

from nobla.config.settings import ComputerControlSettings
from nobla.tools.control.safety import (
    InputSafetyGuard,
    ToolExecutionError,
    _normalize_shortcut,
)


@pytest.fixture(autouse=True)
def _reset_guard():
    """Reset guard state before every test."""
    InputSafetyGuard.reset()
    yield
    InputSafetyGuard.reset()


# ---------------------------------------------------------------------------
# _normalize_shortcut
# ---------------------------------------------------------------------------


class TestNormalizeShortcut:
    def test_lowercase_and_sorted(self):
        assert _normalize_shortcut("Ctrl+Alt+Delete") == "alt+ctrl+delete"

    def test_already_normalized(self):
        assert _normalize_shortcut("a+b+c") == "a+b+c"

    def test_single_key(self):
        assert _normalize_shortcut("Enter") == "enter"

    def test_reversed_order(self):
        assert _normalize_shortcut("shift+ctrl") == "ctrl+shift"

    def test_with_spaces(self):
        assert _normalize_shortcut(" Ctrl + Alt ") == "alt+ctrl"


# ---------------------------------------------------------------------------
# halt / resume / reset
# ---------------------------------------------------------------------------


class TestHaltResume:
    def test_halt_blocks_check(self, control_settings):
        InputSafetyGuard.halt()
        with pytest.raises(ToolExecutionError, match="halted"):
            InputSafetyGuard.check("mouse", control_settings)

    def test_resume_after_halt(self, control_settings):
        InputSafetyGuard.halt()
        InputSafetyGuard.resume()
        # Should not raise
        InputSafetyGuard.check("mouse", control_settings)

    def test_reset_clears_halt(self, control_settings):
        InputSafetyGuard.halt()
        InputSafetyGuard.reset()
        InputSafetyGuard.check("mouse", control_settings)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_under_limit_passes(self):
        settings = ComputerControlSettings(
            max_actions_per_minute=120,
            min_action_delay_ms=0,
        )
        for _ in range(5):
            InputSafetyGuard.check("mouse", settings)

    def test_over_limit_raises(self):
        settings = ComputerControlSettings(
            max_actions_per_minute=3,
            min_action_delay_ms=0,
        )
        InputSafetyGuard.check("mouse", settings)
        InputSafetyGuard.check("mouse", settings)
        InputSafetyGuard.check("mouse", settings)
        with pytest.raises(ToolExecutionError, match="Rate limit"):
            InputSafetyGuard.check("mouse", settings)

    def test_different_tool_types_have_separate_counters(self):
        settings = ComputerControlSettings(
            max_actions_per_minute=2,
            min_action_delay_ms=0,
        )
        InputSafetyGuard.check("mouse", settings)
        InputSafetyGuard.check("mouse", settings)
        # keyboard should still work — separate counter
        InputSafetyGuard.check("keyboard", settings)

    def test_window_expiry_resets_counter(self):
        settings = ComputerControlSettings(
            max_actions_per_minute=1,
            min_action_delay_ms=0,
        )
        InputSafetyGuard.check("mouse", settings)

        # Manually expire the window by back-dating the counter
        InputSafetyGuard._counters["mouse"] = (0, time.time() - 61)

        # Should succeed now — window expired
        InputSafetyGuard.check("mouse", settings)


# ---------------------------------------------------------------------------
# Minimum delay
# ---------------------------------------------------------------------------


class TestMinDelay:
    def test_min_delay_blocks_rapid_calls(self):
        settings = ComputerControlSettings(
            min_action_delay_ms=500,
            max_actions_per_minute=1000,
        )
        InputSafetyGuard.check("mouse", settings)
        with pytest.raises(ToolExecutionError, match="Minimum delay"):
            InputSafetyGuard.check("mouse", settings)

    def test_zero_delay_allows_rapid_calls(self):
        settings = ComputerControlSettings(
            min_action_delay_ms=0,
            max_actions_per_minute=1000,
        )
        InputSafetyGuard.check("mouse", settings)
        InputSafetyGuard.check("mouse", settings)

    def test_delay_applies_per_tool_type(self):
        settings = ComputerControlSettings(
            min_action_delay_ms=500,
            max_actions_per_minute=1000,
        )
        InputSafetyGuard.check("mouse", settings)
        # keyboard has its own last-action timestamp
        InputSafetyGuard.check("keyboard", settings)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    @patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=False)
    def test_wayland_raises_on_linux(self, control_settings):
        InputSafetyGuard.reset()  # clear cached platform check
        with patch.object(sys, "platform", "linux"):
            with pytest.raises(ToolExecutionError, match="Wayland"):
                InputSafetyGuard.check("mouse", control_settings)

    @patch.dict("os.environ", {}, clear=False)
    def test_no_display_raises_on_linux(self, control_settings):
        InputSafetyGuard.reset()
        with patch.object(sys, "platform", "linux"):
            with patch.dict("os.environ", {"DISPLAY": "", "WAYLAND_DISPLAY": ""}, clear=False):
                with pytest.raises(ToolExecutionError, match="No display"):
                    InputSafetyGuard.check("mouse", control_settings)

    def test_platform_check_cached(self):
        """After first successful check, platform is not re-checked."""
        settings = ComputerControlSettings(min_action_delay_ms=0)
        InputSafetyGuard.check("mouse", settings)
        assert InputSafetyGuard._platform_checked is True
        # Second call should skip platform check (no error even if we break env)
        InputSafetyGuard.check("mouse", settings)

    @patch.object(sys, "platform", "win32")
    def test_windows_always_passes(self, control_settings):
        InputSafetyGuard.reset()
        InputSafetyGuard.check("mouse", control_settings)

    @patch.object(sys, "platform", "darwin")
    def test_macos_always_passes(self, control_settings):
        InputSafetyGuard.reset()
        InputSafetyGuard.check("mouse", control_settings)
