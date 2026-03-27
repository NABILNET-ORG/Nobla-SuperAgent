# backend/nobla/gateway/mirror_handlers.py
"""Mirror subscription and on-demand capture RPC handlers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from nobla.gateway.websocket import ConnectionState, rpc_method
from nobla.tools.models import ToolParams

logger = structlog.get_logger(__name__)

# Active mirror subscribers (connection IDs).
_mirror_subscribers: set[str] = set()
_capture_in_progress: bool = False


def _get_registry():
    from nobla.gateway.tool_handlers import get_tool_registry
    return get_tool_registry()


def _get_connection_manager():
    from nobla.gateway.tool_handlers import get_tool_executor
    executor = get_tool_executor()
    return executor._cm if executor else None


@rpc_method("tool.mirror.subscribe")
async def handle_mirror_subscribe(
    params: dict, state: ConnectionState,
) -> dict:
    _mirror_subscribers.add(state.connection_id)
    logger.info("mirror.subscribed", connection_id=state.connection_id)
    return {"status": "subscribed"}


@rpc_method("tool.mirror.unsubscribe")
async def handle_mirror_unsubscribe(
    params: dict, state: ConnectionState,
) -> dict:
    _mirror_subscribers.discard(state.connection_id)
    logger.info("mirror.unsubscribed", connection_id=state.connection_id)
    return {"status": "unsubscribed"}


@rpc_method("tool.mirror.capture")
async def handle_mirror_capture(
    params: dict, state: ConnectionState,
) -> dict:
    """On-demand screenshot capture — request/response pattern."""
    registry = _get_registry()
    if not registry:
        return {"screenshot_b64": None, "error": "Tool platform not initialized"}

    tool = registry.get("screenshot.capture")
    if not tool:
        return {"screenshot_b64": None, "error": "Screenshot tool unavailable"}

    try:
        tool_params = ToolParams(
            args={},
            connection_state=state,
        )
        result = await tool.execute(tool_params)
        if result.success and result.data:
            b64 = result.data.get("screenshot_b64")
            return {"screenshot_b64": b64, "error": None}
        return {"screenshot_b64": None, "error": result.error or "Capture failed"}
    except Exception as exc:
        logger.warning("mirror.capture_failed", error=str(exc))
        return {"screenshot_b64": None, "error": f"Capture failed: {exc}"}


def is_mirror_active(connection_id: str) -> bool:
    return connection_id in _mirror_subscribers


def is_capture_in_progress() -> bool:
    return _capture_in_progress


async def capture_and_send(connection_id: str) -> None:
    """Background task: capture screenshot and send as mirror.frame notification."""
    global _capture_in_progress
    _capture_in_progress = True
    try:
        registry = _get_registry()
        cm = _get_connection_manager()
        if not registry or not cm:
            return

        tool = registry.get("screenshot.capture")
        if not tool:
            return

        state = ConnectionState(connection_id=connection_id)
        tool_params = ToolParams(args={}, connection_state=state)
        result = await tool.execute(tool_params)

        if result.success and result.data:
            b64 = result.data.get("screenshot_b64")
            if b64:
                await cm.send_to(connection_id, {
                    "jsonrpc": "2.0",
                    "method": "tool.mirror.frame",
                    "params": {
                        "screenshot_b64": b64,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })
    except Exception as exc:
        logger.warning("mirror.background_capture_failed", error=str(exc))
    finally:
        _capture_in_progress = False


def remove_subscriber(connection_id: str) -> None:
    """Clean up on WebSocket disconnect."""
    _mirror_subscribers.discard(connection_id)
