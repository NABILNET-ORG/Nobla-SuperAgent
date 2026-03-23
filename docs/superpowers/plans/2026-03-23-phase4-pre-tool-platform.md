# Phase 4-Pre: Tool Platform Foundation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tool platform foundation — BaseTool ABC, registry, execution pipeline with permissions/approval/audit, and gateway integration — so all Phase 4 sub-phases can plug tools into it.

**Architecture:** Hybrid class+decorator pattern. Tools are classes inheriting `BaseTool` ABC, registered via `@register_tool` decorator. A `ToolExecutor` runs every tool through a 5-step pipeline: exists → permission → validate → approve → execute, with audit at every step. Approval flows through WebSocket to Flutter via `asyncio.Future`.

**Tech Stack:** Python 3.12, FastAPI, asyncio, structlog, Pydantic, existing security infrastructure (PermissionChecker, AuditEntry, KillSwitch, SandboxManager)

**Spec:** `docs/superpowers/specs/2026-03-23-phase4-computer-control-vision-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/nobla/gateway/websocket.py` | **Prerequisite**: Extract code.execute handler, add send_to(), free space under 750 lines |
| Create | `backend/nobla/gateway/code_handlers.py` | **Prerequisite**: Extracted code.execute RPC handler |
| Create | `backend/nobla/tools/models.py` | ToolCategory, ToolParams, ToolResult, ApprovalRequest, ApprovalStatus |
| Create | `backend/nobla/tools/base.py` | BaseTool ABC |
| Create | `backend/nobla/tools/registry.py` | @register_tool decorator, ToolRegistry class |
| Create | `backend/nobla/tools/executor.py` | ToolExecutor 5-step pipeline + kill switch + activity feed |
| Create | `backend/nobla/tools/approval.py` | ApprovalManager (WebSocket approval round-trip) |
| Modify | `backend/nobla/tools/__init__.py` | Export tool_registry singleton |
| Create | `backend/nobla/gateway/tool_handlers.py` | tool.execute, tool.list, tool.approval_response RPC handlers |
| Modify | `backend/nobla/config/settings.py` | Add ToolPlatformSettings to Settings root |
| Modify | `backend/nobla/gateway/app.py` | Initialize ToolExecutor + ApprovalManager in lifespan |
| Create | `backend/tests/test_tool_models.py` | Unit tests for data models |
| Create | `backend/tests/test_tool_registry.py` | Unit tests for registry + auto-discovery |
| Create | `backend/tests/test_tool_executor.py` | Unit tests for execution pipeline + kill switch |
| Create | `backend/tests/test_tool_approval.py` | Unit tests for approval manager |
| Create | `backend/tests/test_tool_handlers.py` | Unit tests for gateway RPC handlers |
| Create | `backend/tests/test_tool_settings.py` | Unit tests for ToolPlatformSettings |
| Create | `backend/tests/integration/test_tool_flow.py` | End-to-end WebSocket tool execution |

**Note:** `VisionSettings`, `ComputerControlSettings`, and `RemoteControlSettings` from the spec (Section 4) are deferred to their respective sub-phase plans (4A, 4B, 4D). Only `ToolPlatformSettings` is needed for the platform foundation.

---

## Task 0: Gateway Prerequisite — Extract Handlers & Add send_to

**Files:**
- Modify: `backend/nobla/gateway/websocket.py` (currently 751 lines — at hard limit)
- Create: `backend/nobla/gateway/code_handlers.py`

`websocket.py` is at the 750-line limit. We must extract handlers and add `send_to` before any other work.

- [ ] **Step 1: Extract `handle_code_execute` to `code_handlers.py`**

Cut the `handle_code_execute` function (lines ~377-399) from `websocket.py` and move it to a new file:

```python
# backend/nobla/gateway/code_handlers.py
"""Code execution RPC handlers (extracted from websocket.py)."""
from __future__ import annotations

from nobla.gateway.websocket import (
    ConnectionState,
    get_permission_checker,
    get_sandbox_manager,
    rpc_method,
)
from nobla.security.permissions import Tier


@rpc_method("code.execute")
async def handle_code_execute(params: dict, state: ConnectionState) -> dict:
    """Execute code in sandbox. Will delegate to tool platform when available."""
    pc = get_permission_checker()
    if pc:
        pc.check(current_tier=Tier(state.tier), required_tier=Tier.STANDARD)

    sm = get_sandbox_manager()
    if not sm:
        return {"error": "Sandbox not initialized"}

    code = params.get("code", "")
    language = params.get("language", "python")
    timeout = params.get("timeout")

    result = await sm.execute(code=code, language=language, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
        "timed_out": result.timed_out,
    }
```

In `websocket.py`, delete the original `handle_code_execute` function and add an import at the top of the module (after other imports):

```python
import nobla.gateway.code_handlers  # noqa: F401 — register code RPC methods
```

- [ ] **Step 2: Add `send_to` method to ConnectionManager**

In `websocket.py`, add this method to `ConnectionManager` after the `broadcast` method (around line 98):

```python
    async def send_to(self, connection_id: str, message: dict) -> None:
        """Send a message to a specific connection."""
        entry = self._connections.get(connection_id)
        if entry is None:
            return
        ws, _state = entry
        try:
            await ws.send_json(message)
        except Exception:
            logger.warning("send_to_failed", connection_id=connection_id)
```

- [ ] **Step 3: Verify line count is under 750**

Run: `wc -l backend/nobla/gateway/websocket.py`
Expected: ~730 lines (removed ~22 handler lines, added ~8 send_to + 1 import)

- [ ] **Step 4: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/websocket.py backend/nobla/gateway/code_handlers.py
git commit -m "refactor(gateway): extract code_handlers.py + add ConnectionManager.send_to

Prerequisite for tool platform: frees space in websocket.py (was at 750-line limit).
Adds send_to() for targeted WebSocket messaging."
```

---

## Task 1: Tool Data Models

**Files:**
- Create: `backend/nobla/tools/models.py`
- Create: `backend/tests/test_tool_models.py`

- [ ] **Step 1: Write tests for data models**

```python
# backend/tests/test_tool_models.py
from __future__ import annotations

import pytest

from nobla.tools.models import (
    ApprovalRequest,
    ApprovalStatus,
    ToolCategory,
    ToolParams,
    ToolResult,
)


