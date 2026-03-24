# Phase 4 Design Spec: Computer Control & Vision

**Date:** 2026-03-23
**Author:** NABILNET.AI
**Status:** Draft
**Scope:** Tool platform, screen vision, computer control, code execution, remote control, Flutter approval/activity UI
**Depends on:** Phase 1B (sandbox, permissions, audit), Phase 2B (LLM router), Phase 3 (WebSocket streaming patterns)

---

## 1. Overview

Phase 4 gives Nobla Agent the ability to see and control the computer like a human. The agent captures screenshots, detects UI elements, reads text via OCR, and performs mouse/keyboard actions — all with user approval and full audit logging. A new **Tool Platform** provides the foundation: a registry, execution pipeline, and approval flow that every tool (vision, input, code, SSH) plugs into.

### Goals
- Tool Platform: BaseTool ABC, registry with auto-discovery, execution pipeline with permission → approval → execute → audit
- Screen Vision: screenshot capture, OCR (Tesseract + EasyOCR), UI-TARS element detection (progressive), natural language element targeting
- Computer Control: mouse (click, drag, scroll), keyboard (type, shortcuts), app launch/management, file manager
- Code Execution: enhance existing sandbox with package install, code generation, debug assistant, git integration
- Remote Control: SSH connections, remote command execution, SCP/SFTP file transfer
- Flutter: approval dialogs, activity feed, screen mirror, remote machine manager
- Every tool action is tier-gated, audit-logged, and (where required) user-approved via Flutter

### Non-Goals (Phase 4)
- Multi-machine orchestration (deferred to Phase 6 — Automation & Multi-Agent, coordinated workflows). Phase 4 supports independent connections to multiple machines; Phase 6 adds coordinated execution across N machines.
- Project scaffolding (deferred to Phase 6 — community marketplace skill system; tracked as backlog item BACKLOG-SCAFFOLD)
- Local UI-TARS GPU deployment (cloud/CPU fallback only in Phase 4)
- Always-on screen monitoring / autonomous action loops (requires Phase 6 automation)
- Persona marketplace for tool presets (Phase 6+)

---

## 2. Sub-Phase Decomposition

Phase 4 is decomposed into 6 sub-phases, each with its own plan → implementation cycle:

| Order | Sub-phase | Scope | Dependencies | Status |
|-------|-----------|-------|-------------|--------|
| 1 | **4-Pre: Tool Platform** | BaseTool, registry, executor, approval manager, gateway handlers, settings | Phase 1B infrastructure | ✅ Complete |
| 2 | **4A: Screen Vision** | Screenshot, OCR, UI-TARS detection, NL targeting | Tool Platform | ✅ Complete (158 tests) |
| 3 | **4C: Code Execution** | Sandbox enhancements, codegen, debug, git | Tool Platform + existing SandboxManager | Planned |
| 4 | **4B: Computer Control + Approval UI** | Mouse, keyboard, files, apps + Flutter approval dialog | Tool Platform + Vision (for targeting) | Planned |
| 5 | **4E: Flutter UI** | Screen mirror, activity feed, tool browser | Backend APIs from 4A-4C | Planned |
| 6 | **4D: Remote Control** | SSH, remote exec, SCP/SFTP | Tool Platform | Planned |

**Rationale for ordering:**
- Tool Platform first — all other sub-phases plug into it
- Vision before Control — the agent needs to "see" before it can meaningfully "act"
- Code Execution is independent and builds on existing sandbox (quick value)
- Computer Control + Approval Dialog together — building input tools without the approval UI is a security gap
- Flutter UI after backend APIs exist
- Remote Control last — all P1 priority, well-understood patterns

---

## 3. Architecture: Tool Platform Foundation

### 3.1 Design Approach

**Hybrid class + decorator pattern** — tools are classes inheriting from `BaseTool` ABC (enforcing contracts) and registered via `@register_tool` decorator (clean auto-discovery). This synthesizes two existing patterns in the codebase:
- ABCs for pluggable engines (`voice/stt/base.py`, `voice/tts/base.py`)
- Decorators for registration (`gateway/websocket.py` `@rpc_method`)

### 3.1.1 Prerequisites

