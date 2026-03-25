# Phase 4B Design Spec: Computer Control Tools

**Date:** 2026-03-25
**Author:** NABILNET.AI
**Status:** Implemented
**Scope:** 5 computer control tools + safety layer + Flutter approval UI + settings
**Depends on:** Phase 4-Pre (tool platform), Phase 1B (permissions, kill switch), Phase 4A (screen vision)
**Parent spec:** `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md`

---

## 1. Overview

Phase 4B adds computer control tools to the Nobla tool platform. Five tools provide mouse control, keyboard control, file management, app management, and clipboard management — all executing on the host OS (not in Docker) with a 6-layer defense-in-depth security model. A shared `InputSafetyGuard` provides rate limiting and kill switch integration for input tools. The Flutter app gains an approval bottom sheet and real-time activity feed.

Phase 4A provides the "eyes" (screenshot, OCR, element detection, NL targeting). Phase 4B provides the "hands" (mouse, keyboard, files, apps, clipboard). They are loosely coupled — the LLM orchestrator composes them (e.g., vision finds coordinates, mouse clicks them).

### Goals

- Host-level mouse/keyboard control via `pyautogui` with safety abstraction layer
- File management with directory allow-list, path traversal protection, and automatic backups
- Curated app control with allow-list and PID tracking for Nobla-launched processes
- Clipboard management with content size limits and audit log sanitization
- Flutter approval bottom sheet for dangerous actions, activity feed for monitoring
- All tools follow Phase 4C patterns (compound subcommands, conditional approval, lazy singletons)

### Non-Goals

- Docker/sandbox execution for input tools — mouse/keyboard must control the user's actual display
- Full process manager — only curated apps, not arbitrary PID control
- Multi-monitor explicit API — coordinates work natively via pyautogui, no special handling needed
- Vision-control coupling — no internal cross-module dependencies, orchestrator composes
- Remote desktop / VNC — deferred to Phase 4D (Remote Control)
- Keyboard macros or action recording/playback — deferred to Phase 6 (Automation)

---

## 2. Architecture

### 2.1 File Layout

**New files:**
```
backend/nobla/tools/control/
├── __init__.py          # Auto-discovery imports (~15 lines)
├── mouse.py             # MouseControlTool — 5 subcommands (~150 lines)
├── keyboard.py          # KeyboardControlTool — 3 subcommands (~160 lines)
├── file_manager.py      # FileManageTool — 7 subcommands (~200 lines)
├── app.py               # AppControlTool — 4 subcommands (~180 lines)
├── clipboard.py         # ClipboardManageTool — 3 subcommands (~80 lines)
└── safety.py            # InputSafetyGuard — rate limiter, failsafe, halt (~100 lines)
```

**New Flutter files:**
```
app/lib/features/security/
├── widgets/
│   ├── approval_sheet.dart      # ApprovalBottomSheet (~150 lines)
│   └── activity_feed.dart       # ActivityFeed widget (~120 lines)
├── providers/
│   └── approval_provider.dart   # Riverpod notifier for approval state (~80 lines)
└── models/
    └── approval_models.dart     # ApprovalRequest, ActivityEntry (~40 lines)
```

**Modified files:**
```
backend/nobla/config/settings.py       # +ComputerControlSettings (~30 lines)
backend/nobla/tools/__init__.py        # +control import for auto-discovery
app/lib/features/security/             # Wire new widgets into existing dashboard
```

**Test files:**
```
tests/tools/control/
├── conftest.py            # Shared fixtures (~60 lines)
├── test_mouse.py          # ~200 lines, ~25 tests
├── test_keyboard.py       # ~200 lines, ~25 tests
├── test_file_manager.py   # ~250 lines, ~35 tests
├── test_app.py            # ~200 lines, ~20 tests
├── test_clipboard.py      # ~120 lines, ~15 tests
├── test_safety.py         # ~150 lines, ~20 tests
└── test_settings.py       # ~80 lines, ~10 tests
```

### 2.2 Data Flow