class TestToolCategory:
    def test_all_categories_exist(self):
        expected = {"vision", "input", "file_system", "app_control",
                    "code", "git", "ssh", "clipboard", "search"}
        assert {c.value for c in ToolCategory} == expected

    def test_category_is_string(self):
        assert ToolCategory.VISION == "vision"
        assert isinstance(ToolCategory.VISION, str)


class TestToolParams:
    def test_creation_with_defaults(self):
        from nobla.gateway.websocket import ConnectionState

        state = ConnectionState()
        params = ToolParams(args={"key": "value"}, connection_state=state)
        assert params.args == {"key": "value"}
        assert params.context is None

    def test_creation_with_context(self):
        from nobla.gateway.websocket import ConnectionState

        state = ConnectionState(user_id="u1", tier=2)
        params = ToolParams(
            args={"code": "print(1)"},
            connection_state=state,
            context={"conversation_id": "c1"},
        )
        assert params.context["conversation_id"] == "c1"
        assert params.connection_state.tier == 2


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"output": "hello"})
        assert result.success is True
        assert result.error is None
        assert result.execution_time_ms == 0
        assert result.approval_was_required is False

    def test_error_result(self):
        result = ToolResult(success=False, error="Permission denied")
        assert result.success is False
        assert result.error == "Permission denied"


class TestApprovalRequest:
    def test_creation_with_defaults(self):
        req = ApprovalRequest(
            request_id="abc-123",
            tool_name="mouse.click",
            description="Click at (100, 200)",
            params_summary={"x": 100, "y": 200},
        )
        assert req.timeout_seconds == 30
        assert req.status == ApprovalStatus.PENDING
        assert req.screenshot_b64 is None

    def test_all_approval_statuses(self):
        expected = {"pending", "approved", "denied", "timed_out"}
        assert {s.value for s in ApprovalStatus} == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.tools.models'`

- [ ] **Step 3: Implement tool data models**

```python
# backend/nobla/tools/models.py
"""Data models for the Nobla tool platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nobla.gateway.websocket import ConnectionState


class ToolCategory(str, Enum):
    """Categories for organizing tools."""

    VISION = "vision"
    INPUT = "input"
    FILE_SYSTEM = "file_system"
    APP_CONTROL = "app_control"
    CODE = "code"
    GIT = "git"
    SSH = "ssh"
    CLIPBOARD = "clipboard"
    SEARCH = "search"


class ApprovalStatus(str, Enum):
    """Status of a user approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass
class ToolParams:
    """Input parameters passed to a tool's execute method."""

    args: dict[str, Any]
    connection_state: ConnectionState
    context: dict[str, Any] | None = None


@dataclass
class ToolResult:
    """Uniform result returned by every tool."""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    approval_was_required: bool = False


@dataclass
class ApprovalRequest:
    """Request sent to Flutter for user approval of a tool action."""

    request_id: str
    tool_name: str
    description: str
    params_summary: dict
    screenshot_b64: str | None = None
    timeout_seconds: int = 30
    status: ApprovalStatus = ApprovalStatus.PENDING
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_models.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/models.py backend/tests/test_tool_models.py
git commit -m "feat(tools): add tool platform data models

ToolCategory, ToolParams, ToolResult, ApprovalRequest, ApprovalStatus
for the Phase 4 tool platform foundation."
```

---

## Task 2: BaseTool ABC

**Files:**
- Create: `backend/nobla/tools/base.py`
- Create: `backend/tests/test_tool_base.py`

- [ ] **Step 1: Write tests for BaseTool**

```python
# backend/tests/test_tool_base.py
from __future__ import annotations

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


class ConcreteTool(BaseTool):
    """Minimal concrete implementation for testing."""

    name = "test.echo"
    description = "Echo the input back"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data=params.args)


class AdminTool(BaseTool):
    """Tool requiring admin tier + approval."""

    name = "test.admin"
    description = "Admin-only action"
    category = ToolCategory.INPUT
    tier = Tier.ADMIN
    requires_approval = True
    approval_timeout = 15

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="done")

    def describe_action(self, params: ToolParams) -> str:
        return f"Admin action on {params.args.get('target', 'unknown')}"


class TestBaseToolInterface:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_tool_has_metadata(self):
        tool = ConcreteTool()
        assert tool.name == "test.echo"
        assert tool.description == "Echo the input back"
        assert tool.category == ToolCategory.CODE
        assert tool.tier == Tier.STANDARD
        assert tool.requires_approval is False
        assert tool.approval_timeout == 30

    def test_admin_tool_has_overrides(self):
        tool = AdminTool()
        assert tool.tier == Tier.ADMIN
        assert tool.requires_approval is True
        assert tool.approval_timeout == 15


class TestBaseToolMethods:
    @pytest.fixture
    def params(self):
        state = ConnectionState(user_id="u1", tier=2)
        return ToolParams(args={"target": "button"}, connection_state=state)

    async def test_execute(self, params):
        tool = ConcreteTool()
        result = await tool.execute(params)
        assert result.success is True
        assert result.data == {"target": "button"}

    async def test_validate_default_passes(self, params):
        tool = ConcreteTool()
        await tool.validate(params)  # Should not raise

    async def test_describe_action_default(self, params):
        tool = ConcreteTool()
        assert tool.describe_action(params) == "Echo the input back"

    async def test_describe_action_override(self, params):
        tool = AdminTool()
        assert tool.describe_action(params) == "Admin action on button"

    async def test_get_params_summary_redacts(self):
        state = ConnectionState(user_id="u1", tier=2)
        params = ToolParams(
            args={"query": "hello", "api_key": "sk-secret-123"},
            connection_state=state,
        )
        tool = ConcreteTool()
        summary = tool.get_params_summary(params)
        assert summary["query"] == "hello"
        assert summary["api_key"] == "[REDACTED]"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.tools.base'`

- [ ] **Step 3: Implement BaseTool ABC**

