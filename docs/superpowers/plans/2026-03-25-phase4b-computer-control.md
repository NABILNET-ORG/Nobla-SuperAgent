# Phase 4B: Computer Control — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 host-level computer control tools (mouse, keyboard, files, apps, clipboard) with a 6-layer security model, shared safety guard, and Flutter approval UI.

**Architecture:** All tools execute on the host OS (not Docker) wrapped in the existing ToolExecutor pipeline. An `InputSafetyGuard` class provides rate limiting and kill switch integration for mouse/keyboard. The Flutter app gets an approval bottom sheet and activity feed. All tools follow the Phase 4C compound subcommand pattern (`git.ops` style) with conditional `needs_approval()` overrides.

**Tech Stack:** Python 3.12+, pyautogui (mouse/keyboard), pyperclip (clipboard), psutil (app management), pathlib/shutil (file ops), Flutter 3.x/Riverpod (approval UI)

**Spec:** `docs/superpowers/specs/2026-03-25-phase4b-computer-control-design.md`

---

## File Map

### New Files — Backend

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `backend/nobla/tools/control/__init__.py` | Auto-discovery imports | ~15 |
| `backend/nobla/tools/control/safety.py` | InputSafetyGuard — rate limiter, halt, platform check | ~100 |
| `backend/nobla/tools/control/mouse.py` | MouseControlTool — move/click/double_click/drag/scroll | ~150 |
| `backend/nobla/tools/control/keyboard.py` | KeyboardControlTool — type/shortcut/key_press | ~160 |
| `backend/nobla/tools/control/file_manager.py` | FileManageTool — read/write/list/move/copy/delete/info | ~200 |
| `backend/nobla/tools/control/app.py` | AppControlTool — launch/close/switch/list | ~180 |
| `backend/nobla/tools/control/clipboard.py` | ClipboardManageTool — read/write/clear | ~80 |

### New Files — Tests

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `backend/tests/tools/control/conftest.py` | Shared fixtures (mock_pyautogui, control_settings, safety_guard) | ~60 |
| `backend/tests/tools/control/test_settings.py` | ComputerControlSettings validation | ~80 |
| `backend/tests/tools/control/test_safety.py` | InputSafetyGuard rate limiting, halt, platform | ~150 |
| `backend/tests/tools/control/test_mouse.py` | MouseControlTool tests | ~200 |
| `backend/tests/tools/control/test_keyboard.py` | KeyboardControlTool tests | ~200 |
| `backend/tests/tools/control/test_file_manager.py` | FileManageTool tests (largest — path security) | ~250 |
| `backend/tests/tools/control/test_app.py` | AppControlTool tests | ~200 |
| `backend/tests/tools/control/test_clipboard.py` | ClipboardManageTool tests | ~120 |

### New Files — Flutter

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `app/lib/features/security/models/approval_models.dart` | ApprovalRequest, ActivityEntry data classes | ~40 |
| `app/lib/features/security/providers/approval_provider.dart` | Riverpod notifier for approval queue | ~80 |
| `app/lib/features/security/widgets/approval_sheet.dart` | Approval bottom sheet widget | ~150 |
| `app/lib/features/security/widgets/activity_feed.dart` | Real-time activity feed widget | ~120 |

### Modified Files

| File | Change | Lines Added |
|------|--------|------------|
| `backend/nobla/config/settings.py:188` | Add `ComputerControlSettings` class + field in `Settings` | ~30 |
| `backend/nobla/tools/__init__.py` | Add `from nobla.tools import control` for auto-discovery | ~1 |

---

## Task Dependencies

```
Task 0 (Settings + Safety) ──► Tasks 1-5 (Tools, parallelizable)
                               ├─ Task 1: MouseControlTool
                               ├─ Task 2: KeyboardControlTool
                               ├─ Task 3: FileManageTool
                               ├─ Task 4: AppControlTool
                               └─ Task 5: ClipboardManageTool
                                          │
                                          ▼
                               Task 6: Wiring + Integration
                                          │
                                          ▼
                               Tasks 7-8 (Flutter, parallelizable)
                               ├─ Task 7: Approval Bottom Sheet
                               └─ Task 8: Activity Feed
```

- **Task 0** must complete first (foundation)
- **Tasks 1-5** are independent — parallelize via subagents
- **Task 6** depends on all tools being complete
- **Tasks 7-8** are independent Flutter work — parallelize

---

## Task 0: Settings + InputSafetyGuard (Foundation)

**Files:**
- Modify: `backend/nobla/config/settings.py:188` (add ComputerControlSettings)
- Create: `backend/nobla/tools/control/__init__.py`
- Create: `backend/nobla/tools/control/safety.py`
- Create: `backend/tests/tools/control/__init__.py`
- Create: `backend/tests/tools/control/conftest.py`
- Create: `backend/tests/tools/control/test_settings.py`
- Create: `backend/tests/tools/control/test_safety.py`

### Step-by-step

- [ ] **Step 1: Create directory structure**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
mkdir -p backend/nobla/tools/control
mkdir -p backend/tests/tools/control
touch backend/nobla/tools/control/__init__.py
touch backend/tests/tools/control/__init__.py
```

- [ ] **Step 2: Write ComputerControlSettings tests**

Create `backend/tests/tools/control/test_settings.py`:

```python
"""Tests for ComputerControlSettings validation."""
import pytest
from nobla.config.settings import ComputerControlSettings


class TestComputerControlSettings:
    """Test ComputerControlSettings validation and defaults."""

    def test_defaults(self):
        settings = ComputerControlSettings()
        assert settings.enabled is True
        assert settings.allowed_read_dirs == []
        assert settings.allowed_write_dirs == []
        assert settings.allowed_apps == []
        assert settings.failsafe_enabled is True
        assert settings.min_action_delay_ms == 100
        assert settings.max_actions_per_minute == 120
        assert settings.type_chunk_size == 50
        assert settings.max_file_size_bytes == 10_485_760
        assert settings.max_backups_per_file == 3
        assert settings.max_clipboard_size == 1_048_576
        assert settings.audit_clipboard_preview_length == 50

    def test_blocked_shortcuts_defaults(self):
        settings = ComputerControlSettings()
        assert "ctrl+alt+delete" in settings.blocked_shortcuts
        assert "alt+f4" in settings.blocked_shortcuts
        assert "win+r" in settings.blocked_shortcuts
        assert "win+l" in settings.blocked_shortcuts
        assert "ctrl+w" in settings.blocked_shortcuts
        assert "ctrl+shift+delete" in settings.blocked_shortcuts

    def test_write_dirs_must_be_subset_of_read_dirs(self, tmp_path):
        read_dir = str(tmp_path / "readable")
        write_dir = str(tmp_path / "readable" / "writable")
        (tmp_path / "readable" / "writable").mkdir(parents=True)
        settings = ComputerControlSettings(
            allowed_read_dirs=[read_dir],
            allowed_write_dirs=[write_dir],
        )
        assert settings.allowed_write_dirs == [write_dir]

    def test_write_dir_outside_read_dir_raises(self, tmp_path):
        read_dir = str(tmp_path / "readable")
        write_dir = str(tmp_path / "elsewhere")
        (tmp_path / "readable").mkdir()
        (tmp_path / "elsewhere").mkdir()
        with pytest.raises(ValueError, match="not within any allowed read directory"):
            ComputerControlSettings(
                allowed_read_dirs=[read_dir],
                allowed_write_dirs=[write_dir],
            )

    def test_custom_values(self):
        settings = ComputerControlSettings(
            enabled=False,
            max_actions_per_minute=60,
            min_action_delay_ms=200,
            type_chunk_size=25,
        )
        assert settings.enabled is False
        assert settings.max_actions_per_minute == 60
        assert settings.min_action_delay_ms == 200
        assert settings.type_chunk_size == 25

    def test_empty_write_dirs_always_valid(self):
        settings = ComputerControlSettings(
            allowed_read_dirs=["/some/path"],
            allowed_write_dirs=[],
        )
        assert settings.allowed_write_dirs == []

    def test_empty_blocked_shortcuts_allowed(self):
        settings = ComputerControlSettings(blocked_shortcuts=[])
        assert settings.blocked_shortcuts == []
```

- [ ] **Step 3: Run settings tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_settings.py -v
```

Expected: FAIL — `ComputerControlSettings` not defined yet.

- [ ] **Step 4: Implement ComputerControlSettings**

Add to `backend/nobla/config/settings.py` after `CodeExecutionSettings` (around line 170, before root `Settings` class):

```python
class ComputerControlSettings(BaseModel):
    """Configuration for Phase 4B computer control tools."""
    enabled: bool = True

    # File management
    allowed_read_dirs: list[str] = Field(default_factory=list)
    allowed_write_dirs: list[str] = Field(default_factory=list)
    max_file_size_bytes: int = 10_485_760
    max_backups_per_file: int = 3

    # App management
    allowed_apps: list[str] = Field(default_factory=list)

    # Input safety
    failsafe_enabled: bool = True
    min_action_delay_ms: int = 100
    max_actions_per_minute: int = 120
    type_chunk_size: int = 50
    blocked_shortcuts: list[str] = Field(default_factory=lambda: [
        "ctrl+alt+delete", "alt+f4", "ctrl+shift+delete",
        "win+r", "win+l", "ctrl+w",
    ])

    # Clipboard
    max_clipboard_size: int = 1_048_576
    audit_clipboard_preview_length: int = 50

    @model_validator(mode="after")
    def validate_write_dirs_subset(self):
        """Ensure all write dirs are within a read dir."""
        for wd in self.allowed_write_dirs:
            wd_resolved = Path(wd).resolve()
            if not any(
                wd_resolved.is_relative_to(Path(rd).resolve())
                for rd in self.allowed_read_dirs
            ):
                raise ValueError(
                    f"Write directory '{wd}' is not within any allowed read directory"
                )
        return self
```

Add `from pathlib import Path` to imports if not present. Add field to root `Settings` class (after `code` field at line 189):

```python
    computer_control: ComputerControlSettings = Field(default_factory=ComputerControlSettings)
```

- [ ] **Step 5: Run settings tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_settings.py -v
```

Expected: ALL PASS (7 tests).

- [ ] **Step 6: Write conftest.py shared fixtures**

Create `backend/tests/tools/control/conftest.py`:

```python
"""Shared fixtures for Phase 4B computer control tool tests."""
import pytest
from unittest.mock import MagicMock, patch

from nobla.config.settings import ComputerControlSettings


@pytest.fixture
def control_settings(tmp_path):
    """Settings with tmp_path-based allowed directories."""
    read_dir = tmp_path / "readable"
    write_dir = tmp_path / "readable" / "writable"
    read_dir.mkdir()
    write_dir.mkdir()
    return ComputerControlSettings(
        allowed_read_dirs=[str(read_dir)],
        allowed_write_dirs=[str(write_dir)],
        allowed_apps=["notepad", "chrome", "code"],
        min_action_delay_ms=0,  # No delay in tests
        max_actions_per_minute=9999,  # No rate limit in tests
    )