```
User/LLM Orchestrator
    │
    ├─ mouse.control ────► InputSafetyGuard.check() ─► pyautogui.moveTo/click/drag/scroll
    │                       (rate limit, halt check)
    │
    ├─ keyboard.control ─► InputSafetyGuard.check() ─► pyautogui.write/hotkey/press
    │                       (rate limit, halt check,     (chunked for long strings)
    │                        blocked shortcut check)
    │
    ├─ file.manage ──────► path validation ─► backup (if destructive) ─► pathlib/shutil ops
    │                      (resolve, allow-list,    (.nobla-backup/)
    │                       traversal check)
    │
    ├─ app.control ──────► allow-list check ─► subprocess.Popen/terminate + PID registry
    │
    └─ clipboard.manage ─► pyperclip.paste/copy (fallback: pyautogui)
```

All five tools flow through the standard ToolExecutor pipeline:
```
Registry Lookup → Permission Check (ELEVATED) → validate() → needs_approval()? → execute() → Audit
```

### 2.3 Security Model — 6 Layers of Defense

**Layer 1 — Tier gating:** All 5 tools are `Tier.ELEVATED`. User must have escalated to tier 3+ (requires passphrase in Flutter SecurityTierCard).

**Layer 2 — Allow-lists (hard deny at validate()):**

| Tool | Allow-list | Behavior |
|------|-----------|----------|
| `file.manage` | `allowed_read_dirs`, `allowed_write_dirs` | Paths resolved to absolute, traversal blocked, write_dirs must be subset of read_dirs |
| `app.control` | `allowed_apps` | Case-insensitive app name/path match |
| `keyboard.control` | `blocked_shortcuts` (deny-list) | Hard-blocked combos, not overridable by approval |

All allow-lists default to empty — **nothing is permitted until the user configures access**.

**Layer 3 — Conditional approval:** Per-action via `needs_approval(params)` override:

| Tool | Approval triggers |
|------|------------------|
| `mouse.control` | `action == "drag"` |
| `keyboard.control` | `action == "shortcut"` |
| `file.manage` | `action in {"write", "delete", "move", "copy"}` |
| `app.control` | `action in {"launch", "close"}` |
| `clipboard.manage` | `action in {"write", "clear"}` |

**Layer 4 — Rate limiting:** `InputSafetyGuard` enforces per-tool rate limits for mouse and keyboard. Prevents runaway automation loops.

**Layer 5 — Failsafe:** `pyautogui.FAILSAFE = True` (move mouse to upper-left corner aborts). Plus kill switch sets `InputSafetyGuard._halted = True`, checked before every input action.

**Layer 6 — Audit trail:** Every tool execution logged to PostgreSQL with tool name, action, sanitized params, status, latency. Clipboard content truncated in audit logs.

---

## 3. Tool Specifications

### 3.1 MouseControlTool (`mouse.control`)

**Category:** `INPUT` | **Tier:** `ELEVATED` | **Approval:** Conditional (drag only)

**Subcommands:**

| Action | Params | Description |
|--------|--------|-------------|
| `move` | `x: int, y: int, duration: float = 0.0` | Move cursor to absolute coordinates |
| `click` | `x: int, y: int, button: str = "left"` | Single click (left/right/middle) |
| `double_click` | `x: int, y: int, button: str = "left"` | Double click |
| `drag` | `start_x, start_y, end_x, end_y, duration: float = 0.5` | Drag from start to end (chunked, halt-checked) |
| `scroll` | `clicks: int, x: int = None, y: int = None` | Scroll wheel (positive = up, negative = down) |

**Validation:**
- All coordinates must be within screen bounds (0 to `pyautogui.size()`)
- Negative coordinates → `ValueError`
- `button` must be `"left"`, `"right"`, or `"middle"`
- `duration` must be >= 0

**Execution:**
- All calls go through `asyncio.to_thread()` (pyautogui is synchronous)
- `drag` is chunked: move in 20px increments, check `InputSafetyGuard._halted` between steps
- Returns `ToolResult(data={"action": "click", "x": 450, "y": 320, "button": "left"})`

**Dependency:** `pyautogui` (lazy import, clear error if unavailable)

### 3.2 KeyboardControlTool (`keyboard.control`)

**Category:** `INPUT` | **Tier:** `ELEVATED` | **Approval:** Conditional (shortcut only)

**Subcommands:**

| Action | Params | Description |
|--------|--------|-------------|
| `type` | `text: str` | Type text string character by character |
| `shortcut` | `keys: list[str]` | Key combination (e.g., `["ctrl", "c"]`) |
| `key_press` | `key: str` | Single key press (enter, tab, escape, f1-f12, arrows) |

