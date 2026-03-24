"""Tests for CodeExecutionSettings and Phase 4C platform changes."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from nobla.config.settings import CodeExecutionSettings, Settings, SandboxSettings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import PermissionChecker, Tier
from nobla.tools.approval import ApprovalManager
from nobla.tools.base import BaseTool
from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import ToolRegistry, _TOOL_REGISTRY


# --- CodeExecutionSettings ---


class TestCodeExecutionSettings:
    def test_defaults(self):
        s = CodeExecutionSettings()
        assert s.enabled is True
        assert s.default_language == "python"
        assert s.supported_languages == ["python", "javascript", "bash"]
        assert s.package_volume_prefix == "nobla-pkg"
        assert s.persist_packages is False
        assert s.max_output_length == 50000
        assert s.codegen_max_tokens == 4096
        assert s.debug_max_error_length == 5000
        assert s.git_allowed_hosts == ["github.com", "gitlab.com"]
        assert s.git_timeout == 120
        assert s.git_workspace_volume_prefix == "nobla-git"
        assert s.git_image == "alpine/git:latest"

    def test_custom_values(self):
        s = CodeExecutionSettings(
            default_language="javascript",
            persist_packages=True,
            git_allowed_hosts=["github.com", "gitlab.com", "bitbucket.org"],
        )
        assert s.default_language == "javascript"
        assert s.persist_packages is True
        assert len(s.git_allowed_hosts) == 3

    def test_wired_into_settings(self):
        s = Settings()
        assert hasattr(s, "code")
        assert isinstance(s.code, CodeExecutionSettings)
        assert s.code.enabled is True


class TestSandboxAllowedImages:
    def test_includes_code_images(self):
        s = SandboxSettings()
        assert "python:3.12-slim" in s.allowed_images
        assert "node:20-slim" in s.allowed_images
        assert "alpine/git:latest" in s.allowed_images


# --- BaseTool.needs_approval ---


class _ConditionalApprovalTool(BaseTool):
    name = "test.conditional"
    description = "Tool with conditional approval"
    category = ToolCategory.CODE
    tier = Tier.ELEVATED
    requires_approval = False

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("dangerous", False)

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="done")


class _StaticApprovalTool(BaseTool):
    name = "test.static_approval"
    description = "Tool with static approval"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = True

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data="done")


class TestNeedsApproval:
    def test_default_returns_class_variable_false(self):
        tool = _ConditionalApprovalTool()
        base_tool = _StaticApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ADMIN.value
        )
        params = ToolParams(args={}, connection_state=state)
        assert base_tool.needs_approval(params) is True

    def test_override_returns_false_for_safe_params(self):
        tool = _ConditionalApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ELEVATED.value
        )
        params = ToolParams(args={"dangerous": False}, connection_state=state)
        assert tool.needs_approval(params) is False

    def test_override_returns_true_for_dangerous_params(self):
        tool = _ConditionalApprovalTool()
        state = ConnectionState(
            connection_id="c1", user_id="u1", tier=Tier.ELEVATED.value
        )
        params = ToolParams(args={"dangerous": True}, connection_state=state)
        assert tool.needs_approval(params) is True


# --- ToolExecutor uses needs_approval ---


class TestExecutorUsesNeedsApproval:
    @pytest.fixture()
    def state(self):
        return ConnectionState(
            connection_id="conn1", user_id="user1", tier=Tier.ELEVATED.value
        )

    @pytest.fixture()
    def executor(self):
        _TOOL_REGISTRY.clear()
        registry = ToolRegistry()
        cond_tool = _ConditionalApprovalTool()
        _TOOL_REGISTRY[cond_tool.name] = cond_tool
        checker = PermissionChecker()
        audit = AsyncMock()
        cm = AsyncMock()
        approvals = ApprovalManager(cm)
        return ToolExecutor(registry, checker, audit, approvals)

    @pytest.mark.asyncio
    async def test_no_approval_when_needs_approval_false(self, executor, state):
        params = ToolParams(
            args={"dangerous": False}, connection_state=state
        )
        result = await executor.execute("test.conditional", params)
        assert result.success is True
        assert result.approval_was_required is False

    @pytest.mark.asyncio
    async def test_approval_triggered_when_needs_approval_true(self, executor, state):
        params = ToolParams(
            args={"dangerous": True}, connection_state=state
        )
        tool = _TOOL_REGISTRY["test.conditional"]
        tool.approval_timeout = 1
        result = await executor.execute("test.conditional", params)
        assert result.success is False
        assert result.approval_was_required is True
        assert "timed_out" in result.error