```python
# backend/nobla/tools/base.py
"""Abstract base class for all Nobla tools."""
from __future__ import annotations

from abc import ABC, abstractmethod

from nobla.security.audit import sanitize_params
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


class BaseTool(ABC):
    """Base class for tools. Subclasses define metadata as class variables.

    Example::

        @register_tool
        class ScreenshotTool(BaseTool):
            name = "screenshot.capture"
            description = "Capture a screenshot"
            category = ToolCategory.VISION
            tier = Tier.STANDARD

            async def execute(self, params: ToolParams) -> ToolResult:
                ...
    """

    name: str
    description: str
    category: ToolCategory
    tier: Tier = Tier.STANDARD
    requires_approval: bool = False
    approval_timeout: int = 30

    @abstractmethod
    async def execute(self, params: ToolParams) -> ToolResult:
        """Run the tool. Called only after permission + approval pass."""
        ...

    async def validate(self, params: ToolParams) -> None:
        """Optional pre-execution validation. Raise ValueError on bad input."""

    def describe_action(self, params: ToolParams) -> str:
        """Human-readable description for approval dialog and activity feed."""
        return self.description

    def get_params_summary(self, params: ToolParams) -> dict:
        """Sanitized params for display. Redacts sensitive fields."""
        return sanitize_params(params.args)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_base.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/base.py backend/tests/test_tool_base.py
git commit -m "feat(tools): add BaseTool abstract base class

ABC with execute, validate, describe_action, get_params_summary.
Subclasses define metadata as class variables."
```

---

## Task 3: Tool Registry & Auto-Discovery

**Files:**
- Create: `backend/nobla/tools/registry.py`
- Create: `backend/tests/test_tool_registry.py`

- [ ] **Step 1: Write tests for registry**

```python
# backend/tests/test_tool_registry.py
from __future__ import annotations

import pytest

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry, register_tool, _TOOL_REGISTRY


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear the global registry before/after each test."""
    _TOOL_REGISTRY.clear()
    yield
    _TOOL_REGISTRY.clear()


class TestRegisterToolDecorator:
    def test_register_tool(self):
        @register_tool
        class MyTool(BaseTool):
            name = "test.my_tool"
            description = "A test tool"
            category = ToolCategory.CODE

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        assert "test.my_tool" in _TOOL_REGISTRY
        assert isinstance(_TOOL_REGISTRY["test.my_tool"], MyTool)

    def test_duplicate_name_raises(self):
        @register_tool
        class Tool1(BaseTool):
            name = "test.dup"
            description = "First"
            category = ToolCategory.CODE

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        with pytest.raises(ValueError, match="Duplicate tool name: test.dup"):

            @register_tool
            class Tool2(BaseTool):
                name = "test.dup"
                description = "Second"
                category = ToolCategory.CODE

                async def execute(self, params: ToolParams) -> ToolResult:
                    return ToolResult(success=True)

    def test_decorator_returns_class(self):
        @register_tool
        class MyTool(BaseTool):
            name = "test.return_check"
            description = "Check return"
            category = ToolCategory.CODE

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        assert MyTool.name == "test.return_check"


class TestToolRegistry:
    @pytest.fixture
    def registry_with_tools(self):
        @register_tool
        class VisionTool(BaseTool):
            name = "vision.screenshot"
            description = "Capture screenshot"
            category = ToolCategory.VISION
            tier = Tier.STANDARD

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        @register_tool
        class AdminTool(BaseTool):
            name = "input.mouse"
            description = "Mouse control"
            category = ToolCategory.INPUT
            tier = Tier.ADMIN
            requires_approval = True

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        @register_tool
        class CodeTool(BaseTool):
            name = "code.run"
            description = "Run code in sandbox"
            category = ToolCategory.CODE
            tier = Tier.STANDARD

            async def execute(self, params: ToolParams) -> ToolResult:
                return ToolResult(success=True)

        return ToolRegistry()

    def test_get_existing(self, registry_with_tools):
        tool = registry_with_tools.get("vision.screenshot")
        assert tool is not None
        assert tool.name == "vision.screenshot"

    def test_get_missing(self, registry_with_tools):
        assert registry_with_tools.get("nonexistent") is None

    def test_list_all(self, registry_with_tools):
        tools = registry_with_tools.list_all()
        assert len(tools) == 3

    def test_list_by_category(self, registry_with_tools):
        vision_tools = registry_with_tools.list_by_category(ToolCategory.VISION)
        assert len(vision_tools) == 1
        assert vision_tools[0].name == "vision.screenshot"

    def test_list_available_standard(self, registry_with_tools):
        tools = registry_with_tools.list_available(Tier.STANDARD)
        names = {t.name for t in tools}
        assert names == {"vision.screenshot", "code.run"}

    def test_list_available_admin(self, registry_with_tools):
        tools = registry_with_tools.list_available(Tier.ADMIN)
        assert len(tools) == 3

    def test_get_manifest(self, registry_with_tools):
        manifest = registry_with_tools.get_manifest(Tier.STANDARD)
        assert len(manifest) == 2
        entry = next(m for m in manifest if m["name"] == "vision.screenshot")
        assert entry["description"] == "Capture screenshot"
        assert entry["category"] == "vision"
        assert entry["requires_approval"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.tools.registry'`

- [ ] **Step 3: Implement registry**

```python
# backend/nobla/tools/registry.py
"""Tool registry with decorator-based auto-discovery."""
from __future__ import annotations

from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory

_TOOL_REGISTRY: dict[str, BaseTool] = {}


def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Class decorator: instantiate and register a tool."""
    instance = cls()
    if instance.name in _TOOL_REGISTRY:
        raise ValueError(f"Duplicate tool name: {instance.name}")
    _TOOL_REGISTRY[instance.name] = instance
    return cls


class ToolRegistry:
    """Central access point for discovering and retrieving tools."""

    def get(self, name: str) -> BaseTool | None:
        return _TOOL_REGISTRY.get(name)

    def list_all(self) -> list[BaseTool]:
        return list(_TOOL_REGISTRY.values())

    def list_by_category(self, category: ToolCategory) -> list[BaseTool]:
        return [t for t in _TOOL_REGISTRY.values() if t.category == category]

    def list_available(self, tier: Tier) -> list[BaseTool]:
        """Tools the user can access at their current tier."""
        return [t for t in _TOOL_REGISTRY.values() if t.tier <= tier]

    def get_manifest(self, tier: Tier) -> list[dict]:
        """Tool descriptions for LLM function-calling and Flutter UI."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "requires_approval": t.requires_approval,
            }
            for t in self.list_available(tier)
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_registry.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/registry.py backend/tests/test_tool_registry.py
git commit -m "feat(tools): add tool registry with @register_tool decorator

ToolRegistry for discovery, tier-filtered listing, and LLM manifest.
Auto-discovery via module imports triggering @register_tool."
```