**Validation:**
- `text` must be non-empty for `type`
- `shortcut` checked against `blocked_shortcuts` — hard deny before approval
- `key` must be a recognized key name

**Blocked shortcuts (default, configurable):**
```python
["ctrl+alt+delete", "alt+f4", "ctrl+shift+delete", "win+r", "win+l", "ctrl+w"]
```

**Shortcut normalization:** Before matching against `blocked_shortcuts`, all shortcuts are normalized: lowercased, keys sorted alphabetically, joined with `+`. This means `"Ctrl+Alt+Delete"`, `"alt+ctrl+delete"`, and `"ctrl+alt+delete"` all match the same entry. Normalization is a shared `_normalize_shortcut(keys: list[str]) -> str` function used by both validation and settings.

**Execution:**
- `type` is chunked: 50 characters at a time, check `_halted` between chunks
- `shortcut` calls `pyautogui.hotkey(*keys)`
- `key_press` calls `pyautogui.press(key)`
- All calls via `asyncio.to_thread()`

**Dependency:** `pyautogui` (lazy import)

### 3.3 FileManageTool (`file.manage`)

**Category:** `FILE_SYSTEM` | **Tier:** `ELEVATED` | **Approval:** Conditional (write/delete/move/copy)

**Subcommands:**

| Action | Params | Description |
|--------|--------|-------------|
| `read` | `path: str` | Read file contents (text, max 10MB) |
| `write` | `path: str, content: str` | Write/overwrite file (backup first) |
| `list` | `path: str` | List directory contents with metadata |
| `move` | `source: str, destination: str` | Move/rename file (backup destination if exists) |
| `copy` | `source: str, destination: str` | Copy file to destination |
| `delete` | `path: str` | Delete file (backup first) |
| `info` | `path: str` | File metadata (size, modified, permissions) |

**Path validation (critical security boundary):**
```python
resolved = Path(user_path).resolve()  # Kills ../ traversal
# For read/list/info: check against allowed_read_dirs
# For write/move/copy/delete: check against allowed_write_dirs
if not any(resolved.is_relative_to(Path(d).resolve()) for d in allowed_dirs):
    raise ValueError(f"Path {resolved} outside allowed directories")
```

Additionally:
- Symlinks resolved before allow-list check (prevents symlink escape)
- File size checked against `max_file_size_bytes` (10MB default)
- Binary file detection: return error for non-text files on `read`

**Backup mechanism:**
```
Before write/move/delete:
  ~/Documents/report.txt
  → ~/Documents/.nobla-backup/report.txt.{unix_timestamp}

Max backups per file: 3 (oldest pruned)
Backup dir created automatically on first use
```

**Dependency:** `pathlib`, `shutil` (stdlib only — always available)

### 3.4 AppControlTool (`app.control`)

**Category:** `APP_CONTROL` | **Tier:** `ELEVATED` | **Approval:** Conditional (launch/close)

**Subcommands:**

| Action | Params | Description |
|--------|--------|-------------|
| `launch` | `app: str, args: list[str] = []` | Launch app from allowed_apps list |
| `close` | `app: str` | Close Nobla-launched app (by tracked PID) |
| `switch` | `app: str` | Bring app window to foreground |
| `list` | | List visible windows with titles |

**Allow-list enforcement:**
- `app` name matched case-insensitively against `allowed_apps` config
- Empty `allowed_apps` → hard deny with config hint

**PID registry:**
```python
_launched_pids: dict[str, int] = {}  # app_name → PID

# On launch: track PID
# On close: only terminate if PID in _launched_pids
# Stale PID cleanup: check process.is_running() before operations
```

- `close` only works on processes Nobla launched — cannot kill arbitrary system processes
- `switch` uses platform-specific window focus via a `_focus_window(title)` helper function:
  - Windows: `win32gui.SetForegroundWindow()`
  - macOS: `osascript -e 'tell application "X" to activate'`
  - Linux: `wmctrl -a "title"` (fallback: `xdotool search --name "title" windowactivate`)
  - Helper isolated in a single function for testability (mock one function, not three platform branches)
- `list` returns visible window titles via `psutil` (fallback: subprocess-based platform commands)

