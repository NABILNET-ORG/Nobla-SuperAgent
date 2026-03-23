from __future__ import annotations

import pytest

from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult


class ConcreteTool(BaseTool):
    name = "test.echo"
    description = "Echo the input back"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        return ToolResult(success=True, data=params.args)


class AdminTool(BaseTool):
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