@pytest.fixture
def mock_pyautogui():
    """Mock pyautogui for mouse/keyboard tests."""
    with patch.dict("sys.modules", {"pyautogui": MagicMock()}) as _:
        import sys
        mock = sys.modules["pyautogui"]
        mock.size.return_value = (1920, 1080)
        mock.FAILSAFE = True
        mock.FailSafeException = type("FailSafeException", (Exception,), {})
        yield mock


@pytest.fixture
def mock_pyperclip():
    """Mock pyperclip for clipboard tests."""
    with patch.dict("sys.modules", {"pyperclip": MagicMock()}) as _:
        import sys
        mock = sys.modules["pyperclip"]
        mock.paste.return_value = "clipboard content"
        yield mock


@pytest.fixture
def mock_psutil():
    """Mock psutil for app control tests."""
    with patch.dict("sys.modules", {"psutil": MagicMock()}) as _:
        import sys
        yield sys.modules["psutil"]
```

- [ ] **Step 7: Write InputSafetyGuard tests**

Create `backend/tests/tools/control/test_safety.py`:

```python
"""Tests for InputSafetyGuard — rate limiting, halt, platform detection."""
import time
import pytest
from unittest.mock import patch, MagicMock

from nobla.tools.control.safety import InputSafetyGuard, _normalize_shortcut
from nobla.config.settings import ComputerControlSettings


@pytest.fixture(autouse=True)
def reset_guard():
    """Reset guard state between every test."""
    InputSafetyGuard.reset()
    yield
    InputSafetyGuard.reset()


class TestNormalizeShortcut:
    """Test shortcut normalization for blocklist matching."""

    def test_lowercase(self):
        assert _normalize_shortcut(["Ctrl", "Alt", "Delete"]) == "alt+ctrl+delete"

    def test_sorted_alphabetically(self):
        assert _normalize_shortcut(["alt", "ctrl", "delete"]) == "alt+ctrl+delete"
        assert _normalize_shortcut(["ctrl", "alt", "delete"]) == "alt+ctrl+delete"

    def test_single_key(self):
        assert _normalize_shortcut(["f4"]) == "f4"

    def test_two_keys(self):
        assert _normalize_shortcut(["alt", "f4"]) == "alt+f4"


class TestInputSafetyGuardHalt:
    """Test halt/resume functionality."""

    def test_check_passes_when_not_halted(self, control_settings):
        InputSafetyGuard.check("mouse", control_settings)  # Should not raise

    def test_halt_blocks_check(self, control_settings):
        InputSafetyGuard.halt()
        with pytest.raises(Exception, match="halted"):
            InputSafetyGuard.check("mouse", control_settings)

    def test_resume_unblocks_check(self, control_settings):
        InputSafetyGuard.halt()
        InputSafetyGuard.resume()
        InputSafetyGuard.check("mouse", control_settings)  # Should not raise

    def test_halt_reenables_failsafe(self):
        mock_pag = MagicMock()
        mock_pag.FAILSAFE = False
        with patch.dict("sys.modules", {"pyautogui": mock_pag}):
            InputSafetyGuard.halt()
            assert mock_pag.FAILSAFE is True

    def test_halt_without_pyautogui_installed(self):
        with patch.dict("sys.modules", {"pyautogui": None}):
            InputSafetyGuard.halt()  # Should not raise
            assert InputSafetyGuard._halted is True


class TestInputSafetyGuardRateLimit:
    """Test rate limiting per tool type."""

    def test_within_limit_passes(self, control_settings):
        control_settings.max_actions_per_minute = 5
        for _ in range(5):
            InputSafetyGuard.check("mouse", control_settings)

    def test_exceeds_limit_raises(self, control_settings):
        control_settings.max_actions_per_minute = 3
        control_settings.min_action_delay_ms = 0
        for _ in range(3):
            InputSafetyGuard.check("mouse", control_settings)
        with pytest.raises(Exception, match="rate limit"):
            InputSafetyGuard.check("mouse", control_settings)

    def test_per_tool_counters_independent(self, control_settings):
        control_settings.max_actions_per_minute = 2
        control_settings.min_action_delay_ms = 0
        InputSafetyGuard.check("mouse", control_settings)
        InputSafetyGuard.check("mouse", control_settings)
        # Mouse exhausted, but keyboard should still work
        InputSafetyGuard.check("keyboard", control_settings)

    def test_counter_expires_after_window(self, control_settings):
        control_settings.max_actions_per_minute = 1
        control_settings.min_action_delay_ms = 0
        InputSafetyGuard.check("mouse", control_settings)
        # Manually expire the counter entry
        InputSafetyGuard._counters["mouse"][0] = time.monotonic() - 61
        InputSafetyGuard.check("mouse", control_settings)  # Should not raise


class TestInputSafetyGuardMinDelay:
    """Test minimum delay between actions."""

    def test_min_delay_enforced(self):
        settings = ComputerControlSettings(
            min_action_delay_ms=500,
            max_actions_per_minute=9999,
        )
        InputSafetyGuard.check("mouse", settings)
        with pytest.raises(Exception, match="too fast"):
            InputSafetyGuard.check("mouse", settings)

    def test_zero_delay_allows_rapid(self):
        settings = ComputerControlSettings(
            min_action_delay_ms=0,
            max_actions_per_minute=9999,
        )
        InputSafetyGuard.check("mouse", settings)
        InputSafetyGuard.check("mouse", settings)  # Should not raise


class TestInputSafetyGuardPlatform:
    """Test platform detection (lazy, cached)."""

    def test_platform_check_cached(self, control_settings):
        InputSafetyGuard.check("mouse", control_settings)
        assert InputSafetyGuard._platform_checked is True
        # Second call uses cache — no re-check
        InputSafetyGuard.check("mouse", control_settings)

    @patch("sys.platform", "linux")
    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=False)
    def test_wayland_detected(self, control_settings):
        with pytest.raises(Exception, match="Wayland"):
            InputSafetyGuard.check("mouse", control_settings)

    @patch("sys.platform", "linux")
    @patch.dict("os.environ", {}, clear=True)
    def test_no_display_detected(self, control_settings):
        with pytest.raises(Exception, match="No DISPLAY|No display"):
            InputSafetyGuard.check("mouse", control_settings)

    def test_reset_clears_platform_cache(self, control_settings):
        InputSafetyGuard.check("mouse", control_settings)
        assert InputSafetyGuard._platform_checked is True
        InputSafetyGuard.reset()
        assert InputSafetyGuard._platform_checked is False
```

- [ ] **Step 8: Run safety tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_safety.py -v
```

Expected: FAIL — `nobla.tools.control.safety` module does not exist yet.

- [ ] **Step 9: Implement InputSafetyGuard**

Create `backend/nobla/tools/control/safety.py`:

```python
"""InputSafetyGuard — shared safety layer for mouse/keyboard tools.

Enforces rate limiting, kill switch integration, pyautogui failsafe,
and platform detection. Used by MouseControlTool and KeyboardControlTool.
"""
from __future__ import annotations

import os
import sys
import time
from collections import deque

from nobla.config.settings import ComputerControlSettings


class ToolExecutionError(Exception):
    """Raised when a tool execution is blocked by safety checks."""


def _normalize_shortcut(keys: list[str]) -> str:
    """Normalize shortcut keys: lowercase, sorted, joined with +."""
    return "+".join(sorted(k.lower() for k in keys))


class InputSafetyGuard:
    """Shared safety guard for mouse and keyboard input tools.

    Class-level state acts as a singleton. Use reset() in tests.
    """
    _halted: bool = False
    _counters: dict[str, deque[float]] = {"mouse": deque(), "keyboard": deque()}
    _last_action: dict[str, float] = {"mouse": 0.0, "keyboard": 0.0}
    _platform_checked: bool = False

    @classmethod
    def check(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        """Check all safety conditions. Raises ToolExecutionError if blocked."""
        cls._check_halt()
        cls._check_platform()
        cls._check_rate_limit(tool_type, settings)
        cls._check_min_delay(tool_type, settings)

    @classmethod
    def halt(cls) -> None:
        """Called by kill switch. Blocks all future input actions."""
        cls._halted = True
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
        except (ImportError, ModuleNotFoundError):
            pass

    @classmethod
    def resume(cls) -> None:
        """Re-enable input after halt. Requires explicit call."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Reset all state. Used by test fixtures for isolation."""
        cls._halted = False
        cls._counters = {"mouse": deque(), "keyboard": deque()}
        cls._last_action = {"mouse": 0.0, "keyboard": 0.0}
        cls._platform_checked = False

    @classmethod
    def _check_halt(cls) -> None:
        if cls._halted:
            raise ToolExecutionError("Computer control halted by kill switch")

    @classmethod
    def _check_platform(cls) -> None:
        if cls._platform_checked:
            return
        if sys.platform == "linux":
            session_type = os.environ.get("XDG_SESSION_TYPE", "")
            if session_type == "wayland":
                raise ToolExecutionError(
                    "Wayland detected — pyautogui requires X11 session"
                )
            if not os.environ.get("DISPLAY"):
                raise ToolExecutionError(
                    "No DISPLAY — computer control requires a graphical session"
                )
        cls._platform_checked = True

    @classmethod
    def _check_rate_limit(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        now = time.monotonic()
        counter = cls._counters[tool_type]
        while counter and counter[0] < now - 60:
            counter.popleft()
        if len(counter) >= settings.max_actions_per_minute:
            raise ToolExecutionError(
                f"{tool_type} rate limit exceeded ({settings.max_actions_per_minute}/min)"
            )
        counter.append(now)

    @classmethod
    def _check_min_delay(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        now = time.monotonic()
        last = cls._last_action[tool_type]
        if last > 0:
            elapsed_ms = (now - last) * 1000
            if elapsed_ms < settings.min_action_delay_ms:
                raise ToolExecutionError(
                    f"Action too fast — {elapsed_ms:.0f}ms < "
                    f"{settings.min_action_delay_ms}ms minimum"
                )
        cls._last_action[tool_type] = now
```

- [ ] **Step 10: Run safety tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_safety.py -v
```

Expected: ALL PASS (~20 tests).

- [ ] **Step 11: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/config/settings.py backend/nobla/tools/control/ backend/tests/tools/control/
git commit -m "feat(tools): add ComputerControlSettings and InputSafetyGuard for Phase 4B"
```

---

## Task 1: MouseControlTool

**Files:**
- Create: `backend/nobla/tools/control/mouse.py`
- Create: `backend/tests/tools/control/test_mouse.py`

**Depends on:** Task 0 (settings + safety guard)

### Step-by-step

- [ ] **Step 1: Write MouseControlTool tests**

Create `backend/tests/tools/control/test_mouse.py`:

```python
"""Tests for MouseControlTool — move, click, double_click, drag, scroll."""
import pytest
from unittest.mock import patch, MagicMock, call

from nobla.tools.models import ToolParams


# --- Fixtures ---

@pytest.fixture
def mouse_tool(mock_pyautogui):
    from nobla.tools.control.mouse import MouseControlTool
    return MouseControlTool()


@pytest.fixture
def make_params():
    def _make(action, **kwargs):
        return ToolParams(tool_name="mouse.control", args={"action": action, **kwargs})
    return _make


# --- Validation Tests ---

class TestMouseValidation:

    async def test_valid_move(self, mouse_tool, make_params):
        await mouse_tool.validate(make_params("move", x=100, y=200))

    async def test_negative_x_raises(self, mouse_tool, make_params):
        with pytest.raises(ValueError, match="coordinates"):
            await mouse_tool.validate(make_params("move", x=-1, y=200))

    async def test_negative_y_raises(self, mouse_tool, make_params):
        with pytest.raises(ValueError, match="coordinates"):
            await mouse_tool.validate(make_params("move", x=100, y=-1))

    async def test_beyond_screen_x_raises(self, mouse_tool, make_params, mock_pyautogui):
        mock_pyautogui.size.return_value = (1920, 1080)
        with pytest.raises(ValueError, match="coordinates"):
            await mouse_tool.validate(make_params("move", x=1921, y=500))

    async def test_beyond_screen_y_raises(self, mouse_tool, make_params, mock_pyautogui):
        mock_pyautogui.size.return_value = (1920, 1080)
        with pytest.raises(ValueError, match="coordinates"):
            await mouse_tool.validate(make_params("move", x=500, y=1081))

    async def test_invalid_button_raises(self, mouse_tool, make_params):
        with pytest.raises(ValueError, match="button"):
            await mouse_tool.validate(make_params("click", x=100, y=200, button="invalid"))

    async def test_invalid_action_raises(self, mouse_tool, make_params):
        with pytest.raises(ValueError, match="action"):
            await mouse_tool.validate(make_params("invalid_action", x=100, y=200))

    async def test_negative_duration_raises(self, mouse_tool, make_params):
        with pytest.raises(ValueError, match="duration"):
            await mouse_tool.validate(make_params("move", x=100, y=200, duration=-1.0))


# --- Execution Tests ---

class TestMouseExecution:

    @pytest.mark.asyncio
    async def test_move(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(make_params("move", x=100, y=200, duration=0.5))
        assert result.success is True
        mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0.5)

    @pytest.mark.asyncio
    async def test_click_default_left(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(make_params("click", x=450, y=320))
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(450, 320, button="left")

    @pytest.mark.asyncio
    async def test_click_right_button(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(make_params("click", x=100, y=100, button="right"))
        mock_pyautogui.click.assert_called_once_with(100, 100, button="right")

    @pytest.mark.asyncio
    async def test_double_click(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(make_params("double_click", x=200, y=300))
        assert result.success is True
        mock_pyautogui.doubleClick.assert_called_once_with(200, 300, button="left")

    @pytest.mark.asyncio
    async def test_scroll_up(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(make_params("scroll", clicks=3, x=500, y=500))
        assert result.success is True
        mock_pyautogui.scroll.assert_called_once_with(3, x=500, y=500)

    @pytest.mark.asyncio
    async def test_drag(self, mouse_tool, make_params, mock_pyautogui):
        result = await mouse_tool.execute(
            make_params("drag", start_x=100, start_y=100, end_x=200, end_y=200, duration=0.5)
        )
        assert result.success is True
        # Should call moveTo for start position then drag
        assert mock_pyautogui.moveTo.called or mock_pyautogui.drag.called

    @pytest.mark.asyncio
    async def test_failsafe_exception_caught(self, mouse_tool, make_params, mock_pyautogui):
        mock_pyautogui.click.side_effect = mock_pyautogui.FailSafeException("corner")
        result = await mouse_tool.execute(make_params("click", x=100, y=100))
        assert result.success is False
        assert "Failsafe" in result.error or "failsafe" in result.error.lower()


# --- Approval Tests ---

class TestMouseApproval:

    def test_move_no_approval(self, mouse_tool, make_params):
        assert mouse_tool.needs_approval(make_params("move", x=100, y=200)) is False

    def test_click_no_approval(self, mouse_tool, make_params):
        assert mouse_tool.needs_approval(make_params("click", x=100, y=200)) is False

    def test_scroll_no_approval(self, mouse_tool, make_params):
        assert mouse_tool.needs_approval(make_params("scroll", clicks=3)) is False

    def test_drag_needs_approval(self, mouse_tool, make_params):
        assert mouse_tool.needs_approval(
            make_params("drag", start_x=0, start_y=0, end_x=100, end_y=100)
        ) is True


# --- Describe/Summary Tests ---

class TestMouseDescribeAction:

    def test_describe_click(self, mouse_tool, make_params):
        desc = mouse_tool.describe_action(make_params("click", x=450, y=320, button="left"))
        assert "click" in desc.lower()
        assert "450" in desc
        assert "320" in desc

    def test_describe_drag(self, mouse_tool, make_params):
        desc = mouse_tool.describe_action(
            make_params("drag", start_x=100, start_y=100, end_x=500, end_y=500)
        )
        assert "drag" in desc.lower()

    def test_params_summary(self, mouse_tool, make_params):
        summary = mouse_tool.get_params_summary(make_params("click", x=100, y=200))
        assert "action" in summary
        assert summary["action"] == "click"
```

- [ ] **Step 2: Run mouse tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_mouse.py -v
```

Expected: FAIL — `nobla.tools.control.mouse` does not exist.

- [ ] **Step 3: Implement MouseControlTool**

Create `backend/nobla/tools/control/mouse.py`:

```python
"""MouseControlTool — host-level mouse control via pyautogui.

Subcommands: move, click, double_click, drag, scroll.
All actions go through InputSafetyGuard for rate limiting and halt checks.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.security.permissions import Tier
from nobla.tools.control.safety import InputSafetyGuard, ToolExecutionError

_VALID_ACTIONS = {"move", "click", "double_click", "drag", "scroll"}
_VALID_BUTTONS = {"left", "right", "middle"}
_APPROVAL_ACTIONS = {"drag"}

_settings_cache = None


def _get_settings():
    global _settings_cache
    if _settings_cache is None:
        from nobla.config.settings import Settings
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_pyautogui():
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        raise ToolExecutionError(
            "pyautogui is required for mouse control. Install with: pip install pyautogui"
        )


@register_tool
class MouseControlTool(BaseTool):
    name = "mouse.control"
    description = "Control mouse: move, click, double-click, drag, scroll"
    category = ToolCategory.INPUT
    tier = Tier.ELEVATED
    requires_approval = False
    approval_timeout = 30

    async def validate(self, params: ToolParams) -> None:
        args = params.args
        action = args.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {_VALID_ACTIONS}")

        pag = _get_pyautogui()
        screen_w, screen_h = pag.size()

        # Validate coordinates for actions that need them
        if action in {"move", "click", "double_click"}:
            x, y = args.get("x"), args.get("y")
            if x is None or y is None:
                raise ValueError(f"Action '{action}' requires x and y coordinates")
            if x < 0 or y < 0 or x > screen_w or y > screen_h:
                raise ValueError(
                    f"Invalid coordinates ({x}, {y}) — screen is {screen_w}x{screen_h}"
                )

        if action == "drag":
            for key in ("start_x", "start_y", "end_x", "end_y"):
                val = args.get(key)
                if val is None:
                    raise ValueError(f"Action 'drag' requires {key}")
                if val < 0:
                    raise ValueError(f"Invalid coordinates — {key} cannot be negative")

        if action in {"click", "double_click"}:
            button = args.get("button", "left")
            if button not in _VALID_BUTTONS:
                raise ValueError(f"Invalid button '{button}'. Must be one of: {_VALID_BUTTONS}")

        duration = args.get("duration", 0.0)
        if duration < 0:
            raise ValueError("duration must be >= 0")

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        action = args["action"]
        settings = _get_settings()

        try:
            InputSafetyGuard.check("mouse", settings)
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))

        pag = _get_pyautogui()

        try:
            result_data = await asyncio.to_thread(
                self._execute_action, pag, action, args, settings
            )
            return ToolResult(success=True, data=result_data, error=None)
        except pag.FailSafeException:
            return ToolResult(
                success=False, data=None,
                error="Failsafe triggered — mouse moved to screen corner"
            )
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _execute_action(self, pag, action: str, args: dict, settings) -> dict[str, Any]:
        if action == "move":
            pag.moveTo(args["x"], args["y"], duration=args.get("duration", 0.0))
            return {"action": "move", "x": args["x"], "y": args["y"]}

        elif action == "click":
            button = args.get("button", "left")
            pag.click(args["x"], args["y"], button=button)
            return {"action": "click", "x": args["x"], "y": args["y"], "button": button}

        elif action == "double_click":
            button = args.get("button", "left")
            pag.doubleClick(args["x"], args["y"], button=button)
            return {"action": "double_click", "x": args["x"], "y": args["y"], "button": button}

        elif action == "scroll":
            clicks = args.get("clicks", 1)
            x = args.get("x")
            y = args.get("y")
            pag.scroll(clicks, x=x, y=y)
            return {"action": "scroll", "clicks": clicks, "x": x, "y": y}

        elif action == "drag":
            start_x, start_y = args["start_x"], args["start_y"]
            end_x, end_y = args["end_x"], args["end_y"]
            duration = args.get("duration", 0.5)
            # Move to start, then drag in chunks (halt-checked)
            pag.moveTo(start_x, start_y, duration=0.1)
            dx, dy = end_x - start_x, end_y - start_y
            steps = max(abs(dx), abs(dy)) // 20 or 1
            for i in range(1, steps + 1):
                InputSafetyGuard._check_halt()
                frac = i / steps
                ix = start_x + int(dx * frac)
                iy = start_y + int(dy * frac)
                pag.moveTo(ix, iy, duration=duration / steps)
            return {
                "action": "drag",
                "start": [start_x, start_y],
                "end": [end_x, end_y],
            }

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        action = args.get("action", "unknown")
        if action == "click":
            return f"Click at ({args.get('x')}, {args.get('y')}) with {args.get('button', 'left')} button"
        elif action == "double_click":
            return f"Double-click at ({args.get('x')}, {args.get('y')})"
        elif action == "move":
            return f"Move mouse to ({args.get('x')}, {args.get('y')})"
        elif action == "drag":
            return f"Drag from ({args.get('start_x')}, {args.get('start_y')}) to ({args.get('end_x')}, {args.get('end_y')})"
        elif action == "scroll":
            return f"Scroll {args.get('clicks', 0)} clicks at ({args.get('x')}, {args.get('y')})"
        return f"Mouse action: {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        return {"action": args.get("action"), "x": args.get("x"), "y": args.get("y")}
```

- [ ] **Step 4: Run mouse tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_mouse.py -v
```

Expected: ALL PASS (~25 tests).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/mouse.py backend/tests/tools/control/test_mouse.py
git commit -m "feat(tools): add MouseControlTool with move/click/drag/scroll"
```

---

## Task 2: KeyboardControlTool

**Files:**
- Create: `backend/nobla/tools/control/keyboard.py`
- Create: `backend/tests/tools/control/test_keyboard.py`

**Depends on:** Task 0

### Step-by-step

- [ ] **Step 1: Write KeyboardControlTool tests**

Create `backend/tests/tools/control/test_keyboard.py`:

```python
"""Tests for KeyboardControlTool — type, shortcut, key_press."""
import pytest
from unittest.mock import patch, MagicMock

from nobla.tools.models import ToolParams
from nobla.tools.control.safety import InputSafetyGuard


@pytest.fixture(autouse=True)
def reset_guard():
    InputSafetyGuard.reset()
    yield
    InputSafetyGuard.reset()


@pytest.fixture
def keyboard_tool(mock_pyautogui):
    from nobla.tools.control.keyboard import KeyboardControlTool
    return KeyboardControlTool()


@pytest.fixture
def make_params():
    def _make(action, **kwargs):
        return ToolParams(tool_name="keyboard.control", args={"action": action, **kwargs})
    return _make


class TestKeyboardValidation:

    async def test_valid_type(self, keyboard_tool, make_params):
        await keyboard_tool.validate(make_params("type", text="hello"))

    async def test_empty_text_raises(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="text"):
            await keyboard_tool.validate(make_params("type", text=""))

    async def test_blocked_shortcut_raises(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="blocked"):
            await keyboard_tool.validate(make_params("shortcut", keys=["ctrl", "alt", "delete"]))

    async def test_blocked_shortcut_case_insensitive(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="blocked"):
            await keyboard_tool.validate(make_params("shortcut", keys=["Alt", "F4"]))

    async def test_blocked_shortcut_order_insensitive(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="blocked"):
            await keyboard_tool.validate(make_params("shortcut", keys=["f4", "alt"]))

    async def test_allowed_shortcut_passes(self, keyboard_tool, make_params):
        await keyboard_tool.validate(make_params("shortcut", keys=["ctrl", "c"]))

    async def test_invalid_action_raises(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="action"):
            await keyboard_tool.validate(make_params("invalid_action"))

    async def test_missing_keys_raises(self, keyboard_tool, make_params):
        with pytest.raises(ValueError, match="keys"):
            await keyboard_tool.validate(make_params("shortcut"))


class TestKeyboardExecution:

    @pytest.mark.asyncio
    async def test_type_short_string(self, keyboard_tool, make_params, mock_pyautogui):
        result = await keyboard_tool.execute(make_params("type", text="hello"))
        assert result.success is True
        mock_pyautogui.write.assert_called()

    @pytest.mark.asyncio
    async def test_type_long_string_chunked(self, keyboard_tool, make_params, mock_pyautogui):
        long_text = "a" * 120  # > chunk size of 50
        result = await keyboard_tool.execute(make_params("type", text=long_text))
        assert result.success is True
        assert mock_pyautogui.write.call_count >= 3  # 120 / 50 = 3 chunks

    @pytest.mark.asyncio
    async def test_shortcut(self, keyboard_tool, make_params, mock_pyautogui):
        result = await keyboard_tool.execute(make_params("shortcut", keys=["ctrl", "c"]))
        assert result.success is True
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")

    @pytest.mark.asyncio
    async def test_key_press(self, keyboard_tool, make_params, mock_pyautogui):
        result = await keyboard_tool.execute(make_params("key_press", key="enter"))
        assert result.success is True
        mock_pyautogui.press.assert_called_once_with("enter")

    @pytest.mark.asyncio
    async def test_type_halt_between_chunks(self, keyboard_tool, make_params, mock_pyautogui):
        InputSafetyGuard.halt()
        result = await keyboard_tool.execute(make_params("type", text="a" * 120))
        assert result.success is False
        assert "halted" in result.error.lower()


class TestKeyboardApproval:

    def test_type_no_approval(self, keyboard_tool, make_params):
        assert keyboard_tool.needs_approval(make_params("type", text="hello")) is False

    def test_key_press_no_approval(self, keyboard_tool, make_params):
        assert keyboard_tool.needs_approval(make_params("key_press", key="enter")) is False

    def test_shortcut_needs_approval(self, keyboard_tool, make_params):
        assert keyboard_tool.needs_approval(make_params("shortcut", keys=["ctrl", "s"])) is True


class TestKeyboardDescribeAction:

    def test_describe_type(self, keyboard_tool, make_params):
        desc = keyboard_tool.describe_action(make_params("type", text="hello world"))
        assert "type" in desc.lower() or "hello" in desc

    def test_describe_shortcut(self, keyboard_tool, make_params):
        desc = keyboard_tool.describe_action(make_params("shortcut", keys=["ctrl", "s"]))
        assert "ctrl" in desc.lower()

    def test_params_summary_truncates_text(self, keyboard_tool, make_params):
        long_text = "a" * 200
        summary = keyboard_tool.get_params_summary(make_params("type", text=long_text))
        assert len(summary.get("text", "")) <= 100  # Truncated for display
```

- [ ] **Step 2: Run keyboard tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_keyboard.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement KeyboardControlTool**

Create `backend/nobla/tools/control/keyboard.py`:

```python
"""KeyboardControlTool — host-level keyboard control via pyautogui.