Before implementing the tool platform, two existing files need changes:

1. **`gateway/websocket.py` refactoring** — This file is at the 750-line hard limit. As a prerequisite, extract existing domain-specific RPC handlers (code.execute, conversation handlers, chat handlers) into separate handler files (e.g., `gateway/code_handlers.py`, `gateway/chat_handlers.py`). This creates room for tool platform wiring and follows the same pattern as the new `gateway/tool_handlers.py`.

2. **`ConnectionManager.send_to()` method** — The approval flow and activity feed require sending targeted messages to a specific connection. Add a `send_to(connection_id, message)` method to `ConnectionManager` in `gateway/websocket.py`. The connection store (`dict[str, tuple[WebSocket, ConnectionState]]`) already supports this — the method simply looks up the connection and calls `websocket.send_json(message)`.

3. **Existing `code.execute` RPC migration** — The current `code.execute` RPC handler in `websocket.py` (line ~377) bypasses the tool platform pipeline (no tier check, no approval, no audit). During Phase 4-Pre, this handler must be replaced by a thin shim that delegates to `tool_executor.execute("code.run", ...)`, ensuring all code execution flows through the unified permission/audit pipeline.

### 3.2 Backend Module Structure

```
backend/nobla/tools/
├── __init__.py          # Auto-discovery imports + tool_registry singleton
├── models.py            # ToolCategory, ToolParams, ToolResult, ApprovalRequest
├── base.py              # BaseTool ABC
├── registry.py          # @register_tool decorator, ToolRegistry class
├── executor.py          # ToolExecutor — 5-step execution pipeline
├── approval.py          # ApprovalManager — WebSocket approval round-trip
├── search/              # Existing search tools (already built)
│   └── ...
├── vision/              # Sub-phase 4A
│   ├── __init__.py
│   ├── capture.py       # ScreenshotTool
│   ├── ocr.py           # OCRTool (Tesseract + EasyOCR)
│   ├── detection.py     # UIDetectionTool (UI-TARS)
│   └── targeting.py     # ElementTargetingTool (NL → coordinates)
├── input/               # Sub-phase 4B
│   ├── __init__.py
│   ├── mouse.py         # MouseTool
│   ├── keyboard.py      # KeyboardTool
│   └── clipboard.py     # ClipboardTool
├── app_control/         # Sub-phase 4B
│   ├── __init__.py
│   ├── launcher.py      # AppLaunchTool
│   ├── windows.py       # WindowManagementTool
│   └── file_manager.py  # FileManagerTool
├── code/                # Sub-phase 4C
│   ├── __init__.py
│   ├── runner.py        # CodeRunnerTool (wraps SandboxManager)
│   ├── packages.py      # PackageInstallTool
│   ├── codegen.py       # CodeGenerationTool
│   ├── debug.py         # DebugAssistantTool
│   └── git.py           # GitTool
└── ssh/                 # Sub-phase 4D
    ├── __init__.py
    ├── connection.py    # SSHConnectionTool
    ├── commands.py      # RemoteCommandTool
    └── transfer.py      # FileTransferTool
```

**Gateway addition:**
```
backend/nobla/gateway/
├── ...existing files...
└── tool_handlers.py     # tool.execute, tool.list, tool.approval_response
```

**Flutter additions:**
```
app/lib/features/
├── tools/
│   ├── screens/
│   │   └── tool_browser_screen.dart
│   ├── widgets/
│   │   ├── approval_dialog.dart
│   │   └── activity_feed.dart
│   └── providers/
│       ├── tool_provider.dart
│       └── approval_provider.dart
├── screen_mirror/
│   ├── screens/
│   │   └── mirror_screen.dart
│   └── providers/
│       └── mirror_provider.dart
└── remote/
    ├── screens/
    │   └── remote_manager_screen.dart
    └── providers/
        └── remote_provider.dart
```

### 3.3 Core Data Models

File: `tools/models.py` (~80 lines)

