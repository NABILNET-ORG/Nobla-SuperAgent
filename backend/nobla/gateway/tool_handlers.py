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