**Dependencies:** `psutil` (optional, fallback for list/switch), `subprocess` (stdlib)

### 3.5 ClipboardManageTool (`clipboard.manage`)

**Category:** `CLIPBOARD` | **Tier:** `ELEVATED` | **Approval:** Conditional (write/clear)

**Subcommands:**

| Action | Params | Description |
|--------|--------|-------------|
| `read` | | Read current clipboard contents |
| `write` | `content: str` | Write content to clipboard |
| `clear` | | Clear clipboard contents |

**Validation:**
- `write` content must be within `max_clipboard_size` (1MB default)

**Audit sanitization:**
- `get_params_summary()` truncates clipboard content to first 50 characters + `"..."` in audit logs
- Full content only in `ToolResult.data`, never persisted to PostgreSQL

**Dependencies:** `pyperclip` (primary), `pyautogui` clipboard functions (fallback), clear error if neither available

---

## 4. InputSafetyGuard

Shared safety layer for `mouse.control` and `keyboard.control`. Enforces rate limiting, kill switch integration, and pyautogui failsafe.

### 4.1 Interface

```python
class InputSafetyGuard:
    _halted: bool = False
    _counters: dict[str, deque[float]] = {"mouse": deque(), "keyboard": deque()}
    _last_action: dict[str, float] = {"mouse": 0.0, "keyboard": 0.0}
    _platform_checked: bool = False

    @classmethod
    def check(cls, tool_type: str, settings: ComputerControlSettings) -> None:
        """Call before every mouse/keyboard action. Raises ToolExecutionError if blocked."""
        cls._check_halt()
        cls._check_platform()       # Lazy, cached after first call
        cls._check_rate_limit(tool_type, settings)
        cls._check_min_delay(tool_type, settings)

    @classmethod
    def halt(cls) -> None:
        """Called by kill switch. Blocks all future input actions."""
        cls._halted = True
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
        except ImportError:
            pass

    @classmethod
    def resume(cls) -> None:
        """Explicitly re-enable input after halt. Requires manual call."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Reset all state. Used by test fixtures for isolation."""
        cls._halted = False
        cls._counters = {"mouse": deque(), "keyboard": deque()}
        cls._last_action = {"mouse": 0.0, "keyboard": 0.0}
        cls._platform_checked = False
```

**Test isolation:** `conftest.py` calls `InputSafetyGuard.reset()` in a fixture to prevent cross-test contamination of rate counters, halt state, and platform cache.

### 4.2 Rate Limiting

```python
@classmethod
def _check_rate_limit(cls, tool_type: str, settings: ComputerControlSettings):
    now = time.monotonic()
    counter = cls._counters[tool_type]
    # Prune entries older than 60 seconds
    while counter and counter[0] < now - 60:
        counter.popleft()
    if len(counter) >= settings.max_actions_per_minute:
        raise ToolExecutionError(
            f"{tool_type} rate limit exceeded ({settings.max_actions_per_minute}/min)"
        )
    counter.append(now)

@classmethod
def _check_min_delay(cls, tool_type: str, settings: ComputerControlSettings):
    now = time.monotonic()
    elapsed_ms = (now - cls._last_action[tool_type]) * 1000
    if elapsed_ms < settings.min_action_delay_ms:
        raise ToolExecutionError(
            f"Action too fast — {elapsed_ms:.0f}ms < {settings.min_action_delay_ms}ms minimum"
        )
    cls._last_action[tool_type] = now
```

### 4.3 Platform Detection (lazy, cached)

```python
@classmethod
def _check_platform(cls):
    if cls._platform_checked:
        return
    # Linux: check display server
    if sys.platform == "linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if session_type == "wayland":
            raise ToolExecutionError("Wayland detected — pyautogui requires X11 session")
        if not os.environ.get("DISPLAY"):
            raise ToolExecutionError("No DISPLAY — computer control requires a graphical session")
    # macOS: accessibility check
    elif sys.platform == "darwin":
        # pyautogui will raise on first use if no accessibility permission
        pass  # Caught at execution time with clear error message
    # Windows: generally works, UAC-elevated windows may block input
    cls._platform_checked = True
```

---

## 5. Settings

### 5.1 ComputerControlSettings