```python
class ToolCategory(str, Enum):
    VISION = "vision"
    INPUT = "input"
    FILE_SYSTEM = "file_system"
    APP_CONTROL = "app_control"
    CODE = "code"
    GIT = "git"
    SSH = "ssh"
    CLIPBOARD = "clipboard"
    SEARCH = "search"

@dataclass
class ToolParams:
    args: dict[str, Any]
    connection_state: ConnectionState
    context: dict[str, Any] | None = None

@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    approval_was_required: bool = False

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"

@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    description: str
    params_summary: dict
    screenshot_b64: str | None = None
    timeout_seconds: int = 30
    status: ApprovalStatus = ApprovalStatus.PENDING
```

### 3.4 BaseTool ABC

File: `tools/base.py` (~60 lines)

```python
class BaseTool(ABC):
    """Abstract base class for all Nobla tools.

    Subclasses MUST define name, description, and category as class variables
    (not instance variables). Optional class variables: tier, requires_approval,
    approval_timeout have defaults.
    """
    name: str                          # Class variable — set by subclass
    description: str                   # Class variable — set by subclass
    category: ToolCategory             # Class variable — set by subclass
    tier: Tier = Tier.STANDARD
    requires_approval: bool = False
    approval_timeout: int = 30

    @abstractmethod
    async def execute(self, params: ToolParams) -> ToolResult:
        ...

    async def validate(self, params: ToolParams) -> None:
        pass

    def describe_action(self, params: ToolParams) -> str:
        return self.description

    def get_params_summary(self, params: ToolParams) -> dict:
        return sanitize_params(params.args)
```

**Concrete subclass example:**
```python
@register_tool
class ScreenshotTool(BaseTool):
    name = "screenshot.capture"                # Class variable, NOT annotation
    description = "Capture a screenshot of the current screen"
    category = ToolCategory.VISION
    tier = Tier.STANDARD
    requires_approval = False

    async def execute(self, params: ToolParams) -> ToolResult:
        # ... capture logic ...
        return ToolResult(success=True, data={"image_b64": screenshot_b64})
```

**Design rationale:**
- Metadata is defined as **class variables** (e.g., `name = "screenshot.capture"`), not bare annotations — `@register_tool` calls `cls()` which requires no arguments, and the class variables are accessible on the instance
- `validate()` is optional — simple tools skip it, SSH tools check host validity
- `describe_action()` provides context for the approval dialog (e.g., "Click Submit button at (450, 320)")
- `get_params_summary()` reuses existing `sanitize_params()` from `security/audit.py`

### 3.5 Tool Registry & Auto-Discovery

File: `tools/registry.py` (~70 lines)

```python
_TOOL_REGISTRY: dict[str, BaseTool] = {}

def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    instance = cls()
    if instance.name in _TOOL_REGISTRY:
        raise ValueError(f"Duplicate tool name: {instance.name}")
    _TOOL_REGISTRY[instance.name] = instance
    return cls

class ToolRegistry:
    def get(self, name: str) -> BaseTool | None:
        return _TOOL_REGISTRY.get(name)

    def list_all(self) -> list[BaseTool]:
        return list(_TOOL_REGISTRY.values())

    def list_by_category(self, category: ToolCategory) -> list[BaseTool]:
        return [t for t in _TOOL_REGISTRY.values() if t.category == category]

    def list_available(self, tier: Tier) -> list[BaseTool]:
        return [t for t in _TOOL_REGISTRY.values() if t.tier <= tier]

    def get_manifest(self, tier: Tier) -> list[dict]:
        return [
            {"name": t.name, "description": t.description,
             "category": t.category.value, "requires_approval": t.requires_approval}
            for t in self.list_available(tier)
        ]
```

Auto-discovery via `tools/__init__.py`:
```python
from nobla.tools.registry import ToolRegistry
from nobla.tools import vision, input, code  # noqa: F401 — triggers @register_tool
tool_registry = ToolRegistry()
```

**Design rationale:**
- Module-level dict — simple, no metaclass magic
- `@register_tool` instantiates immediately — tools are singletons (stateless)
- `get_manifest()` provides tier-filtered tool list for LLM function-calling and Flutter UI
- Duplicate name detection prevents silent overwrites

### 3.6 Execution Pipeline

File: `tools/executor.py` (~120 lines)

The ToolExecutor orchestrates 5 steps for every tool call:

