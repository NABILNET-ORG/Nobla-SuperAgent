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