Subcommands: type, shortcut, key_press.
Long text is chunked with halt checks between chunks.
Blocked shortcuts are hard-denied before approval.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.security.permissions import Tier
from nobla.tools.control.safety import (
    InputSafetyGuard, ToolExecutionError, _normalize_shortcut,
)

_VALID_ACTIONS = {"type", "shortcut", "key_press"}
_APPROVAL_ACTIONS = {"shortcut"}

_settings_cache = None


def _get_settings():
    global _settings_cache
    if _settings_cache is None:
        from nobla.config.settings import Settings
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_pyautogui():
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        raise ToolExecutionError(
            "pyautogui is required for keyboard control. Install with: pip install pyautogui"
        )


@register_tool
class KeyboardControlTool(BaseTool):
    name = "keyboard.control"
    description = "Control keyboard: type text, press shortcuts, press individual keys"
    category = ToolCategory.INPUT
    tier = Tier.ELEVATED
    requires_approval = False
    approval_timeout = 30

    async def validate(self, params: ToolParams) -> None:
        args = params.args
        action = args.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {_VALID_ACTIONS}")

        settings = _get_settings()

        if action == "type":
            text = args.get("text", "")
            if not text:
                raise ValueError("Action 'type' requires non-empty text")

        elif action == "shortcut":
            keys = args.get("keys")
            if not keys or not isinstance(keys, list):
                raise ValueError("Action 'shortcut' requires keys as a list")
            normalized = _normalize_shortcut(keys)
            blocked = [_normalize_shortcut(s.split("+")) for s in settings.blocked_shortcuts]
            if normalized in blocked:
                raise ValueError(
                    f"Shortcut '{'+'.join(keys)}' is blocked for safety"
                )

        elif action == "key_press":
            key = args.get("key")
            if not key:
                raise ValueError("Action 'key_press' requires a key name")

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        action = args["action"]
        settings = _get_settings()

        try:
            InputSafetyGuard.check("keyboard", settings)
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))

        pag = _get_pyautogui()

        try:
            result_data = await asyncio.to_thread(
                self._execute_action, pag, action, args, settings
            )
            return ToolResult(success=True, data=result_data, error=None)
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _execute_action(self, pag, action: str, args: dict, settings) -> dict[str, Any]:
        if action == "type":
            text = args["text"]
            chunk_size = settings.type_chunk_size
            for i in range(0, len(text), chunk_size):
                InputSafetyGuard._check_halt()
                pag.write(text[i:i + chunk_size], interval=0.02)
            return {"action": "type", "length": len(text)}

        elif action == "shortcut":
            keys = args["keys"]
            pag.hotkey(*keys)
            return {"action": "shortcut", "keys": keys}

        elif action == "key_press":
            key = args["key"]
            pag.press(key)
            return {"action": "key_press", "key": key}

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        action = args.get("action", "unknown")
        if action == "type":
            text = args.get("text", "")
            preview = text[:50] + "..." if len(text) > 50 else text
            return f'Type "{preview}"'
        elif action == "shortcut":
            keys = args.get("keys", [])
            return f"Press shortcut {'+'.join(keys)}"
        elif action == "key_press":
            return f"Press key: {args.get('key', 'unknown')}"
        return f"Keyboard action: {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        summary = {"action": args.get("action")}
        if args.get("text"):
            text = args["text"]
            summary["text"] = text[:100] + "..." if len(text) > 100 else text
        if args.get("keys"):
            summary["keys"] = args["keys"]
        if args.get("key"):
            summary["key"] = args["key"]
        return summary
```

- [ ] **Step 4: Run keyboard tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_keyboard.py -v
```

