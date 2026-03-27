# backend/tests/tools/test_executor_mirror.py
"""Test that executor triggers mirror capture after tool.activity broadcast."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.tools.executor import ToolExecutor
from nobla.tools.models import ToolParams
from nobla.gateway.websocket import ConnectionState


@pytest.mark.asyncio
async def test_audit_triggers_mirror_capture_when_subscribed():
    """When mirror is active for a connection, _audit should spawn capture task."""
    mock_registry = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "test.tool"
    mock_tool.category = MagicMock(value="code")
    mock_tool.describe_action.return_value = "Test action"
    mock_tool.get_params_summary.return_value = {}

    mock_cm = AsyncMock()
    mock_audit = AsyncMock()

    executor = ToolExecutor(
        registry=mock_registry,
        permission_checker=MagicMock(),
        audit_logger=mock_audit,
        approval_manager=MagicMock(),
        connection_manager=mock_cm,
    )

    state = ConnectionState(connection_id="conn-1", user_id="u1", tier=4)
    params = ToolParams(args={}, connection_state=state)

    with patch("nobla.tools.executor.is_mirror_active", return_value=True), \
         patch("nobla.tools.executor.is_capture_in_progress", return_value=False), \
         patch("nobla.tools.executor.capture_and_send", new_callable=AsyncMock) as mock_capture, \
         patch("asyncio.create_task") as mock_create_task:
        import time
        await executor._audit(mock_tool, params, "success", time.monotonic())
        mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_audit_skips_mirror_when_not_subscribed():
    """When mirror is not active, no capture task is spawned."""
    mock_cm = AsyncMock()
    mock_audit = AsyncMock()
    mock_tool = MagicMock()
    mock_tool.name = "test.tool"
    mock_tool.category = MagicMock(value="code")
    mock_tool.describe_action.return_value = "Test"
    mock_tool.get_params_summary.return_value = {}

    executor = ToolExecutor(
        registry=MagicMock(),
        permission_checker=MagicMock(),
        audit_logger=mock_audit,
        approval_manager=MagicMock(),
        connection_manager=mock_cm,
    )

    state = ConnectionState(connection_id="conn-1", user_id="u1", tier=4)
    params = ToolParams(args={}, connection_state=state)

    with patch("nobla.tools.executor.is_mirror_active", return_value=False), \
         patch("asyncio.create_task") as mock_create_task:
        import time
        await executor._audit(mock_tool, params, "success", time.monotonic())
        mock_create_task.assert_not_called()