```python
class ComputerControlSettings(BaseModel):
    """Configuration for Phase 4B computer control tools."""
    enabled: bool = True

    # File management
    allowed_read_dirs: list[str] = Field(default_factory=list)
    allowed_write_dirs: list[str] = Field(default_factory=list)
    max_file_size_bytes: int = 10_485_760       # 10MB
    max_backups_per_file: int = 3

    # App management
    allowed_apps: list[str] = Field(default_factory=list)

    # Input safety
    failsafe_enabled: bool = True
    min_action_delay_ms: int = 100
    max_actions_per_minute: int = 120
    type_chunk_size: int = 50                    # Characters between halt checks
    blocked_shortcuts: list[str] = Field(default_factory=lambda: [
        "ctrl+alt+delete", "alt+f4", "ctrl+shift+delete",
        "win+r", "win+l", "ctrl+w",
    ])

    # Clipboard
    max_clipboard_size: int = 1_048_576          # 1MB
    audit_clipboard_preview_length: int = 50

    @model_validator(mode="after")
    def validate_write_dirs_subset(self):
        """Ensure all write dirs are within a read dir."""
        for wd in self.allowed_write_dirs:
            wd_resolved = Path(wd).resolve()
            if not any(wd_resolved.is_relative_to(Path(rd).resolve())
                       for rd in self.allowed_read_dirs):
                raise ValueError(
                    f"Write directory '{wd}' is not within any allowed read directory"
                )
        return self
```

**Environment variable overrides:** `COMPUTER_CONTROL__ENABLED=false`, `COMPUTER_CONTROL__MAX_ACTIONS_PER_MINUTE=60`, etc. (Pydantic `__` separator pattern from existing settings).

### 5.2 Integration with Settings

Added to the root `Settings` class alongside `VisionSettings`, `CodeExecutionSettings`:
```python
class Settings(BaseModel):
    # ... existing ...
    vision: VisionSettings = Field(default_factory=VisionSettings)
    code: CodeExecutionSettings = Field(default_factory=CodeExecutionSettings)
    computer_control: ComputerControlSettings = Field(default_factory=ComputerControlSettings)  # NEW
```

---

## 6. Flutter Approval UI

### 6.1 ApprovalBottomSheet

A modal bottom sheet that appears when a tool requests approval via WebSocket.

**Layout:**
```
┌──────────────────────────────────┐
│  Lock Icon   Approval Required   │
│                                  │
│  tool_name → action              │
│  "describe_action() text"        │
│                                  │
│  ┌────────────────────────────┐  │
│  │ Parameters:                │  │
│  │  param1: value1            │  │
│  │  param2: value2            │  │
│  └────────────────────────────┘  │
│                                  │
│  Timer icon  Auto-deny in 27s    │
│                                  │
│  [ Deny ]            [ Approve ] │
└──────────────────────────────────┘
```

**Behavior:**
- Triggered by `tool.approval_request` WebSocket message
- Shows `describe_action()` text (human-readable) and `get_params_summary()` (sanitized params)
- Countdown timer with circular progress indicator, auto-denies on expiry
- Swipe-down to dismiss = deny
- Only one active at a time — subsequent requests queued
- Haptic feedback on appear
- Sends `tool.approval_response` back via WebSocket with `{request_id, approved: bool}`

**Riverpod state:**
```dart
@riverpod
class ApprovalNotifier extends _$ApprovalNotifier {
    Queue<ApprovalRequest> _queue = Queue();
    ApprovalRequest? current;
    Timer? _countdownTimer;
    int remainingSeconds;

    void onApprovalRequest(ApprovalRequest req);  // WebSocket handler
    void approve(String requestId);                // Approve button
    void deny(String requestId);                   // Deny / swipe / timeout
    void _processNext();                           // Dequeue next request
}
```

### 6.2 ActivityFeed

A scrollable list showing real-time tool execution activity.

**Layout:**
```
┌──────────────────────────────────┐
│  Recent Activity                 │
│                                  │
│  ✓  mouse.control → click        │
│     Clicked at (450, 320)        │
│     142ms · 2s ago               │
│                                  │
│  ⏳ keyboard.control → shortcut  │
│     Awaiting approval...         │
│                                  │
│  ✓  file.manage → read           │
│     Read ~/Documents/notes.txt   │
│     38ms · 15s ago               │
│                                  │
│  ✗  app.control → launch         │
│     Denied: launch "terminal"    │
│     · 1m ago                     │
└──────────────────────────────────┘
```