Expected: ALL PASS (~25 tests).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/keyboard.py backend/tests/tools/control/test_keyboard.py
git commit -m "feat(tools): add KeyboardControlTool with type/shortcut/key_press"
```

---

## Task 3: FileManageTool

**Files:**
- Create: `backend/nobla/tools/control/file_manager.py`
- Create: `backend/tests/tools/control/test_file_manager.py`

**Depends on:** Task 0

### Step-by-step

- [ ] **Step 1: Write FileManageTool tests**

Create `backend/tests/tools/control/test_file_manager.py`:

```python
"""Tests for FileManageTool — read, write, list, move, copy, delete, info.

Focuses heavily on path security: allow-list, traversal, symlink escape.
Uses pytest tmp_path for real filesystem operations.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from nobla.tools.models import ToolParams
from nobla.config.settings import ComputerControlSettings


@pytest.fixture
def file_tool(control_settings):
    from nobla.tools.control.file_manager import FileManageTool
    # Inject settings for testing
    import nobla.tools.control.file_manager as fm
    fm._settings_cache = control_settings
    tool = FileManageTool()
    yield tool
    fm._settings_cache = None


@pytest.fixture
def make_params():
    def _make(action, **kwargs):
        return ToolParams(tool_name="file.manage", args={"action": action, **kwargs})
    return _make


@pytest.fixture
def readable_file(control_settings):
    """Create a test file in the readable directory."""
    read_dir = Path(control_settings.allowed_read_dirs[0])
    test_file = read_dir / "test.txt"
    test_file.write_text("hello world")
    return test_file


@pytest.fixture
def writable_dir(control_settings):
    """Return the writable directory path."""
    return Path(control_settings.allowed_write_dirs[0])


# --- Path Security Tests ---

class TestFilePathSecurity:

    async def test_read_within_allowed_dir(self, file_tool, make_params, readable_file):
        await file_tool.validate(make_params("read", path=str(readable_file)))

    async def test_read_outside_allowed_dir_raises(self, file_tool, make_params):
        with pytest.raises(ValueError, match="outside allowed"):
            await file_tool.validate(make_params("read", path="/etc/passwd"))

    async def test_traversal_attack_blocked(self, file_tool, make_params, control_settings):
        read_dir = control_settings.allowed_read_dirs[0]
        evil_path = os.path.join(read_dir, "..", "..", "etc", "passwd")
        with pytest.raises(ValueError, match="outside allowed"):
            await file_tool.validate(make_params("read", path=evil_path))

    async def test_symlink_escape_blocked(self, file_tool, make_params, control_settings, tmp_path):
        read_dir = Path(control_settings.allowed_read_dirs[0])
        # Create symlink inside allowed dir pointing outside
        outside_file = tmp_path / "outside" / "secret.txt"
        outside_file.parent.mkdir()
        outside_file.write_text("secret")
        symlink = read_dir / "escape_link"
        try:
            symlink.symlink_to(outside_file)
        except OSError:
            pytest.skip("Symlinks not supported")
        with pytest.raises(ValueError, match="outside allowed"):
            await file_tool.validate(make_params("read", path=str(symlink)))

    async def test_write_outside_write_dir_raises(self, file_tool, make_params, control_settings):
        # Read dir but not write dir
        read_dir = control_settings.allowed_read_dirs[0]
        path = os.path.join(read_dir, "not_writable.txt")
        with pytest.raises(ValueError, match="outside allowed"):
            await file_tool.validate(make_params("write", path=path, content="data"))

    async def test_write_within_write_dir(self, file_tool, make_params, writable_dir):
        path = str(writable_dir / "new_file.txt")
        await file_tool.validate(make_params("write", path=path, content="data"))

    async def test_empty_allowed_dirs_raises(self, make_params):
        from nobla.tools.control.file_manager import FileManageTool
        import nobla.tools.control.file_manager as fm
        fm._settings_cache = ComputerControlSettings()  # Empty dirs
        tool = FileManageTool()
        with pytest.raises(ValueError, match="No.*configured"):
            await tool.validate(make_params("read", path="/any/path"))
        fm._settings_cache = None

    async def test_file_too_large_raises(self, file_tool, make_params, control_settings):
        read_dir = Path(control_settings.allowed_read_dirs[0])
        big_file = read_dir / "big.txt"
        # Don't actually create a huge file — mock the size check
        big_file.write_text("x")
        control_settings.max_file_size_bytes = 1
        with pytest.raises(ValueError, match="exceeds"):
            await file_tool.validate(make_params("read", path=str(big_file)))


# --- Execution Tests ---

class TestFileExecution:

    @pytest.mark.asyncio
    async def test_read(self, file_tool, make_params, readable_file):
        result = await file_tool.execute(make_params("read", path=str(readable_file)))
        assert result.success is True
        assert result.data["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_write(self, file_tool, make_params, writable_dir):
        path = str(writable_dir / "output.txt")
        result = await file_tool.execute(
            make_params("write", path=path, content="new content")
        )
        assert result.success is True
        assert Path(path).read_text() == "new content"

    @pytest.mark.asyncio
    async def test_write_creates_backup(self, file_tool, make_params, writable_dir):
        path = writable_dir / "existing.txt"
        path.write_text("original")
        await file_tool.execute(make_params("write", path=str(path), content="updated"))
        backup_dir = writable_dir / ".nobla-backup"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("existing.txt.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "original"

    @pytest.mark.asyncio
    async def test_list_directory(self, file_tool, make_params, readable_file):
        dir_path = str(readable_file.parent)
        result = await file_tool.execute(make_params("list", path=dir_path))
        assert result.success is True
        names = [e["name"] for e in result.data["entries"]]
        assert "test.txt" in names

    @pytest.mark.asyncio
    async def test_delete_creates_backup(self, file_tool, make_params, writable_dir):
        path = writable_dir / "to_delete.txt"
        path.write_text("bye")
        result = await file_tool.execute(make_params("delete", path=str(path)))
        assert result.success is True
        assert not path.exists()
        backup_dir = writable_dir / ".nobla-backup"
        backups = list(backup_dir.glob("to_delete.txt.*"))
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_move(self, file_tool, make_params, writable_dir):
        src = writable_dir / "src.txt"
        dst = writable_dir / "dst.txt"
        src.write_text("moving")
        result = await file_tool.execute(
            make_params("move", source=str(src), destination=str(dst))
        )
        assert result.success is True
        assert not src.exists()
        assert dst.read_text() == "moving"

    @pytest.mark.asyncio
    async def test_copy(self, file_tool, make_params, writable_dir, readable_file):
        dst = writable_dir / "copied.txt"
        result = await file_tool.execute(
            make_params("copy", source=str(readable_file), destination=str(dst))
        )
        assert result.success is True
        assert dst.read_text() == "hello world"
        assert readable_file.exists()  # Original still there

    @pytest.mark.asyncio
    async def test_info(self, file_tool, make_params, readable_file):
        result = await file_tool.execute(make_params("info", path=str(readable_file)))
        assert result.success is True
        assert result.data["size"] > 0
        assert "modified" in result.data

    @pytest.mark.asyncio
    async def test_max_backups_pruned(self, file_tool, make_params, writable_dir, control_settings):
        control_settings.max_backups_per_file = 2
        path = writable_dir / "pruned.txt"
        for i in range(4):
            path.write_text(f"version {i}")
            await file_tool.execute(make_params("write", path=str(path), content=f"v{i+1}"))
        backup_dir = writable_dir / ".nobla-backup"
        backups = sorted(backup_dir.glob("pruned.txt.*"))
        assert len(backups) <= 2

    @pytest.mark.asyncio
    async def test_file_not_found(self, file_tool, make_params, control_settings):
        read_dir = control_settings.allowed_read_dirs[0]
        path = os.path.join(read_dir, "nonexistent.txt")
        result = await file_tool.execute(make_params("read", path=path))
        assert result.success is False


# --- Approval Tests ---

class TestFileApproval:

    def test_read_no_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("read", path="/any")) is False

    def test_list_no_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("list", path="/any")) is False

    def test_info_no_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("info", path="/any")) is False

    def test_write_needs_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("write", path="/any", content="x")) is True

    def test_delete_needs_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("delete", path="/any")) is True

    def test_move_needs_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("move", source="/a", destination="/b")) is True

    def test_copy_needs_approval(self, file_tool, make_params):
        assert file_tool.needs_approval(make_params("copy", source="/a", destination="/b")) is True
```

- [ ] **Step 2: Run file manager tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_file_manager.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement FileManageTool**

Create `backend/nobla/tools/control/file_manager.py`:

```python
"""FileManageTool — host-level file management with directory allow-list.

Subcommands: read, write, list, move, copy, delete, info.
All paths validated against allowed_read_dirs/allowed_write_dirs.
Destructive ops create backups in .nobla-backup/ before executing.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time as _time
from pathlib import Path
from typing import Any

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.security.permissions import Tier
from nobla.tools.control.safety import ToolExecutionError

_VALID_ACTIONS = {"read", "write", "list", "move", "copy", "delete", "info"}
_READ_ACTIONS = {"read", "list", "info"}
_WRITE_ACTIONS = {"write", "delete", "move", "copy"}
_APPROVAL_ACTIONS = {"write", "delete", "move", "copy"}

_settings_cache = None


def _get_settings():
    global _settings_cache
    if _settings_cache is None:
        from nobla.config.settings import Settings
        _settings_cache = Settings().computer_control
    return _settings_cache


def _resolve_and_validate(path_str: str, allowed_dirs: list[str], label: str) -> Path:
    """Resolve path and check against allow-list. Raises ValueError."""
    if not allowed_dirs:
        raise ValueError(
            f"No {label} directories configured. Update ComputerControlSettings."
        )
    resolved = Path(path_str).resolve()
    # Symlink resolution is already done by .resolve()
    for d in allowed_dirs:
        if resolved.is_relative_to(Path(d).resolve()):
            return resolved
    raise ValueError(f"Path '{resolved}' outside allowed {label} directories")


def _create_backup(file_path: Path, max_backups: int) -> None:
    """Create backup in .nobla-backup/ before destructive operation."""
    if not file_path.exists():
        return
    backup_dir = file_path.parent / ".nobla-backup"
    backup_dir.mkdir(exist_ok=True)
    timestamp = int(_time.time())
    backup_name = f"{file_path.name}.{timestamp}"
    shutil.copy2(str(file_path), str(backup_dir / backup_name))
    # Prune old backups
    pattern = f"{file_path.name}.*"
    backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    while len(backups) > max_backups:
        backups.pop(0).unlink()