```
1. Tool exists?        → ToolResult(error) if not
2. Permission check    → InsufficientPermissions if tier too low
3. Validate params     → ValueError if invalid
4. Approval (if req.)  → ApprovalStatus.DENIED/TIMED_OUT stops execution
5. Execute             → ToolResult with data or error
   + Audit at EVERY step (success, denied, failed, error)
```

```python
class ToolExecutor:
    def __init__(self, registry, permission_checker, audit_logger, approval_manager):
        self.registry = registry
        self.checker = permission_checker
        self.audit = audit_logger
        self.approvals = approval_manager

    async def execute(self, tool_name: str, params: ToolParams) -> ToolResult:
        start = time.monotonic()
        tool = self.registry.get(tool_name)

        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Permission check
        try:
            self.checker.check(Tier(params.connection_state.tier), tool.tier)
        except InsufficientPermissions as e:
            await self._audit(tool, params, "permission_denied", start)
            return ToolResult(success=False, error=str(e))

        # Validate
        try:
            await tool.validate(params)
        except ValueError as e:
            await self._audit(tool, params, "validation_failed", start)
            return ToolResult(success=False, error=f"Invalid params: {e}")

        # Approval
        approval_required = False
        if tool.requires_approval:
            approval_required = True
            request = ApprovalRequest(
                request_id=str(uuid.uuid4()),
                tool_name=tool.name,
                description=tool.describe_action(params),
                params_summary=tool.get_params_summary(params),
                timeout_seconds=tool.approval_timeout,
            )
            status = await self.approvals.request_approval(
                request, params.connection_state.connection_id
            )
            if status != ApprovalStatus.APPROVED:
                await self._audit(tool, params, f"approval_{status.value}", start)
                return ToolResult(success=False, error=f"Action {status.value} by user",
                                  approval_was_required=True)

        # Execute
        try:
            result = await tool.execute(params)
            result.approval_was_required = approval_required
            result.execution_time_ms = int((time.monotonic() - start) * 1000)
            await self._audit(tool, params, "success", start)
            return result
        except Exception as e:
            await self._audit(tool, params, "execution_error", start)
            return ToolResult(success=False, error=f"Tool execution failed: {e}",
                              execution_time_ms=int((time.monotonic() - start) * 1000))
```

**Design rationale:**
- Linear pipeline, no middleware — 5 clear steps, easy to debug
- Reuses existing `PermissionChecker`, `AuditEntry`, `sanitize_params()`
- Exception boundary catches tool errors — never crashes the pipeline
- Audit logs every outcome for full trail

### 3.6.1 Kill Switch Integration

`ToolExecutor` registers callbacks with the existing `KillSwitch` during initialization:

```python
# In ToolExecutor.__init__:
kill_switch.on_soft_kill(self._handle_kill)

async def _handle_kill(self):
    # 1. Resolve all pending approvals as DENIED
    self.approvals.deny_all()
    # 2. Cancel all in-flight tool tasks
    for task in self._running_tasks:
        task.cancel()
    # 3. Reset concurrent tool semaphore
    self._semaphore = asyncio.Semaphore(self._max_concurrent)
```

`ApprovalManager` adds a `deny_all()` method:
```python
def deny_all(self) -> None:
    for future in self._pending.values():
        if not future.done():
            future.set_result(ApprovalStatus.DENIED)
    self._pending.clear()
```

The executor wraps each `tool.execute()` call in an `asyncio.Task` tracked in `self._running_tasks`, enabling cancellation on kill switch. When the kill switch fires, in-flight tools receive `asyncio.CancelledError`, which the executor catches and logs as `"killed"` status in the audit trail.

### 3.7 Approval Manager

File: `tools/approval.py` (~60 lines)