**Behavior:**
- Listens to `tool.activity` WebSocket broadcasts
- Most recent at top, max 50 entries in memory
- Status indicators: success (green check), pending (amber spinner), denied/failed (red X)
- Each entry shows: tool + action, description, execution time, relative timestamp
- Placed as a new tab in the existing security dashboard

### 6.3 WebSocket Protocol

**Server → Flutter (existing protocol, new handlers):**
```json
{
    "jsonrpc": "2.0",
    "method": "tool.approval_request",
    "params": {
        "request_id": "uuid-string",
        "tool_name": "mouse.control",
        "description": "Drag file report.pdf to Trash",
        "params_summary": {"start": [450, 320], "end": [850, 600]},
        "timeout_seconds": 30
    }
}
```

```json
{
    "jsonrpc": "2.0",
    "method": "tool.activity",
    "params": {
        "tool_name": "file.manage",
        "action": "read",
        "description": "Read ~/Documents/notes.txt",
        "status": "success",
        "execution_time_ms": 38,
        "timestamp": "2026-03-25T10:30:15Z"
    }
}
```

**Flutter → Server:**
```json
{
    "jsonrpc": "2.0",
    "method": "tool.approval_response",
    "params": {
        "request_id": "uuid-string",
        "approved": true
    }
}
```

---

## 7. Error Handling & Graceful Degradation

### 7.1 Dependency Availability

| Tool | Dependency | Fallback |
|------|-----------|----------|
| `mouse.control` | `pyautogui` | Clear error: "pip install pyautogui" |
| `keyboard.control` | `pyautogui` | Same |
| `file.manage` | `pathlib`, `shutil` (stdlib) | Always available |
| `app.control` | `psutil` (optional) + `subprocess` | Without psutil: list/switch use subprocess fallback |
| `clipboard.manage` | `pyperclip` | Fallback: pyautogui clipboard. Neither: clear error |

**Lazy import pattern (from Phase 4A):**
```python
def _get_pyautogui():
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        raise ToolExecutionError(
            "pyautogui is required for mouse/keyboard control. "
            "Install with: pip install pyautogui"
        )
```

### 7.2 Platform-Specific Edge Cases

| Platform | Issue | Detection | Error message |
|----------|-------|-----------|---------------|
| macOS | Accessibility permissions | Caught at pyautogui first use | "Grant accessibility in System Preferences" |
| Linux/Wayland | pyautogui requires X11 | `$XDG_SESSION_TYPE` check | "Wayland detected — requires X11 session" |
| Windows | UAC-protected windows | Caught at execution time | "Cannot interact with elevated window" |
| Headless/SSH | No display server | `$DISPLAY` check (Linux), screen availability | "No display — requires graphical session" |

Platform detection is lazy and cached in `InputSafetyGuard._platform_checked`.

### 7.3 Kill Switch Integration

```python
# InputSafetyGuard.halt() called by kill switch alongside ApprovalManager.deny_all()
# Immediately blocks all future mouse/keyboard actions

# Long operations (type, drag) are chunked:
# - keyboard.type: 50 chars at a time, halt check between chunks
# - mouse.drag: 20px increments, halt check between steps
# This ensures halt takes effect within ~100ms even mid-operation
```

### 7.4 Timeout Defaults

| Tool | Timeout | Rationale |
|------|---------|-----------|
| `mouse.control` | 5s | Single action, near-instant |
| `keyboard.control` | 10s | Long strings take time (chunked) |
| `file.manage` | 30s | Large file I/O |
| `app.control` | 15s | App launch can be slow |
| `clipboard.manage` | 5s | Instant operation |

---

## 8. Testing Strategy

### 8.1 Test Layout

```
tests/tools/control/
├── conftest.py            # ~60 lines — shared fixtures
├── test_mouse.py          # ~200 lines, ~25 tests
├── test_keyboard.py       # ~200 lines, ~25 tests
├── test_file_manager.py   # ~250 lines, ~35 tests
├── test_app.py            # ~200 lines, ~20 tests
├── test_clipboard.py      # ~120 lines, ~15 tests
├── test_safety.py         # ~150 lines, ~20 tests
└── test_settings.py       # ~80 lines, ~10 tests
```