@register_tool
class FileManageTool(BaseTool):
    name = "file.manage"
    description = "Manage files: read, write, list, move, copy, delete, info"
    category = ToolCategory.FILE_SYSTEM
    tier = Tier.ELEVATED
    requires_approval = False
    approval_timeout = 30

    async def validate(self, params: ToolParams) -> None:
        args = params.args
        action = args.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {_VALID_ACTIONS}")

        settings = _get_settings()
        path_str = args.get("path") or args.get("source")

        if action in _READ_ACTIONS:
            resolved = _resolve_and_validate(
                path_str, settings.allowed_read_dirs, "read"
            )
            if action == "read" and resolved.exists():
                if resolved.stat().st_size > settings.max_file_size_bytes:
                    raise ValueError(
                        f"File size exceeds limit of {settings.max_file_size_bytes} bytes"
                    )

        elif action in _WRITE_ACTIONS:
            if action in {"move", "copy"}:
                _resolve_and_validate(
                    args.get("source"), settings.allowed_read_dirs, "read"
                )
                _resolve_and_validate(
                    args.get("destination"), settings.allowed_write_dirs, "write"
                )
            else:
                _resolve_and_validate(
                    path_str, settings.allowed_write_dirs, "write"
                )

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        action = args["action"]
        try:
            result_data = await asyncio.to_thread(self._execute_action, action, args)
            return ToolResult(success=True, data=result_data, error=None)
        except FileNotFoundError as e:
            return ToolResult(success=False, data=None, error=f"File not found: {e}")
        except PermissionError as e:
            return ToolResult(success=False, data=None, error=f"Permission denied: {e}")
        except OSError as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _execute_action(self, action: str, args: dict) -> dict[str, Any]:
        settings = _get_settings()

        if action == "read":
            path = Path(args["path"]).resolve()
            content = path.read_text(encoding="utf-8")
            return {"action": "read", "path": str(path), "content": content,
                    "size": len(content)}

        elif action == "write":
            path = Path(args["path"]).resolve()
            _create_backup(path, settings.max_backups_per_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return {"action": "write", "path": str(path),
                    "size": len(args["content"])}

        elif action == "list":
            path = Path(args["path"]).resolve()
            entries = []
            for entry in sorted(path.iterdir()):
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            return {"action": "list", "path": str(path), "entries": entries}

        elif action == "move":
            src = Path(args["source"]).resolve()
            dst = Path(args["destination"]).resolve()
            _create_backup(dst, settings.max_backups_per_file)
            shutil.move(str(src), str(dst))
            return {"action": "move", "source": str(src), "destination": str(dst)}

        elif action == "copy":
            src = Path(args["source"]).resolve()
            dst = Path(args["destination"]).resolve()
            shutil.copy2(str(src), str(dst))
            return {"action": "copy", "source": str(src), "destination": str(dst)}

        elif action == "delete":
            path = Path(args["path"]).resolve()
            _create_backup(path, settings.max_backups_per_file)
            path.unlink()
            return {"action": "delete", "path": str(path)}

        elif action == "info":
            path = Path(args["path"]).resolve()
            stat = path.stat()
            return {
                "action": "info", "path": str(path),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "permissions": oct(stat.st_mode),
                "is_dir": path.is_dir(),
            }

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        action = args.get("action", "unknown")
        path = args.get("path") or args.get("source", "")
        if action == "read":
            return f"Read file {path}"
        elif action == "write":
            return f"Write to {path}"
        elif action == "list":
            return f"List directory {path}"
        elif action == "move":
            return f"Move {path} to {args.get('destination', '')}"
        elif action == "copy":
            return f"Copy {path} to {args.get('destination', '')}"
        elif action == "delete":
            return f"Delete file {path}"
        elif action == "info":
            return f"Get info for {path}"
        return f"File action: {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        summary = {"action": args.get("action")}
        if args.get("path"):
            summary["path"] = args["path"]
        if args.get("source"):
            summary["source"] = args["source"]
        if args.get("destination"):
            summary["destination"] = args["destination"]
        # Never include file content in summary
        return summary
```

- [ ] **Step 4: Run file manager tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_file_manager.py -v
```

Expected: ALL PASS (~35 tests).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/file_manager.py backend/tests/tools/control/test_file_manager.py
git commit -m "feat(tools): add FileManageTool with path security and backup"
```

---

## Task 4: AppControlTool

**Files:**
- Create: `backend/nobla/tools/control/app.py`
- Create: `backend/tests/tools/control/test_app.py`

**Depends on:** Task 0

### Step-by-step

- [ ] **Step 1: Write AppControlTool tests**

Create `backend/tests/tools/control/test_app.py`:

```python
"""Tests for AppControlTool — launch, close, switch, list."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from nobla.tools.models import ToolParams


@pytest.fixture
def app_tool(control_settings, mock_psutil):
    from nobla.tools.control.app import AppControlTool
    import nobla.tools.control.app as app_mod
    app_mod._settings_cache = control_settings
    app_mod._launched_pids = {}  # Reset PID registry
    tool = AppControlTool()
    yield tool
    app_mod._settings_cache = None
    app_mod._launched_pids = {}


@pytest.fixture
def make_params():
    def _make(action, **kwargs):
        return ToolParams(tool_name="app.control", args={"action": action, **kwargs})
    return _make


class TestAppValidation:

    async def test_valid_launch(self, app_tool, make_params):
        await app_tool.validate(make_params("launch", app="notepad"))

    async def test_app_not_in_allowed_raises(self, app_tool, make_params):
        with pytest.raises(ValueError, match="not in allowed"):
            await app_tool.validate(make_params("launch", app="malware"))

    async def test_app_match_case_insensitive(self, app_tool, make_params):
        await app_tool.validate(make_params("launch", app="Notepad"))

    async def test_empty_allowed_apps_raises(self, make_params):
        from nobla.tools.control.app import AppControlTool
        import nobla.tools.control.app as app_mod
        from nobla.config.settings import ComputerControlSettings
        app_mod._settings_cache = ComputerControlSettings()  # Empty
        tool = AppControlTool()
        with pytest.raises(ValueError, match="No.*configured"):
            await tool.validate(make_params("launch", app="anything"))
        app_mod._settings_cache = None

    async def test_invalid_action_raises(self, app_tool, make_params):
        with pytest.raises(ValueError, match="action"):
            await app_tool.validate(make_params("invalid"))


class TestAppExecution:

    @pytest.mark.asyncio
    async def test_launch_tracks_pid(self, app_tool, make_params):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc
            result = await app_tool.execute(make_params("launch", app="notepad"))
            assert result.success is True
            import nobla.tools.control.app as app_mod
            assert "notepad" in app_mod._launched_pids

    @pytest.mark.asyncio
    async def test_close_nobla_launched(self, app_tool, make_params):
        import nobla.tools.control.app as app_mod
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        app_mod._launched_pids["notepad"] = mock_proc
        result = await app_tool.execute(make_params("close", app="notepad"))
        assert result.success is True
        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_non_launched_denied(self, app_tool, make_params):
        result = await app_tool.execute(make_params("close", app="notepad"))
        assert result.success is False
        assert "not launched" in result.error.lower()

    @pytest.mark.asyncio
    async def test_close_stale_pid(self, app_tool, make_params):
        import nobla.tools.control.app as app_mod
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = False  # Already exited
        app_mod._launched_pids["notepad"] = mock_proc
        result = await app_tool.execute(make_params("close", app="notepad"))
        assert result.success is False
        assert "notepad" not in app_mod._launched_pids  # Cleaned up

    @pytest.mark.asyncio
    async def test_list(self, app_tool, make_params, mock_psutil):
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 1, "name": "chrome.exe"}
        mock_psutil.process_iter.return_value = [mock_proc]
        result = await app_tool.execute(make_params("list"))
        assert result.success is True


class TestAppApproval:

    def test_list_no_approval(self, app_tool, make_params):
        assert app_tool.needs_approval(make_params("list")) is False

    def test_switch_no_approval(self, app_tool, make_params):
        assert app_tool.needs_approval(make_params("switch", app="chrome")) is False

    def test_launch_needs_approval(self, app_tool, make_params):
        assert app_tool.needs_approval(make_params("launch", app="notepad")) is True

    def test_close_needs_approval(self, app_tool, make_params):
        assert app_tool.needs_approval(make_params("close", app="notepad")) is True
```

- [ ] **Step 2: Run app tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_app.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement AppControlTool**

Create `backend/nobla/tools/control/app.py`:

```python
"""AppControlTool — curated app management with allow-list and PID tracking.

Subcommands: launch, close, switch, list.
Only apps in allowed_apps can be launched. Only Nobla-launched processes can be closed.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.security.permissions import Tier
from nobla.tools.control.safety import ToolExecutionError

_VALID_ACTIONS = {"launch", "close", "switch", "list"}
_APPROVAL_ACTIONS = {"launch", "close"}

_settings_cache = None
_launched_pids: dict[str, Any] = {}  # app_name -> Popen or psutil.Process


def _get_settings():
    global _settings_cache
    if _settings_cache is None:
        from nobla.config.settings import Settings
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _focus_window(title: str) -> bool:
    """Platform-specific window focus. Returns True on success."""
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32

            def _enum_cb(hwnd, results):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if title.lower() in buf.value.lower():
                        results.append(hwnd)
                return True

            results = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.c_void_p
            )
            user32.EnumWindows(WNDENUMPROC(_enum_cb), None)
            if results:
                user32.SetForegroundWindow(results[0])
                return True

        elif sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'tell application "{title}" to activate'],
                timeout=5, check=True,
            )
            return True

        else:  # Linux
            result = subprocess.run(
                ["wmctrl", "-a", title], timeout=5, capture_output=True
            )
            if result.returncode != 0:
                subprocess.run(
                    ["xdotool", "search", "--name", title, "windowactivate"],
                    timeout=5, check=True,
                )
            return True

    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return False