```python
class ApprovalManager:
    def __init__(self):
        self._pending: dict[str, asyncio.Future[ApprovalStatus]] = {}

    async def request_approval(self, request: ApprovalRequest, connection_id: str) -> ApprovalStatus:
        future = asyncio.get_event_loop().create_future()
        self._pending[request.request_id] = future

        # Send JSON-RPC notification to Flutter
        await connection_manager.send_to(connection_id, {
            "jsonrpc": "2.0",
            "method": "tool.approval_request",
            "params": {
                "request_id": request.request_id,
                "tool_name": request.tool_name,
                "description": request.description,
                "params_summary": request.params_summary,
                "screenshot_b64": request.screenshot_b64,
                "timeout_seconds": request.timeout_seconds,
            },
        })

        try:
            return await asyncio.wait_for(future, timeout=request.timeout_seconds)
        except asyncio.TimeoutError:
            return ApprovalStatus.TIMED_OUT
        finally:
            self._pending.pop(request.request_id, None)

    def resolve(self, request_id: str, approved: bool) -> None:
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED)
```

**Approval flow:**
```
Backend                          Flutter App
   │                                │
   ├── tool.approval_request ─────►│  Shows approval dialog:
   │   (JSON-RPC notification)      │  "Agent wants to click Submit"
   │                                │  [Approve] [Deny]
   │◄── tool.approval_response ────┤
   │   (approved: true/false)       │
   ▼ continues execution            │
```

**Design rationale:**
- `asyncio.Future` per request — clean await without polling
- JSON-RPC notification for request, method call for response — matches existing protocol
- Timeout returns `TIMED_OUT` (not `DENIED`) — distinguishes "user said no" from "user didn't see it"
- `resolve()` is idempotent — safe against race conditions
- Cleanup in `finally` — no memory leaks

### 3.8 Gateway Integration

File: `gateway/tool_handlers.py` (~80 lines)

Three new RPC methods:

```python
@rpc_method("tool.execute")
async def handle_tool_execute(params: dict, state: ConnectionState) -> dict:
    tool_params = ToolParams(
        args=params.get("args", {}),
        connection_state=state,
        context=params.get("context"),
    )
    result = await tool_executor.execute(params["tool_name"], tool_params)
    return asdict(result)

@rpc_method("tool.list")
async def handle_tool_list(params: dict, state: ConnectionState) -> dict:
    tier = Tier(state.tier)
    category = params.get("category")
    if category:
        tools = [t for t in tool_registry.list_by_category(ToolCategory(category))
                 if t.tier <= tier]
    else:
        tools = tool_registry.list_available(tier)
    return {"tools": [
        {"name": t.name, "description": t.description,
         "category": t.category.value, "tier": t.tier,
         "requires_approval": t.requires_approval}
        for t in tools
    ]}

@rpc_method("tool.approval_response")
async def handle_approval_response(params: dict, state: ConnectionState) -> dict:
    approval_manager.resolve(params["request_id"], params["approved"])
    return {"status": "acknowledged"}
```

**Activity feed** — broadcast via notification in `ToolExecutor._audit()`:

```python
await connection_manager.send_to(connection_id, {
    "jsonrpc": "2.0",
    "method": "tool.activity",
    "params": {
        "tool_name": tool.name,
        "category": tool.category.value,
        "description": tool.describe_action(params),
        "status": status,
        "execution_time_ms": latency_ms,
        "timestamp": datetime.utcnow().isoformat(),
    },
})
```

**Design rationale:**
- 3 RPC methods — minimal surface area
- `tool.list` is tier-filtered — SAFE users never see ADMIN tools
- Activity feed reuses the audit path — no separate tracking system
- `tool.activity` is a notification (no `id` field) — Flutter receives passively

---

## 4. Configuration & Settings

Added to `config/settings.py`:

```python
class ToolPlatformSettings(BaseModel):
    enabled: bool = True
    default_approval_timeout: int = 30
    activity_feed_enabled: bool = True
    max_concurrent_tools: int = 5
    category_overrides: dict[str, dict] = {}

class VisionSettings(BaseModel):
    enabled: bool = True
    screenshot_format: str = "png"
    screenshot_quality: int = 85
    screenshot_max_dimension: int = 1920
    ocr_engine: str = "tesseract"
    ocr_languages: list[str] = ["en"]
    ui_tars_enabled: bool = False          # progressive — off by default
    ui_tars_model_path: str = ""
    element_cache_ttl: int = 5

class ComputerControlSettings(BaseModel):
    enabled: bool = False                  # explicit opt-in required
    input_delay_ms: int = 50
    double_click_interval_ms: int = 200
    screenshot_before_action: bool = True
    screenshot_after_action: bool = True

class RemoteControlSettings(BaseModel):
    enabled: bool = False                  # explicit opt-in required
    max_connections: int = 10
    default_timeout: int = 30
    allowed_hosts: list[str] = []          # whitelist — empty = none
    key_directory: str = "~/.ssh"
```