---

## Task 4: Approval Manager

**Files:**
- Create: `backend/nobla/tools/approval.py`
- Create: `backend/tests/test_tool_approval.py`

**Depends on:** Task 0 (`ConnectionManager.send_to` already added)

- [ ] **Step 1: Write tests for ApprovalManager**

```python
# backend/tests/test_tool_approval.py
from __future__ import annotations

import asyncio

import pytest

from nobla.tools.approval import ApprovalManager
from nobla.tools.models import ApprovalRequest, ApprovalStatus


class FakeConnectionManager:
    """Mock ConnectionManager that captures sent messages."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send_to(self, connection_id: str, message: dict) -> None:
        self.sent.append((connection_id, message))


class TestApprovalManager:
    @pytest.fixture
    def fake_cm(self):
        return FakeConnectionManager()

    @pytest.fixture
    def approval_mgr(self, fake_cm):
        return ApprovalManager(connection_manager=fake_cm)

    @pytest.fixture
    def sample_request(self):
        return ApprovalRequest(
            request_id="req-001",
            tool_name="mouse.click",
            description="Click at (100, 200)",
            params_summary={"x": 100, "y": 200},
            timeout_seconds=2,
        )

    async def test_approval_approved(self, approval_mgr, sample_request, fake_cm):
        async def approve_soon():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=True)

        asyncio.create_task(approve_soon())
        status = await approval_mgr.request_approval(sample_request, "conn-1")

        assert status == ApprovalStatus.APPROVED
        assert len(fake_cm.sent) == 1
        conn_id, msg = fake_cm.sent[0]
        assert conn_id == "conn-1"
        assert msg["method"] == "tool.approval_request"
        assert msg["params"]["request_id"] == "req-001"

    async def test_approval_denied(self, approval_mgr, sample_request):
        async def deny_soon():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=False)

        asyncio.create_task(deny_soon())
        status = await approval_mgr.request_approval(sample_request, "conn-1")
        assert status == ApprovalStatus.DENIED

    async def test_approval_timeout(self, approval_mgr, sample_request):
        sample_request.timeout_seconds = 0.1
        status = await approval_mgr.request_approval(sample_request, "conn-1")
        assert status == ApprovalStatus.TIMED_OUT

    async def test_resolve_unknown_request_is_noop(self, approval_mgr):
        approval_mgr.resolve("nonexistent", approved=True)  # Should not raise

    async def test_resolve_after_timeout_is_noop(self, approval_mgr, sample_request):
        sample_request.timeout_seconds = 0.05
        await approval_mgr.request_approval(sample_request, "conn-1")
        # Now try resolving after timeout
        approval_mgr.resolve("req-001", approved=True)  # Should not raise

    async def test_deny_all(self, approval_mgr, fake_cm):
        req1 = ApprovalRequest(
            request_id="r1", tool_name="t1",
            description="d1", params_summary={}, timeout_seconds=10,
        )
        req2 = ApprovalRequest(
            request_id="r2", tool_name="t2",
            description="d2", params_summary={}, timeout_seconds=10,
        )

        async def deny_all_soon():
            await asyncio.sleep(0.05)
            approval_mgr.deny_all()

        asyncio.create_task(deny_all_soon())

        results = await asyncio.gather(
            approval_mgr.request_approval(req1, "c1"),
            approval_mgr.request_approval(req2, "c2"),
        )
        assert results[0] == ApprovalStatus.DENIED
        assert results[1] == ApprovalStatus.DENIED

    async def test_cleanup_after_resolve(self, approval_mgr, sample_request):
        async def approve():
            await asyncio.sleep(0.05)
            approval_mgr.resolve("req-001", approved=True)

        asyncio.create_task(approve())
        await approval_mgr.request_approval(sample_request, "conn-1")
        assert "req-001" not in approval_mgr._pending
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_approval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.tools.approval'`

- [ ] **Step 3: Implement ApprovalManager**

```python
# backend/nobla/tools/approval.py
"""Approval flow for tools requiring user confirmation."""
from __future__ import annotations

import asyncio

import structlog

from nobla.tools.models import ApprovalRequest, ApprovalStatus

logger = structlog.get_logger(__name__)


class ApprovalManager:
    """Sends approval requests to Flutter and awaits user response."""

    def __init__(self, connection_manager):
        self._cm = connection_manager
        self._pending: dict[str, asyncio.Future[ApprovalStatus]] = {}

    async def request_approval(
        self, request: ApprovalRequest, connection_id: str
    ) -> ApprovalStatus:
        """Send approval request via WebSocket, wait for response or timeout."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalStatus] = loop.create_future()
        self._pending[request.request_id] = future

        await self._cm.send_to(connection_id, {
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
            return await asyncio.wait_for(
                future, timeout=request.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.info("approval_timed_out", request_id=request.request_id)
            return ApprovalStatus.TIMED_OUT
        finally:
            self._pending.pop(request.request_id, None)

    def resolve(self, request_id: str, approved: bool) -> None:
        """Called when Flutter sends back the user's decision."""
        future = self._pending.get(request_id)
        if future and not future.done():
            status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
            future.set_result(status)

    def deny_all(self) -> None:
        """Deny all pending approvals. Called by kill switch."""
        for future in self._pending.values():
            if not future.done():
                future.set_result(ApprovalStatus.DENIED)
        self._pending.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_approval.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/approval.py backend/tests/test_tool_approval.py
git commit -m "feat(tools): add ApprovalManager

WebSocket-based approval round-trip with asyncio.Future.
Supports approve, deny, timeout, and deny_all (kill switch)."
```

---

## Task 5: Tool Executor Pipeline

**Files:**
- Create: `backend/nobla/tools/executor.py`
- Create: `backend/tests/test_tool_executor.py`

- [ ] **Step 1: Write tests for ToolExecutor**