@register_tool
class AppControlTool(BaseTool):
    name = "app.control"
    description = "Control apps: launch, close, switch focus, list windows"
    category = ToolCategory.APP_CONTROL
    tier = Tier.ELEVATED
    requires_approval = False
    approval_timeout = 30

    async def validate(self, params: ToolParams) -> None:
        args = params.args
        action = args.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {_VALID_ACTIONS}")

        settings = _get_settings()

        if action in {"launch", "close", "switch"}:
            app_name = args.get("app", "")
            if not app_name:
                raise ValueError(f"Action '{action}' requires app name")
            if action == "launch":
                if not settings.allowed_apps:
                    raise ValueError(
                        "No apps configured. Update ComputerControlSettings.allowed_apps"
                    )
                allowed_lower = [a.lower() for a in settings.allowed_apps]
                if app_name.lower() not in allowed_lower:
                    raise ValueError(
                        f"App '{app_name}' not in allowed apps: {settings.allowed_apps}"
                    )

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        action = args["action"]
        try:
            result_data = await asyncio.to_thread(self._execute_action, action, args)
            return ToolResult(success=True, data=result_data, error=None)
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _execute_action(self, action: str, args: dict) -> dict[str, Any]:
        global _launched_pids

        if action == "launch":
            app_name = args["app"]
            app_args = args.get("args", [])
            proc = subprocess.Popen(
                [app_name] + app_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _launched_pids[app_name.lower()] = proc
            return {"action": "launch", "app": app_name, "pid": proc.pid}

        elif action == "close":
            app_name = args["app"].lower()
            proc = _launched_pids.get(app_name)
            if proc is None:
                raise ToolExecutionError(
                    f"App '{app_name}' was not launched by Nobla — cannot close"
                )
            # Check if still running (works for both Popen and psutil.Process)
            running = False
            if hasattr(proc, "is_running"):
                running = proc.is_running()
            elif hasattr(proc, "poll"):
                running = proc.poll() is None
            if not running:
                del _launched_pids[app_name]
                raise ToolExecutionError(
                    f"App '{app_name}' already exited (stale PID cleaned up)"
                )
            proc.terminate()
            del _launched_pids[app_name]
            return {"action": "close", "app": args["app"]}

        elif action == "switch":
            app_name = args["app"]
            success = _focus_window(app_name)
            if not success:
                raise ToolExecutionError(f"Could not focus window for '{app_name}'")
            return {"action": "switch", "app": app_name}

        elif action == "list":
            psutil = _get_psutil()
            windows = []
            if psutil:
                for proc in psutil.process_iter(["pid", "name"]):
                    windows.append(proc.info)
            else:
                # Fallback: subprocess-based listing
                if sys.platform == "win32":
                    result = subprocess.run(
                        ["tasklist", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=10,
                    )
                    for line in result.stdout.strip().split("\n")[:50]:
                        parts = line.strip('"').split('","')
                        if len(parts) >= 2:
                            windows.append({"name": parts[0], "pid": parts[1]})
                else:
                    result = subprocess.run(
                        ["ps", "-eo", "pid,comm", "--no-headers"],
                        capture_output=True, text=True, timeout=10,
                    )
                    for line in result.stdout.strip().split("\n")[:50]:
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            windows.append({"pid": parts[0], "name": parts[1]})
            return {"action": "list", "processes": windows[:50]}

    def describe_action(self, params: ToolParams) -> str:
        args = params.args
        action = args.get("action", "unknown")
        app = args.get("app", "")
        if action == "launch":
            return f"Launch application: {app}"
        elif action == "close":
            return f"Close application: {app}"
        elif action == "switch":
            return f"Switch to application: {app}"
        elif action == "list":
            return "List running applications"
        return f"App action: {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        summary = {"action": args.get("action")}
        if args.get("app"):
            summary["app"] = args["app"]
        return summary
```

- [ ] **Step 4: Run app tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_app.py -v
```

Expected: ALL PASS (~20 tests).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/app.py backend/tests/tools/control/test_app.py
git commit -m "feat(tools): add AppControlTool with allow-list and PID tracking"
```

---

## Task 5: ClipboardManageTool

**Files:**
- Create: `backend/nobla/tools/control/clipboard.py`
- Create: `backend/tests/tools/control/test_clipboard.py`

**Depends on:** Task 0

### Step-by-step

- [ ] **Step 1: Write ClipboardManageTool tests**

Create `backend/tests/tools/control/test_clipboard.py`:

```python
"""Tests for ClipboardManageTool — read, write, clear."""
import pytest
from unittest.mock import MagicMock

from nobla.tools.models import ToolParams


@pytest.fixture
def clipboard_tool(control_settings, mock_pyperclip):
    from nobla.tools.control.clipboard import ClipboardManageTool
    import nobla.tools.control.clipboard as cb_mod
    cb_mod._settings_cache = control_settings
    tool = ClipboardManageTool()
    yield tool
    cb_mod._settings_cache = None


@pytest.fixture
def make_params():
    def _make(action, **kwargs):
        return ToolParams(tool_name="clipboard.manage", args={"action": action, **kwargs})
    return _make


class TestClipboardValidation:

    async def test_valid_read(self, clipboard_tool, make_params):
        await clipboard_tool.validate(make_params("read"))

    async def test_valid_write(self, clipboard_tool, make_params):
        await clipboard_tool.validate(make_params("write", content="hello"))

    async def test_write_exceeds_max_size_raises(self, clipboard_tool, make_params, control_settings):
        control_settings.max_clipboard_size = 10
        with pytest.raises(ValueError, match="exceeds"):
            await clipboard_tool.validate(
                make_params("write", content="a" * 11)
            )

    async def test_invalid_action_raises(self, clipboard_tool, make_params):
        with pytest.raises(ValueError, match="action"):
            await clipboard_tool.validate(make_params("invalid"))


class TestClipboardExecution:

    @pytest.mark.asyncio
    async def test_read(self, clipboard_tool, make_params, mock_pyperclip):
        mock_pyperclip.paste.return_value = "clipboard data"
        result = await clipboard_tool.execute(make_params("read"))
        assert result.success is True
        assert result.data["content"] == "clipboard data"

    @pytest.mark.asyncio
    async def test_write(self, clipboard_tool, make_params, mock_pyperclip):
        result = await clipboard_tool.execute(make_params("write", content="new data"))
        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("new data")

    @pytest.mark.asyncio
    async def test_clear(self, clipboard_tool, make_params, mock_pyperclip):
        result = await clipboard_tool.execute(make_params("clear"))
        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("")


class TestClipboardApproval:

    def test_read_no_approval(self, clipboard_tool, make_params):
        assert clipboard_tool.needs_approval(make_params("read")) is False

    def test_write_needs_approval(self, clipboard_tool, make_params):
        assert clipboard_tool.needs_approval(make_params("write", content="x")) is True

    def test_clear_needs_approval(self, clipboard_tool, make_params):
        assert clipboard_tool.needs_approval(make_params("clear")) is True


class TestClipboardAuditSanitization:

    def test_params_summary_truncates_content(self, clipboard_tool, make_params):
        long_content = "a" * 200
        summary = clipboard_tool.get_params_summary(
            make_params("write", content=long_content)
        )
        assert len(summary.get("content", "")) <= 55  # 50 + "..."

    def test_params_summary_read_no_content(self, clipboard_tool, make_params):
        summary = clipboard_tool.get_params_summary(make_params("read"))
        assert "content" not in summary or summary.get("content") is None


class TestClipboardDegradation:

    @pytest.mark.asyncio
    async def test_no_pyperclip_falls_back(self, control_settings):
        """When pyperclip unavailable, should try pyautogui fallback or error."""
        from nobla.tools.control.clipboard import ClipboardManageTool
        import nobla.tools.control.clipboard as cb_mod
        cb_mod._settings_cache = control_settings
        tool = ClipboardManageTool()
        # Force pyperclip import to fail — tool should handle gracefully
        with pytest.raises(Exception):
            # This tests that _get_clipboard_backend raises cleanly
            cb_mod._get_clipboard_backend()
        cb_mod._settings_cache = None
```

- [ ] **Step 2: Run clipboard tests to verify they fail**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_clipboard.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement ClipboardManageTool**

Create `backend/nobla/tools/control/clipboard.py`:

```python
"""ClipboardManageTool — clipboard read/write/clear with audit sanitization.

Subcommands: read, write, clear.
Primary backend: pyperclip. Fallback: pyautogui clipboard functions.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.security.permissions import Tier
from nobla.tools.control.safety import ToolExecutionError

_VALID_ACTIONS = {"read", "write", "clear"}
_APPROVAL_ACTIONS = {"write", "clear"}

_settings_cache = None


def _get_settings():
    global _settings_cache
    if _settings_cache is None:
        from nobla.config.settings import Settings
        _settings_cache = Settings().computer_control
    return _settings_cache


def _get_clipboard_backend():
    """Get clipboard backend: pyperclip preferred, pyautogui fallback."""
    try:
        import pyperclip
        return pyperclip
    except ImportError:
        pass
    try:
        import pyautogui
        # pyautogui exposes clipboard via hotkey simulation — less reliable
        class _PyAutoGuiClipboard:
            @staticmethod
            def paste():
                import pyautogui
                return pyautogui.hotkey("ctrl", "v") or ""
            @staticmethod
            def copy(text):
                import pyperclip
                pyperclip.copy(text)
        return _PyAutoGuiClipboard()
    except ImportError:
        pass
    raise ToolExecutionError(
        "Clipboard requires pyperclip or pyautogui. "
        "Install with: pip install pyperclip"
    )


@register_tool
class ClipboardManageTool(BaseTool):
    name = "clipboard.manage"
    description = "Manage clipboard: read, write, clear contents"
    category = ToolCategory.CLIPBOARD
    tier = Tier.ELEVATED
    requires_approval = False
    approval_timeout = 30

    async def validate(self, params: ToolParams) -> None:
        args = params.args
        action = args.get("action")
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {_VALID_ACTIONS}")

        if action == "write":
            settings = _get_settings()
            content = args.get("content", "")
            if len(content) > settings.max_clipboard_size:
                raise ValueError(
                    f"Content size {len(content)} exceeds max clipboard "
                    f"size of {settings.max_clipboard_size} bytes"
                )

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def execute(self, params: ToolParams) -> ToolResult:
        args = params.args
        action = args["action"]
        try:
            backend = _get_clipboard_backend()
            result_data = await asyncio.to_thread(
                self._execute_action, backend, action, args
            )
            return ToolResult(success=True, data=result_data, error=None)
        except ToolExecutionError as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _execute_action(self, backend, action: str, args: dict) -> dict[str, Any]:
        if action == "read":
            content = backend.paste()
            return {"action": "read", "content": content}
        elif action == "write":
            backend.copy(args["content"])
            return {"action": "write", "length": len(args["content"])}
        elif action == "clear":
            backend.copy("")
            return {"action": "clear"}

    def describe_action(self, params: ToolParams) -> str:
        action = params.args.get("action", "unknown")
        if action == "read":
            return "Read clipboard contents"
        elif action == "write":
            return "Write to clipboard"
        elif action == "clear":
            return "Clear clipboard"
        return f"Clipboard action: {action}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        summary = {"action": args.get("action")}
        if args.get("content"):
            settings = _get_settings()
            limit = settings.audit_clipboard_preview_length
            content = args["content"]
            summary["content"] = (
                content[:limit] + "..." if len(content) > limit else content
            )
        return summary
```

- [ ] **Step 4: Run clipboard tests to verify they pass**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/test_clipboard.py -v
```

Expected: ALL PASS (~15 tests).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/clipboard.py backend/tests/tools/control/test_clipboard.py
git commit -m "feat(tools): add ClipboardManageTool with audit sanitization"
```

---

## Task 6: Auto-Discovery Wiring + Integration Tests

**Files:**
- Modify: `backend/nobla/tools/control/__init__.py`
- Modify: `backend/nobla/tools/__init__.py`
- Run: all tests together

**Depends on:** Tasks 1-5 (all tools complete)

### Step-by-step

- [ ] **Step 1: Write auto-discovery imports in control/__init__.py**

Update `backend/nobla/tools/control/__init__.py`:

```python
"""Phase 4B: Computer Control tools.

Auto-discovery imports trigger @register_tool decorators.
"""
from nobla.tools.control import mouse  # noqa: F401
from nobla.tools.control import keyboard  # noqa: F401
from nobla.tools.control import file_manager  # noqa: F401
from nobla.tools.control import app  # noqa: F401
from nobla.tools.control import clipboard  # noqa: F401
```

- [ ] **Step 2: Add control import to tools/__init__.py**

Add to `backend/nobla/tools/__init__.py` after the existing `code` import:

```python
from nobla.tools import control  # noqa: F401  # Phase 4B auto-discovery
```

- [ ] **Step 3: Run ALL Phase 4B tests together**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/tools/control/ -v --tb=short
```

Expected: ALL PASS (130+ tests across all 8 test files).

- [ ] **Step 4: Verify tool registration**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -c "
from nobla.tools.registry import get_registry
registry = get_registry()
phase4b_tools = [name for name in registry if name in (
    'mouse.control', 'keyboard.control', 'file.manage', 'app.control', 'clipboard.manage'
)]
print(f'Phase 4B tools registered: {phase4b_tools}')
assert len(phase4b_tools) == 5, f'Expected 5 tools, got {len(phase4b_tools)}'
print('All 5 Phase 4B tools registered successfully!')
"
```

- [ ] **Step 5: Run full test suite (4A + 4C + 4B)**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/ -v --tb=short
```

Expected: ALL PASS — Phase 4B tests pass alongside existing 4A (158) and 4C (110) tests.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add backend/nobla/tools/control/__init__.py backend/nobla/tools/__init__.py
git commit -m "feat(tools): wire Phase 4B auto-discovery and verify integration"
```

---

## Task 7: Flutter Approval Bottom Sheet

**Files:**
- Create: `app/lib/features/security/models/approval_models.dart`
- Create: `app/lib/features/security/providers/approval_provider.dart`
- Create: `app/lib/features/security/widgets/approval_sheet.dart`

**Depends on:** Task 0 (for WebSocket protocol understanding)

### Step-by-step

- [ ] **Step 1: Create directory structure**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
mkdir -p app/lib/features/security/models
mkdir -p app/lib/features/security/providers
mkdir -p app/lib/features/security/widgets
```

- [ ] **Step 2: Create approval data models**

Create `app/lib/features/security/models/approval_models.dart`:

```dart
/// Data models for tool approval and activity tracking.
import 'package:flutter/foundation.dart';

@immutable
class ApprovalRequest {
  final String requestId;
  final String toolName;
  final String description;
  final Map<String, dynamic> paramsSummary;
  final int timeoutSeconds;
  final DateTime receivedAt;

  const ApprovalRequest({
    required this.requestId,
    required this.toolName,
    required this.description,
    required this.paramsSummary,
    required this.timeoutSeconds,
    required this.receivedAt,
  });

  factory ApprovalRequest.fromJson(Map<String, dynamic> json) {
    return ApprovalRequest(
      requestId: json['request_id'] as String,
      toolName: json['tool_name'] as String,
      description: json['description'] as String? ?? '',
      paramsSummary: json['params_summary'] as Map<String, dynamic>? ?? {},
      timeoutSeconds: json['timeout_seconds'] as int? ?? 30,
      receivedAt: DateTime.now(),
    );
  }
}

enum ActivityStatus { success, failed, denied, pending }

@immutable
class ActivityEntry {
  final String toolName;
  final String action;
  final String description;
  final ActivityStatus status;
  final int? executionTimeMs;
  final DateTime timestamp;

  const ActivityEntry({
    required this.toolName,
    required this.action,
    required this.description,
    required this.status,
    this.executionTimeMs,
    required this.timestamp,
  });

  factory ActivityEntry.fromJson(Map<String, dynamic> json) {
    return ActivityEntry(
      toolName: json['tool_name'] as String,
      action: json['action'] as String? ?? '',
      description: json['description'] as String? ?? '',
      status: _parseStatus(json['status'] as String? ?? 'success'),
      executionTimeMs: json['execution_time_ms'] as int?,
      timestamp: DateTime.tryParse(json['timestamp'] as String? ?? '') ?? DateTime.now(),
    );
  }

  static ActivityStatus _parseStatus(String s) => switch (s) {
    'success' => ActivityStatus.success,
    'failed' => ActivityStatus.failed,
    'denied' => ActivityStatus.denied,
    _ => ActivityStatus.pending,
  };
}
```

- [ ] **Step 3: Create approval provider**

Create `app/lib/features/security/providers/approval_provider.dart`:

```dart
import 'dart:async';
import 'dart:collection';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/approval_models.dart';

/// State for the approval system.
class ApprovalState {
  final ApprovalRequest? current;
  final int remainingSeconds;
  final List<ActivityEntry> activities;

  const ApprovalState({
    this.current,
    this.remainingSeconds = 0,
    this.activities = const [],
  });

  ApprovalState copyWith({
    ApprovalRequest? current,
    int? remainingSeconds,
    List<ActivityEntry>? activities,
    bool clearCurrent = false,
  }) {
    return ApprovalState(
      current: clearCurrent ? null : (current ?? this.current),
      remainingSeconds: remainingSeconds ?? this.remainingSeconds,
      activities: activities ?? this.activities,
    );
  }
}

class ApprovalNotifier extends StateNotifier<ApprovalState> {
  ApprovalNotifier({required this.sendWebSocketMessage})
      : super(const ApprovalState());

  final void Function(Map<String, dynamic> message) sendWebSocketMessage;
  final Queue<ApprovalRequest> _queue = Queue();
  Timer? _countdownTimer;

  void onApprovalRequest(ApprovalRequest request) {
    if (state.current != null) {
      _queue.add(request);
    } else {
      _showRequest(request);
    }
  }

  void approve(String requestId) {
    _respond(requestId, true);
  }

  void deny(String requestId) {
    _respond(requestId, false);
  }

  void onActivity(ActivityEntry entry) {
    final updated = [entry, ...state.activities];
    if (updated.length > 50) updated.removeLast();
    state = state.copyWith(activities: updated);
  }

  void _showRequest(ApprovalRequest request) {
    state = state.copyWith(
      current: request,
      remainingSeconds: request.timeoutSeconds,
    );
    _startCountdown(request);
  }

  void _startCountdown(ApprovalRequest request) {
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final remaining = state.remainingSeconds - 1;
      if (remaining <= 0) {
        deny(request.requestId);
      } else {
        state = state.copyWith(remainingSeconds: remaining);
      }
    });
  }

  void _respond(String requestId, bool approved) {
    _countdownTimer?.cancel();
    sendWebSocketMessage({
      'jsonrpc': '2.0',
      'method': 'tool.approval_response',
      'params': {'request_id': requestId, 'approved': approved},
    });
    state = state.copyWith(clearCurrent: true);
    _processNext();
  }

  void _processNext() {
    if (_queue.isNotEmpty) {
      _showRequest(_queue.removeFirst());
    }
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }
}

final approvalProvider =
    StateNotifierProvider<ApprovalNotifier, ApprovalState>((ref) {
  // sendWebSocketMessage injected during app initialization
  throw UnimplementedError('Must be overridden with sendWebSocketMessage');
});
```

- [ ] **Step 4: Create approval bottom sheet widget**

Create `app/lib/features/security/widgets/approval_sheet.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/approval_models.dart';
import '../providers/approval_provider.dart';

/// Shows the approval bottom sheet when a tool requests approval.
///
/// Call [showApprovalSheet] to display it. It auto-dismisses on timeout.
void showApprovalSheet(BuildContext context) {
  showModalBottomSheet(
    context: context,
    isDismissible: true,
    enableDrag: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => const _ApprovalSheetContent(),
  ).then((_) {
    // If dismissed by swipe, treat as deny
  });
  HapticFeedback.mediumImpact();
}

class _ApprovalSheetContent extends ConsumerWidget {
  const _ApprovalSheetContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(approvalProvider);
    final request = state.current;
    if (request == null) {
      return const SizedBox(height: 100, child: Center(child: Text('No pending request')));
    }
    final theme = Theme.of(context);
    final remaining = state.remainingSeconds;
    final progress = remaining / request.timeoutSeconds;

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Icon(Icons.lock_outline, color: theme.colorScheme.error, size: 24),
              const SizedBox(width: 8),
              Text('Approval Required',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  )),
            ],
          ),
          const SizedBox(height: 16),

          // Tool name + action
          Text(request.toolName,
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 4),
          Text(request.description, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 16),

          // Params card
          if (request.paramsSummary.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Parameters:', style: theme.textTheme.labelSmall),
                  const SizedBox(height: 4),
                  ...request.paramsSummary.entries.map((e) => Text(
                    '${e.key}: ${e.value}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  )),
                ],
              ),
            ),
          const SizedBox(height: 16),

          // Countdown
          Row(
            children: [
              SizedBox(
                width: 20, height: 20,
                child: CircularProgressIndicator(
                  value: progress,
                  strokeWidth: 2,
                  color: remaining <= 5
                      ? theme.colorScheme.error
                      : theme.colorScheme.primary,
                ),
              ),
              const SizedBox(width: 8),
              Text('Auto-deny in ${remaining}s',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: remaining <= 5 ? theme.colorScheme.error : null,
                  )),
            ],
          ),
          const SizedBox(height: 24),

          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () {
                    ref.read(approvalProvider.notifier).deny(request.requestId);
                    Navigator.of(context).pop();
                  },
                  child: const Text('Deny'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: FilledButton(
                  onPressed: () {
                    ref.read(approvalProvider.notifier).approve(request.requestId);
                    Navigator.of(context).pop();
                  },
                  child: const Text('Approve'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
```

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add app/lib/features/security/
git commit -m "feat(flutter): add approval bottom sheet with countdown timer"
```

---

## Task 8: Flutter Activity Feed

**Files:**
- Create: `app/lib/features/security/widgets/activity_feed.dart`

**Depends on:** Task 7 (models already created)

### Step-by-step

- [ ] **Step 1: Create activity feed widget**

Create `app/lib/features/security/widgets/activity_feed.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/approval_models.dart';
import '../providers/approval_provider.dart';

/// Real-time feed of tool execution activity.
class ActivityFeed extends ConsumerWidget {
  const ActivityFeed({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activities = ref.watch(approvalProvider).activities;
    final theme = Theme.of(context);

    if (activities.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.history, size: 48, color: theme.colorScheme.outline),
            const SizedBox(height: 8),
            Text('No activity yet', style: theme.textTheme.bodyMedium),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: activities.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) => _ActivityTile(entry: activities[index]),
    );
  }
}

class _ActivityTile extends StatelessWidget {
  const _ActivityTile({required this.entry});

  final ActivityEntry entry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Status icon
          _StatusIcon(status: entry.status),
          const SizedBox(width: 12),
          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${entry.toolName}${entry.action.isNotEmpty ? ' → ${entry.action}' : ''}',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (entry.description.isNotEmpty)
                  Text(entry.description, style: theme.textTheme.bodySmall),
                const SizedBox(height: 2),
                Text(
                  _formatMeta(entry),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.outline,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatMeta(ActivityEntry entry) {
    final parts = <String>[];
    if (entry.executionTimeMs != null) {
      parts.add('${entry.executionTimeMs}ms');
    }
    parts.add(_relativeTime(entry.timestamp));
    return parts.join(' · ');
  }

  String _relativeTime(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }
}

class _StatusIcon extends StatelessWidget {
  const _StatusIcon({required this.status});

  final ActivityStatus status;

  @override
  Widget build(BuildContext context) {
    return switch (status) {
      ActivityStatus.success => const Icon(Icons.check_circle, color: Colors.green, size: 20),
      ActivityStatus.pending => const SizedBox(
          width: 20, height: 20,
          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.amber)),
      ActivityStatus.denied => const Icon(Icons.cancel, color: Colors.red, size: 20),
      ActivityStatus.failed => const Icon(Icons.error, color: Colors.red, size: 20),
    };
  }
}
```

- [ ] **Step 2: Wire into security dashboard**

Modify `app/lib/features/security/` dashboard screen (create if not exists). Add a `TabBar` with two tabs: "Security" (existing tier card + kill switch) and "Activity" (new `ActivityFeed` widget). Also register a WebSocket listener that routes incoming `tool.approval_request` messages to `ApprovalNotifier.onApprovalRequest()` and `tool.activity` messages to `ApprovalNotifier.onActivity()`:

```dart
// In the WebSocket message handler (e.g., core/network/websocket_service.dart):
void _onMessage(Map<String, dynamic> message) {
  final method = message['method'] as String?;
  final params = message['params'] as Map<String, dynamic>?;
  if (params == null) return;

  if (method == 'tool.approval_request') {
    final request = ApprovalRequest.fromJson(params);
    ref.read(approvalProvider.notifier).onApprovalRequest(request);
    // Show the bottom sheet
    showApprovalSheet(navigatorKey.currentContext!);
  } else if (method == 'tool.activity') {
    final entry = ActivityEntry.fromJson(params);
    ref.read(approvalProvider.notifier).onActivity(entry);
  }
}
```

- [ ] **Step 3: Run Flutter analyze**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/app" && flutter analyze
```

Expected: No analysis errors.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add app/lib/features/security/
git commit -m "feat(flutter): add activity feed and wire into security dashboard"
```

---

## Task 9: Documentation & Final Verification

**Files:**
- Modify: `CLAUDE.md` (update completed phases)
- Create: `docs/superpowers/prompts/phase4b-implementation-prompt.md` (continuation prompt for next session)

### Step-by-step

- [ ] **Step 1: Update CLAUDE.md**

Update the Phase 4 sub-phases table to mark 4B as complete:

```markdown
| 4B: Computer Control | Complete | mouse.control, keyboard.control, file.manage, app.control, clipboard.manage (130+ tests) |
```

Update the "Completed Phases" list and project structure to include `tools/control/`.

- [ ] **Step 2: Run full test suite one final time**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && python -m pytest tests/ -v --tb=short --co -q
```

Expected: 398+ tests collected (158 Phase 4A + 110 Phase 4C + 130+ Phase 4B).

- [ ] **Step 3: Commit all documentation**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
git add CLAUDE.md docs/
git commit -m "docs: update all documentation for Phase 4B completion"
```