**Target: 130+ tests** across all files.

### 8.2 Mock Boundaries

**Mock (system boundary):** `pyautogui`, `psutil`, `pyperclip`, `subprocess.Popen`, file I/O (use `tmp_path` fixture)

**Test real:** `InputSafetyGuard`, `ComputerControlSettings` validation, `validate()`, `needs_approval()`, `describe_action()`, `get_params_summary()`

### 8.3 Test Categories Per Tool

**MouseControlTool (~25 tests):**
- Validation: coordinates in/out of bounds, invalid button, negative coords
- Execution: each action calls correct pyautogui function with right args
- Approval: drag=True, all others=False
- Safety: FailSafeException caught, halt blocks, rate limit enforced
- Describe/summary: human-readable output per action

**KeyboardControlTool (~25 tests):**
- Validation: blocked shortcuts denied, empty text rejected
- Execution: short type (single call), long type (chunked), shortcut (hotkey), key_press
- Approval: shortcut=True, type/key_press=False
- Safety: halt between type chunks, rate limit per action
- Platform: no display error, accessibility error

**FileManageTool (~35 tests):**
- Path security: allow-list pass/fail, traversal blocked, symlink escape blocked, empty dirs hint
- Execution: read/write/list/move/copy/delete/info all work correctly
- Backup: created before write/delete, max backups pruned, backup dir auto-created
- Approval: read/list/info=False, write/delete/move/copy=True
- Settings: write_dirs subset validation, env override, max_file_size

**AppControlTool (~20 tests):**
- Validation: allowed app pass, disallowed deny, empty list hint
- Execution: launch tracks PID, close only Nobla-launched, switch focuses, list returns windows
- PID registry: tracked on launch, removed on close, stale PIDs handled
- Approval: list/switch=False, launch/close=True
- Degradation: psutil unavailable fallback

**ClipboardManageTool (~15 tests):**
- Validation: content within size limit, oversized rejected
- Execution: read/write/clear call correct functions
- Approval: read=False, write/clear=True
- Audit: params_summary truncates content, full content in result only
- Degradation: pyperclip unavailable → pyautogui fallback → error

**InputSafetyGuard (~20 tests):**
- Rate limit: within limit passes, exceeded blocks, counter expires after 60s, per-tool independent
- Min delay: enforced, too-fast blocked
- Halt: halt() blocks, resume() unblocks, halt re-enables failsafe
- Platform: display checks cached, Wayland detected, headless detected

**Settings (~10 tests):**
- Defaults correct, write_dirs subset validation, env override, blocked_shortcuts parsed

### 8.4 TDD Execution Order

1. `test_settings.py` + `test_safety.py` → implement `settings` + `safety.py`
2. `test_mouse.py` → implement `mouse.py`
3. `test_keyboard.py` → implement `keyboard.py`
4. `test_file_manager.py` → implement `file_manager.py`
5. `test_app.py` → implement `app.py`
6. `test_clipboard.py` → implement `clipboard.py`
7. Integration: auto-discovery wiring + end-to-end tests
8. Flutter: approval_sheet.dart, activity_feed.dart, providers, models

---

## 9. Size Estimates

| Component | Files | Lines (est.) |
|-----------|-------|-------------|
| Backend tools (`tools/control/`) | 7 files | ~870 |
| Settings (`config/settings.py`) | 1 edit | ~30 |
| Flutter UI (`features/security/`) | 4 new files | ~390 |
| Tests (`tests/tools/control/`) | 8 files | ~1,260 |
| **Total** | **20 files** | **~2,550** |

All files well within the 750-line hard limit. Largest file is `file_manager.py` at ~200 lines.

---

## 10. Open Items & Future Work

- **Session-scoped permissions:** Temporary access grants (e.g., "read Downloads for this task only") — deferred, adds complexity
- **Action recording/playback:** Record mouse/keyboard sequences for replay — Phase 6 (Automation)
- **Multi-monitor explicit API:** Named monitor selection for mouse targets — deferred, coordinates work natively
- **Remote control:** SSH + remote execution — Phase 4D
- **Vision-control convenience wrappers:** `mouse.control(target="Submit button")` — belongs in orchestrator layer (Phase 6), not individual tools