```python
# backend/tests/test_tool_executor.py
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.audit import AuditEntry
from nobla.security.permissions import PermissionChecker, Tier
from nobla.tools.approval import ApprovalManager
from nobla.tools.base import BaseTool
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import (
    ApprovalStatus,
    ToolCategory,
    ToolParams,
    ToolResult,
)
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY, register_tool


@pytest.fixture(autouse=True)
def clean_registry():
    _TOOL_REGISTRY.clear()
    yield
    _TOOL_REGISTRY.clear()


@register_tool
class EchoTool(BaseTool):
    name = "test.echo"
    description = "Echo input"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data=params.args)


@register_tool
class AdminApprovalTool(BaseTool):
    name = "test.admin_action"
    description = "Admin action"
    category = ToolCategory.INPUT
    tier = Tier.ADMIN
    requires_approval = True
    approval_timeout = 2

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="executed")


@register_tool
class ValidatingTool(BaseTool):
    name = "test.validated"
    description = "Validates input"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def validate(self, params: ToolParams) -> None:
        if "required_key" not in params.args:
            raise ValueError("Missing required_key")

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data=params.args["required_key"])


@register_tool
class FailingTool(BaseTool):
    name = "test.failing"
    description = "Always fails"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        raise RuntimeError("Something broke")


class FakeApprovalManager:
    def __init__(self, auto_status: ApprovalStatus = ApprovalStatus.APPROVED):
        self._auto_status = auto_status

    async def request_approval(self, request, connection_id):
        return self._auto_status

    def deny_all(self):
        pass


@pytest.fixture
def audit_log():
    return []


@pytest.fixture
def make_executor(audit_log):
    def _make(approval_status=ApprovalStatus.APPROVED):
        async def audit_fn(entry: AuditEntry):
            audit_log.append(entry)

        return ToolExecutor(
            registry=ToolRegistry(),
            permission_checker=PermissionChecker(),
            audit_logger=audit_fn,
            approval_manager=FakeApprovalManager(approval_status),
        )
    return _make


def make_params(tier: int = 1, args: dict | None = None) -> ToolParams:
    state = ConnectionState(user_id="u1", tier=tier, connection_id="conn-1")
    return ToolParams(args=args or {}, connection_state=state)


class TestToolExecutorPipeline:
    async def test_unknown_tool(self, make_executor):
        executor = make_executor()
        result = await executor.execute("nonexistent.tool", make_params())
        assert result.success is False
        assert "Unknown tool" in result.error

    async def test_permission_denied(self, make_executor, audit_log):
        executor = make_executor()
        result = await executor.execute("test.admin_action", make_params(tier=2))
        assert result.success is False
        assert "tier" in result.error.lower()
        assert audit_log[-1].status == "permission_denied"

    async def test_permission_granted(self, make_executor, audit_log):
        executor = make_executor()
        result = await executor.execute("test.echo", make_params(tier=2, args={"x": 1}))
        assert result.success is True
        assert result.data == {"x": 1}
        assert audit_log[-1].status == "success"

    async def test_validation_failure(self, make_executor, audit_log):
        executor = make_executor()
        result = await executor.execute("test.validated", make_params(tier=2, args={}))
        assert result.success is False
        assert "required_key" in result.error
        assert audit_log[-1].status == "validation_failed"

    async def test_validation_success(self, make_executor):
        executor = make_executor()
        result = await executor.execute(
            "test.validated", make_params(tier=2, args={"required_key": "val"})
        )
        assert result.success is True
        assert result.data == "val"

    async def test_approval_denied(self, make_executor, audit_log):
        executor = make_executor(approval_status=ApprovalStatus.DENIED)
        result = await executor.execute("test.admin_action", make_params(tier=4))
        assert result.success is False
        assert result.approval_was_required is True
        assert "denied" in result.error.lower()
        assert "approval_denied" in audit_log[-1].status

    async def test_approval_approved(self, make_executor, audit_log):
        executor = make_executor(approval_status=ApprovalStatus.APPROVED)
        result = await executor.execute("test.admin_action", make_params(tier=4))
        assert result.success is True
        assert result.approval_was_required is True
        assert audit_log[-1].status == "success"

    async def test_execution_error_caught(self, make_executor, audit_log):
        executor = make_executor()
        result = await executor.execute("test.failing", make_params(tier=2))
        assert result.success is False
        assert "Something broke" in result.error
        assert audit_log[-1].status == "execution_error"

    async def test_execution_time_tracked(self, make_executor):
        executor = make_executor()
        result = await executor.execute("test.echo", make_params(tier=2, args={}))
        assert result.execution_time_ms >= 0

    async def test_audit_metadata_includes_category(self, make_executor, audit_log):
        executor = make_executor()
        await executor.execute("test.echo", make_params(tier=2, args={"q": "hi"}))
        entry = audit_log[-1]
        assert entry.action == "tool.test.echo"
        assert entry.metadata["category"] == "code"

    async def test_kill_switch_denies_pending_approvals(self, audit_log):
        """handle_kill() denies all pending approvals and cancels tasks."""
        async def audit_fn(entry):
            audit_log.append(entry)

        fake_approval = FakeApprovalManager(ApprovalStatus.APPROVED)
        executor = ToolExecutor(
            registry=ToolRegistry(),
            permission_checker=PermissionChecker(),
            audit_logger=audit_fn,
            approval_manager=fake_approval,
            max_concurrent=5,
        )
        # Verify handle_kill calls deny_all (via mock)
        from unittest.mock import MagicMock
        fake_approval.deny_all = MagicMock()
        executor.approvals = fake_approval
        executor.handle_kill()
        fake_approval.deny_all.assert_called_once()

    async def test_activity_feed_broadcast(self, audit_log):
        """_audit sends tool.activity notification when connection_manager is set."""
        sent_messages = []

        class FakeCM:
            async def send_to(self, conn_id, msg):
                sent_messages.append((conn_id, msg))

        async def audit_fn(entry):
            audit_log.append(entry)

        executor = ToolExecutor(
            registry=ToolRegistry(),
            permission_checker=PermissionChecker(),
            audit_logger=audit_fn,
            approval_manager=FakeApprovalManager(),
            connection_manager=FakeCM(),
        )
        result = await executor.execute("test.echo", make_params(tier=2, args={"x": 1}))
        assert result.success is True
        assert len(sent_messages) == 1
        conn_id, msg = sent_messages[0]
        assert msg["method"] == "tool.activity"
        assert msg["params"]["tool_name"] == "test.echo"
        assert msg["params"]["status"] == "success"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.tools.executor'`