**Design rationale:**
- Computer control and remote control are **off by default** — privacy-first
- `screenshot_before/after_action` — approval dialog shows context, activity feed shows result
- `ui_tars_enabled: False` — progressive enhancement, system works with OCR alone
- `allowed_hosts` whitelist for SSH — empty = no remote access until configured
- `element_cache_ttl` — avoids expensive re-detection during rapid action sequences

---

## 5. Permission Model for Phase 4

All Phase 4 tools map to the existing 4-tier permission system:

| Tool | Required Tier | Requires Approval | Rationale |
|------|-------------|-------------------|-----------|
| `screenshot.capture` | STANDARD | No | Read-only screen access |
| `ocr.extract` | STANDARD | No | Text extraction from image |
| `ui.detect_elements` | STANDARD | No | Element detection from image |
| `ui.target_element` | STANDARD | No | Coordinate resolution |
| `mouse.click` | ADMIN | Yes | Direct system control |
| `mouse.drag` | ADMIN | Yes | Direct system control |
| `mouse.scroll` | ADMIN | Yes | Direct system control |
| `keyboard.type` | ADMIN | Yes | Direct system control |
| `keyboard.shortcut` | ADMIN | Yes | Direct system control |
| `app.launch` | ELEVATED | Yes | Process creation |
| `app.close` | ELEVATED | Yes | Process termination |
| `window.manage` | ELEVATED | Yes | Window manipulation |
| `file.browse` | STANDARD | No | Read-only listing |
| `file.create` | ELEVATED | No | File creation |
| `file.delete` | ELEVATED | Yes | Destructive action |
| `file.move` | ELEVATED | No | File relocation |
| `file.copy` | STANDARD | No | Non-destructive |
| `clipboard.read` | ELEVATED | No | Sensitive data access |
| `clipboard.write` | ELEVATED | No | System modification |
| `code.run` | STANDARD | No | Sandboxed execution |
| `code.install_package` | ELEVATED | No | Network + install |
| `code.generate` | STANDARD | No | LLM-driven, output is sandboxed |
| `code.debug` | STANDARD | No | Read-only analysis |
| `git.clone` | ELEVATED | No | Network + disk |
| `git.commit` | ELEVATED | No | Repository modification |
| `git.push` | ELEVATED | Yes | Remote modification |
| `git.create_pr` | ELEVATED | Yes | External service action |
| `ssh.connect` | ADMIN | Yes | Remote machine access |
| `ssh.execute` | ADMIN | Yes | Remote command execution |
| `ssh.transfer` | ADMIN | Yes | Remote file transfer |

**Principle:** Approval is required for actions that are **destructive**, **externally visible**, or grant **direct system/remote control**. Read-only and sandboxed actions skip approval for speed.

---

## 6. Sub-Phase Details

### 6.1 Sub-Phase 4-Pre: Tool Platform Foundation

**Scope:** `tools/models.py`, `tools/base.py`, `tools/registry.py`, `tools/executor.py`, `tools/approval.py`, `gateway/tool_handlers.py`, settings additions, gateway refactoring prerequisites.

**Deliverables:**
- **Prerequisite:** Refactor `gateway/websocket.py` — extract domain-specific RPC handlers into separate files to free space (currently at 750-line limit)
- **Prerequisite:** Add `ConnectionManager.send_to(connection_id, message)` method
- **Prerequisite:** Migrate existing `code.execute` RPC handler to delegate through tool executor
- All 5 core tool platform files
- Gateway RPC handlers (`tool_handlers.py`)
- Settings classes (ToolPlatformSettings, VisionSettings, ComputerControlSettings, RemoteControlSettings)
- Kill switch integration (callbacks for tool cancellation)
- Unit tests: registry, executor pipeline (mock tools), approval manager (mock WebSocket), kill switch cancellation, permission enforcement
- Integration test: end-to-end tool execution via WebSocket

