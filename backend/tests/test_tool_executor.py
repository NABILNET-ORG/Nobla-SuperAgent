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


class EchoTool(BaseTool):
    name = "test.echo"
    description = "Echo input"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data=params.args)


class AdminApprovalTool(BaseTool):
    name = "test.admin_action"
    description = "Admin action"
    category = ToolCategory.INPUT
    tier = Tier.ADMIN
    requires_approval = True
    approval_timeout = 2

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="executed")


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


class FailingTool(BaseTool):
    name = "test.failing"
    description = "Always fails"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        raise RuntimeError("Something broke")


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry and register test tools for each test."""
    _TOOL_REGISTRY.clear()
    _TOOL_REGISTRY["test.echo"] = EchoTool()
    _TOOL_REGISTRY["test.admin_action"] = AdminApprovalTool()
    _TOOL_REGISTRY["test.validated"] = ValidatingTool()
    _TOOL_REGISTRY["test.failing"] = FailingTool()
    yield
    _TOOL_REGISTRY.clear()


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