- [ ] **Step 3: Implement ToolExecutor**

```python
# backend/nobla/tools/executor.py
"""Tool execution pipeline: permission -> approval -> execute -> audit."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Awaitable, Callable

import structlog

from nobla.security.audit import AuditEntry
from nobla.security.permissions import InsufficientPermissions, PermissionChecker, Tier
from nobla.tools.approval import ApprovalManager
from nobla.tools.models import ApprovalRequest, ApprovalStatus, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class ToolExecutor:
    """Runs tools through the 5-step execution pipeline."""

    def __init__(
        self,
        registry: ToolRegistry,
        permission_checker: PermissionChecker,
        audit_logger: Callable[[AuditEntry], Awaitable[None]],
        approval_manager: ApprovalManager,
        connection_manager=None,
        max_concurrent: int = 5,
    ):
        self.registry = registry
        self.checker = permission_checker
        self.audit = audit_logger
        self.approvals = approval_manager
        self._cm = connection_manager
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: set[asyncio.Task] = set()

    async def execute(self, tool_name: str, params: ToolParams) -> ToolResult:
        start = time.monotonic()

        # 1. Tool exists?
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # 2. Permission check
        try:
            self.checker.check(
                Tier(params.connection_state.tier), tool.tier
            )
        except InsufficientPermissions as exc:
            await self._audit(tool, params, "permission_denied", start)
            return ToolResult(success=False, error=str(exc))

        # 3. Validate params
        try:
            await tool.validate(params)
        except ValueError as exc:
            await self._audit(tool, params, "validation_failed", start)
            return ToolResult(success=False, error=f"Invalid params: {exc}")

        # 4. Approval (if required)
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
                request, params.connection_state.connection_id,
            )
            if status != ApprovalStatus.APPROVED:
                await self._audit(
                    tool, params, f"approval_{status.value}", start,
                )
                return ToolResult(
                    success=False,
                    error=f"Action {status.value} by user",
                    approval_was_required=True,
                )

        # 5. Execute (with concurrency control and task tracking)
        async with self._semaphore:
            task = asyncio.current_task()
            if task:
                self._running_tasks.add(task)
            try:
                result = await tool.execute(params)
                result.approval_was_required = approval_required
                result.execution_time_ms = int(
                    (time.monotonic() - start) * 1000
                )
                await self._audit(tool, params, "success", start)
                return result
            except asyncio.CancelledError:
                await self._audit(tool, params, "killed", start)
                return ToolResult(
                    success=False,
                    error="Tool execution cancelled by kill switch",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception as exc:
                await self._audit(tool, params, "execution_error", start)
                return ToolResult(
                    success=False,
                    error=f"Tool execution failed: {exc}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )
            finally:
                if task:
                    self._running_tasks.discard(task)

    def handle_kill(self) -> None:
        """Kill switch callback: deny approvals + cancel in-flight tasks."""
        self.approvals.deny_all()
        for task in self._running_tasks:
            task.cancel()
        self._running_tasks.clear()
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def _audit(self, tool, params: ToolParams, status: str, start: float):
        latency = int((time.monotonic() - start) * 1000)
        entry = AuditEntry(
            user_id=params.connection_state.user_id,
            action=f"tool.{tool.name}",
            method="tool.execute",
            tier=params.connection_state.tier,
            status=status,
            latency_ms=latency,
            metadata={
                "category": tool.category.value,
                "params": tool.get_params_summary(params),
            },
        )
        await self.audit(entry)

        # Broadcast activity feed notification
        if self._cm:
            conn_id = params.connection_state.connection_id
            await self._cm.send_to(conn_id, {
                "jsonrpc": "2.0",
                "method": "tool.activity",
                "params": {
                    "tool_name": tool.name,
                    "category": tool.category.value,
                    "description": tool.describe_action(params),
                    "status": status,
                    "execution_time_ms": latency,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_executor.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/executor.py backend/tests/test_tool_executor.py
git commit -m "feat(tools): add ToolExecutor with kill switch + activity feed

5-step pipeline, semaphore concurrency control, task cancellation
on kill switch, tool.activity WebSocket notifications."
```

---

## Task 6: Gateway Handlers & Code.Execute Migration

**Files:**
- Create: `backend/nobla/gateway/tool_handlers.py`
- Modify: `backend/nobla/gateway/code_handlers.py` (add tool platform delegation)
- Create: `backend/tests/test_tool_handlers.py`

- [ ] **Step 1: Write tests for gateway handlers**

```python
# backend/tests/test_tool_handlers.py
from __future__ import annotations

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.tools.models import ToolResult


class FakeExecutor:
    def __init__(self, result=None):
        self._result = result or ToolResult(success=True, data="ok")

    async def execute(self, tool_name, params):
        return self._result


class FakeRegistry:
    def list_available(self, tier):
        return []

    def list_by_category(self, category):
        return []


class TestToolHandlers:
    async def test_handle_tool_execute_no_executor(self):
        import nobla.gateway.tool_handlers as th
        th._tool_executor = None
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_execute(
            {"tool_name": "test.echo", "args": {}}, state
        )
        assert "error" in result

    async def test_handle_tool_execute_with_executor(self):
        import nobla.gateway.tool_handlers as th
        th._tool_executor = FakeExecutor()
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_execute(
            {"tool_name": "test.echo", "args": {"x": 1}}, state
        )
        assert result["success"] is True

    async def test_handle_tool_list_empty(self):
        import nobla.gateway.tool_handlers as th
        th._tool_registry = FakeRegistry()
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_tool_list({}, state)
        assert result == {"tools": []}

    async def test_handle_approval_response(self):
        import nobla.gateway.tool_handlers as th
        mock_mgr = MagicMock()
        th._approval_manager = mock_mgr
        state = ConnectionState(user_id="u1", tier=2)
        result = await th.handle_approval_response(
            {"request_id": "r1", "approved": True}, state
        )
        assert result["status"] == "acknowledged"
        mock_mgr.resolve.assert_called_once_with("r1", True)
```

- [ ] **Step 2: Create tool_handlers.py with RPC methods**