**Estimated size:** ~390 lines platform + ~80 lines gateway handlers + ~100 lines settings + ~300 lines tests + prerequisite refactoring

### 6.2 Sub-Phase 4A: Screen Vision

**Scope:** `tools/vision/` — 4 tools

**Tools:**
- `screenshot.capture` — Uses `mss` (python-mss) for fast cross-platform capture. Returns base64 PNG/JPEG. Supports multi-monitor, region capture, resolution scaling.
- `ocr.extract` — Tesseract (primary) + EasyOCR (fallback). Returns text with bounding box coordinates and confidence scores. Multi-language via settings.
- `ui.detect_elements` — UI-TARS model for GUI element detection. Returns element list with type, label, bounding box, confidence. Progressive: disabled by default, falls back to OCR-based detection.
- `ui.target_element` — Natural language → (x, y) coordinates. Takes a description ("the blue Submit button") and returns the best matching element's center coordinates. Uses vision tools internally.

**Tech stack:** python-mss, Pillow, pytesseract, easyocr, UI-TARS (optional)

### 6.3 Sub-Phase 4C: Code Execution

**Scope:** `tools/code/` — 5 tools

**Tools:**
- `code.run` — Thin wrapper around existing `SandboxManager`. Adds language auto-detection, structured output parsing, and tool platform integration.
- `code.install_package` — Runs pip/npm install inside a persistent sandbox container (not ephemeral). Requires ELEVATED tier for network access.
- `code.generate` — Routes description through LLM router (`brain/router.py`) with code-generation system prompt. Returns generated code + optional sandbox execution.
- `code.debug` — Parses error messages, identifies error type, suggests fixes via LLM. Read-only analysis.
- `git.*` — Git operations via subprocess in sandbox. Clone, commit, push, PR creation. GitHub/GitLab API integration for PR creation.

**Key design:** `code.run` does NOT replace `SandboxManager` — it wraps it. The sandbox stays in `security/sandbox.py` for kill switch integration.

### 6.4 Sub-Phase 4B: Computer Control + Approval UI

**Scope:** `tools/input/`, `tools/app_control/`, Flutter approval dialog

**Tools:**
- `mouse.*` — PyAutoGUI for cross-platform mouse control. All actions require ADMIN + approval. `screenshot_before_action` captures context for the approval dialog.
- `keyboard.*` — PyAutoGUI for keyboard input. Configurable delay between keystrokes for realism.
- `app.launch/close` — Platform-specific: subprocess (all), AppKit (macOS), win32 (Windows). ELEVATED + approval.
- `window.*` — Platform-specific window management. ELEVATED + approval.
- `file.*` — pathlib + shutil. Tier varies by operation (browse=STANDARD, delete=ELEVATED+approval).
- `clipboard.*` — pyperclip for cross-platform clipboard. ELEVATED tier.

**Flutter approval dialog:**
- Modal overlay triggered by `tool.approval_request` notification
- Shows: tool name, action description, sanitized params, optional screenshot
- Approve/Deny buttons with countdown timer (from `timeout_seconds`)
- Sends `tool.approval_response` RPC back to backend

**Built together because:** Mouse/keyboard without approval UI is a security gap. They must ship as a unit.

### 6.5 Sub-Phase 4E: Flutter UI

**Scope:** Screen mirror, activity feed, tool browser

**Screen mirror:**
- Receives screenshot frames via WebSocket (`tool.screen_frame` notification)
- Configurable refresh rate (1-10 FPS) — not video streaming, periodic captures
- Pinch-to-zoom, tap to highlight coordinates
- Toggle on/off in dashboard

**Activity feed:**
- Receives `tool.activity` notifications
- Reverse chronological list: tool name, category icon, description, status badge, timestamp
- Expandable rows for params and result details
- Filterable by category and status
- Lives as a widget embeddable in dashboard or standalone screen

**Tool browser:**
- Lists available tools grouped by category
- Shows tier requirement and approval status
- Enable/disable categories (maps to settings)

### 6.6 Sub-Phase 4D: Remote Control

**Scope:** `tools/ssh/` — 3 tools

**Tools:**
- `ssh.connect` — Paramiko for SSH connections. Key-based auth (password as fallback). Connection pooling. Host whitelist enforcement from settings.
- `ssh.execute` — Remote command execution with stdout/stderr/exit_code return. Full audit logging. ADMIN + approval for every command.
- `ssh.transfer` — SCP/SFTP via Paramiko. Upload/download with progress reporting. ADMIN + approval.

**Flutter remote manager:**
- Add/remove SSH connection profiles (host, port, user, key path)
- Test connection button
- Default machine selection
- Connection status indicator

**Phase 4 vs Phase 6 boundary:** Phase 4 supports connecting to multiple machines independently (one command at a time, user-initiated). Phase 6 adds coordinated multi-machine workflows (run the same task across N machines, automated orchestration via A2A protocol).

---

## 7. Error Handling

### New JSON-RPC Error Codes

```python
TOOL_NOT_FOUND = -32040
TOOL_VALIDATION_FAILED = -32041
TOOL_APPROVAL_DENIED = -32042
TOOL_APPROVAL_TIMEOUT = -32043
TOOL_EXECUTION_ERROR = -32044
TOOL_DISABLED = -32045
```

### Graceful Degradation

| Condition | Behavior |
|-----------|----------|
| UI-TARS model unavailable | Fall back to OCR-based element detection |
| GPU unavailable | CPU mode for all vision models |
| Tesseract not installed | Fall back to EasyOCR |
| Docker unavailable | Return clear error, suggest installation |
| SSH host unreachable | Return error with connection details |
| PyAutoGUI display unavailable | Return error (headless mode) |
| Approval timeout | Return TIMED_OUT, log to activity feed |

---

## 8. Testing Strategy

### Unit Tests (per sub-phase)
- **Tool Platform:** Registry operations, executor pipeline with mock tools, approval manager with mock WebSocket, permission enforcement
- **Vision:** Screenshot capture (mock display), OCR accuracy (sample images), element detection (mock model)
- **Code:** Sandbox wrapper, code generation prompts, debug analysis
- **Control:** Mouse/keyboard action construction (no actual input), file operations (temp directory)
- **SSH:** Connection management (mock Paramiko), command execution (mock channel)

### Integration Tests
- End-to-end: WebSocket → tool.execute → permission check → approval → result
- Concurrent tool execution (max_concurrent_tools enforcement)
- Approval timeout flow
- Kill switch stops all running tools
- Activity feed receives events for all tool outcomes

### Security Tests
- SAFE tier cannot access any tools except search
- STANDARD tier cannot access mouse/keyboard/SSH
- ELEVATED tier cannot access mouse/keyboard/SSH
- ADMIN tier with approval can access everything
- Audit trail captures all attempts (including denied)
- Sanitized params never contain secrets

---

## 9. Dependencies & Tech Stack

| Component | Package | Version | Purpose |
|-----------|---------|---------|---------|
| Screenshots | python-mss | ^9.0 | Fast cross-platform capture |
| Image processing | Pillow | ^10.0 | Resize, format conversion |
| OCR (primary) | pytesseract | ^0.3 | Tesseract wrapper |
| OCR (fallback) | easyocr | ^1.7 | Neural network OCR |
| UI detection | UI-TARS | TBD | GUI element detection (optional) |
| Mouse/keyboard | pyautogui | ^0.9 | Cross-platform input |
| Clipboard | pyperclip | ^1.8 | Cross-platform clipboard |
| SSH | paramiko | ^3.4 | SSH connections, SFTP |
| Git | gitpython | ^3.1 | Git operations |
| File ops | stdlib | - | pathlib, shutil, os |

---

## 10. Open Questions

1. **UI-TARS model selection** — Which specific UI-TARS checkpoint? Need to evaluate accuracy vs. resource requirements. Decision deferred to 4A implementation.
2. **Screen mirror frame format** — JPEG (smaller, lossy) vs. PNG (lossless, larger) vs. delta encoding. Decision deferred to 4E implementation.
3. **Persistent sandbox containers** — For package installation, should containers persist across sessions or rebuild each time? Trade-off: speed vs. reproducibility. Decision deferred to 4C implementation.