```python
# backend/nobla/gateway/tool_handlers.py
"""JSON-RPC handlers for the tool platform."""
from __future__ import annotations

from dataclasses import asdict

from nobla.gateway.websocket import ConnectionState, rpc_method
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams

# These are set during app lifespan initialization.
_tool_executor = None
_tool_registry = None
_approval_manager = None


def set_tool_executor(executor) -> None:
    global _tool_executor
    _tool_executor = executor


def get_tool_executor():
    return _tool_executor


def set_tool_registry(registry) -> None:
    global _tool_registry
    _tool_registry = registry


def get_tool_registry():
    return _tool_registry


def set_approval_manager(mgr) -> None:
    global _approval_manager
    _approval_manager = mgr


def get_approval_manager():
    return _approval_manager


@rpc_method("tool.execute")
async def handle_tool_execute(params: dict, state: ConnectionState) -> dict:
    """Execute a tool by name through the permission/approval pipeline."""
    executor = get_tool_executor()
    if not executor:
        return {"error": "Tool platform not initialized"}

    tool_params = ToolParams(
        args=params.get("args", {}),
        connection_state=state,
        context=params.get("context"),
    )
    result = await executor.execute(params["tool_name"], tool_params)
    return asdict(result)


@rpc_method("tool.list")
async def handle_tool_list(params: dict, state: ConnectionState) -> dict:
    """List available tools for the user's current tier."""
    registry = get_tool_registry()
    if not registry:
        return {"tools": []}

    tier = Tier(state.tier)
    category = params.get("category")

    if category:
        tools = [
            t
            for t in registry.list_by_category(ToolCategory(category))
            if t.tier <= tier
        ]
    else:
        tools = registry.list_available(tier)

    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "tier": int(t.tier),
                "requires_approval": t.requires_approval,
            }
            for t in tools
        ]
    }


@rpc_method("tool.approval_response")
async def handle_approval_response(
    params: dict, state: ConnectionState,
) -> dict:
    """User's approval/denial of a pending tool action."""
    mgr = get_approval_manager()
    if mgr:
        mgr.resolve(params["request_id"], params["approved"])
    return {"status": "acknowledged"}
```

- [ ] **Step 3: Migrate code.execute in code_handlers.py**

In `backend/nobla/gateway/code_handlers.py` (extracted in Task 0), update `handle_code_execute` to delegate to the tool platform when available:

```python
@rpc_method("code.execute")
async def handle_code_execute(params: dict, state: ConnectionState) -> dict:
    """Execute code — delegates to tool platform when available."""
    from nobla.gateway.tool_handlers import get_tool_executor

    executor = get_tool_executor()
    if executor:
        from dataclasses import asdict

        from nobla.tools.models import ToolParams

        tool_params = ToolParams(
            args={
                "code": params.get("code", ""),
                "language": params.get("language", "python"),
                "timeout": params.get("timeout"),
            },
            connection_state=state,
        )
        result = await executor.execute("code.run", tool_params)
        return asdict(result)

    # Fallback: direct sandbox execution (pre-tool-platform)
    pc = get_permission_checker()
    if pc:
        pc.check(current_tier=Tier(state.tier), required_tier=Tier.STANDARD)

    sm = get_sandbox_manager()
    if not sm:
        return {"error": "Sandbox not initialized"}

    code = params.get("code", "")
    language = params.get("language", "python")
    timeout = params.get("timeout")

    result = await sm.execute(code=code, language=language, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
        "timed_out": result.timed_out,
    }
```

- [ ] **Step 4: Run tests (unit + existing)**

Run: `cd backend && python -m pytest tests/test_tool_handlers.py tests/ -v --ignore=tests/integration`
Expected: All tests PASS including 4 new handler tests

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration`
Expected: All existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/tool_handlers.py backend/nobla/gateway/code_handlers.py backend/tests/test_tool_handlers.py
git commit -m "feat(tools): add gateway RPC handlers + migrate code.execute

tool.execute, tool.list, tool.approval_response RPC methods.
code.execute now delegates to tool platform when available."
```

---

## Task 7: Configuration Settings

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Create: `backend/tests/test_tool_settings.py`

**Note:** `VisionSettings`, `ComputerControlSettings`, and `RemoteControlSettings` are deferred to their respective sub-phase plans (4A, 4B, 4D). Only `ToolPlatformSettings` is needed for the platform foundation.

- [ ] **Step 1: Write test for settings**

```python
# backend/tests/test_tool_settings.py
from __future__ import annotations

from nobla.config.settings import Settings


class TestToolPlatformSettings:
    def test_defaults(self):
        settings = Settings()
        assert settings.tools.enabled is True
        assert settings.tools.default_approval_timeout == 30
        assert settings.tools.activity_feed_enabled is True
        assert settings.tools.max_concurrent_tools == 5

    def test_override(self):
        settings = Settings(tools={"enabled": False, "max_concurrent_tools": 10})
        assert settings.tools.enabled is False
        assert settings.tools.max_concurrent_tools == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tool_settings.py -v`
Expected: FAIL — `tools` attribute does not exist on `Settings`

- [ ] **Step 3: Add ToolPlatformSettings to settings.py**

Add the new settings class before the `Settings` root class, and add it to the root:

```python
class ToolPlatformSettings(BaseModel):
    """Settings for the tool execution platform."""

    enabled: bool = True
    default_approval_timeout: int = 30
    activity_feed_enabled: bool = True
    max_concurrent_tools: int = 5
```

Add to the `Settings` root class:

```python
    tools: ToolPlatformSettings = ToolPlatformSettings()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_settings.py tests/ -k "settings or config or tool_settings" -v`
Expected: All tests PASS including 2 new settings tests

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/config/settings.py backend/tests/test_tool_settings.py
git commit -m "feat(config): add ToolPlatformSettings

Settings for tool platform: enabled, approval timeout,
activity feed, max concurrent tools."
```

---

## Task 8: Package Init & Wiring

**Files:**
- Modify: `backend/nobla/tools/__init__.py`
- Modify: `backend/nobla/gateway/app.py`

- [ ] **Step 1: Update tools/__init__.py**

```python
# backend/nobla/tools/__init__.py
"""Nobla tool platform — registry, executor, and auto-discovered tools."""
from nobla.tools.registry import ToolRegistry

tool_registry = ToolRegistry()

__all__ = ["tool_registry"]
```

- [ ] **Step 2: Wire ToolExecutor into app lifespan**

In `backend/nobla/gateway/app.py`, add tool platform initialization after the existing sandbox manager setup (around line 155). Add these lines in the lifespan function:

```python
    # --- Tool Platform (Phase 4) ---
    from nobla.tools import tool_registry
    from nobla.tools.approval import ApprovalManager
    from nobla.tools.executor import ToolExecutor
    from nobla.gateway.tool_handlers import (
        set_tool_executor,
        set_tool_registry,
        set_approval_manager,
    )

    approval_manager = ApprovalManager(connection_manager=manager)
    tool_executor = ToolExecutor(
        registry=tool_registry,
        permission_checker=pc,
        audit_logger=_log_audit,
        approval_manager=approval_manager,
        connection_manager=manager,
        max_concurrent=settings.tools.max_concurrent_tools,
    )

    # Register kill switch callback
    ks = get_kill_switch()
    if ks:
        ks.on_soft_kill(tool_executor.handle_kill)

    set_tool_executor(tool_executor)
    set_tool_registry(tool_registry)
    set_approval_manager(approval_manager)
```

Also add the audit helper function (if not already present):

```python
async def _log_audit(entry: AuditEntry) -> None:
    """Log an audit entry via structlog."""
    logger.info(
        "audit",
        user_id=entry.user_id,
        action=entry.action,
        status=entry.status,
        latency_ms=entry.latency_ms,
        tier=entry.tier,
        **entry.metadata,
    )
```

Also ensure `import nobla.gateway.tool_handlers` is present so the RPC methods get registered:

```python
    import nobla.gateway.tool_handlers  # noqa: F401 — register RPC methods
```

- [ ] **Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/nobla/tools/__init__.py backend/nobla/gateway/app.py
git commit -m "feat(tools): wire tool platform into app lifespan

Initialize ToolExecutor, ApprovalManager, register kill switch
callback, and set service accessors in gateway."
```

---

## Task 9: Integration Test

**Files:**
- Create: `backend/tests/integration/test_tool_flow.py`

- [ ] **Step 1: Write integration test**

```python
# backend/tests/integration/test_tool_flow.py
"""End-to-end tool execution via WebSocket."""
from __future__ import annotations

import pytest

from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestToolFlow:
    async def test_tool_list_returns_tools(self, authenticated_client: RpcClient):
        """Authenticated user can list available tools."""
        result = await authenticated_client.call_expect_result("tool.list", {})
        assert "tools" in result
        assert isinstance(result["tools"], list)

    async def test_tool_list_filtered_by_category(self, authenticated_client: RpcClient):
        """Can filter tool list by category."""
        result = await authenticated_client.call_expect_result(
            "tool.list", {"category": "code"}
        )
        assert "tools" in result
        for tool in result["tools"]:
            assert tool["category"] == "code"

    async def test_tool_execute_unknown_tool(self, authenticated_client: RpcClient):
        """Unknown tool returns error."""
        result = await authenticated_client.call_expect_result(
            "tool.execute", {"tool_name": "nonexistent.tool", "args": {}}
        )
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    async def test_tool_execute_permission_denied(self, ws_client: RpcClient):
        """Unauthenticated user (SAFE tier) denied access to ELEVATED+ tools."""
        # Register but don't escalate — stays at SAFE tier
        await ws_client.call_expect_result(
            "system.register",
            {"passphrase": "testpassphrase123"},
        )
        result = await ws_client.call_expect_result(
            "tool.execute",
            {"tool_name": "test.admin_action", "args": {}},
        )
        # Should fail — either unknown (no test tools in prod) or permission denied
        assert result["success"] is False

    async def test_approval_response_acknowledged(self, authenticated_client: RpcClient):
        """Approval response returns acknowledged even if no pending request."""
        result = await authenticated_client.call_expect_result(
            "tool.approval_response",
            {"request_id": "nonexistent", "approved": True},
        )
        assert result["status"] == "acknowledged"
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && python -m pytest tests/integration/test_tool_flow.py -v -m integration`
Expected: All 5 tests PASS (some may be skipped if no backend is running)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_tool_flow.py
git commit -m "test(tools): add integration tests for tool platform

End-to-end tests: tool.list, tool.execute, permissions, approval."
```

---

## Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration --cov=nobla.tools`
Expected: All tests PASS, coverage for `nobla.tools` > 90%

- [ ] **Step 2: Run linter**

Run: `cd backend && python -m ruff check nobla/tools/ nobla/gateway/tool_handlers.py`
Expected: No errors

- [ ] **Step 3: Run type checker**

Run: `cd backend && python -m mypy nobla/tools/ nobla/gateway/tool_handlers.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 4: Verify file line counts**

Run: `wc -l backend/nobla/tools/*.py backend/nobla/gateway/tool_handlers.py`
Expected: All files under 200 lines, well within 750-line limit

- [ ] **Step 5: Final commit with all files verified**

```bash
git add -A
git status  # Verify only expected files
git commit -m "feat(tools): Phase 4-Pre complete — Tool Platform Foundation

Tool platform with BaseTool ABC, @register_tool decorator, ToolRegistry,
ToolExecutor (5-step pipeline), ApprovalManager, gateway RPC handlers,
and kill switch integration. All tests passing."
```

---

## Summary

| Task | Files Created | Files Modified | Tests |
|------|--------------|----------------|-------|
| 0. Gateway Prereq | `gateway/code_handlers.py` | `websocket.py` | — |
| 1. Data Models | `tools/models.py` | — | 7 |
| 2. BaseTool ABC | `tools/base.py` | — | 8 |
| 3. Registry | `tools/registry.py` | — | 10 |
| 4. Approval | `tools/approval.py` | — | 7 |
| 5. Executor | `tools/executor.py` | — | 12 |
| 6. Gateway | `gateway/tool_handlers.py` | `code_handlers.py` | 4 |
| 7. Config | `test_tool_settings.py` | `config/settings.py` | 2 |
| 8. Wiring | — | `tools/__init__.py`, `app.py` | — |
| 9. Integration | `test_tool_flow.py` | — | 5 |
| 10. Verification | — | — | — |
| **Total** | **9 new files** | **5 modified** | **55 tests** |

**Estimated total lines:** ~440 (platform + kill switch + activity) + ~80 (gateway) + ~35 (code_handlers) + ~15 (config) + ~600 (tests) = **~1,170 lines**
