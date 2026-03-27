# backend/tests/gateway/test_mirror_handlers.py
"""Tests for mirror subscription and capture handlers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.gateway.mirror_handlers import (
    handle_mirror_subscribe,
    handle_mirror_unsubscribe,
    handle_mirror_capture,
    is_mirror_active,
    remove_subscriber,
    _mirror_subscribers,
)
from nobla.gateway.websocket import ConnectionState


@pytest.fixture(autouse=True)
def _clear_subscribers():
    _mirror_subscribers.clear()
    yield
    _mirror_subscribers.clear()


def _make_state(cid: str = "conn-1") -> ConnectionState:
    return ConnectionState(connection_id=cid, user_id="user-1", tier=4)


@pytest.mark.asyncio
async def test_subscribe_adds_connection():
    state = _make_state()
    result = await handle_mirror_subscribe({}, state)
    assert result == {"status": "subscribed"}
    assert is_mirror_active("conn-1")


@pytest.mark.asyncio
async def test_unsubscribe_removes_connection():
    state = _make_state()
    await handle_mirror_subscribe({}, state)
    result = await handle_mirror_unsubscribe({}, state)
    assert result == {"status": "unsubscribed"}
    assert not is_mirror_active("conn-1")


@pytest.mark.asyncio
async def test_unsubscribe_noop_when_not_subscribed():
    state = _make_state()
    result = await handle_mirror_unsubscribe({}, state)
    assert result == {"status": "unsubscribed"}


def test_remove_subscriber_cleans_up():
    _mirror_subscribers.add("conn-1")
    remove_subscriber("conn-1")
    assert not is_mirror_active("conn-1")


def test_remove_subscriber_noop_for_unknown():
    remove_subscriber("unknown")  # Should not raise


@pytest.mark.asyncio
async def test_capture_returns_screenshot():
    mock_registry = MagicMock()
    mock_tool = AsyncMock()
    mock_tool.execute = AsyncMock(return_value=MagicMock(
        success=True, data={"screenshot_b64": "abc123"}
    ))
    mock_registry.get.return_value = mock_tool

    with patch("nobla.gateway.mirror_handlers._get_registry", return_value=mock_registry):
        state = _make_state()
        result = await handle_mirror_capture({}, state)
        assert result["screenshot_b64"] == "abc123"
        assert result["error"] is None


@pytest.mark.asyncio
async def test_capture_returns_error_when_tool_unavailable():
    with patch("nobla.gateway.mirror_handlers._get_registry", return_value=MagicMock(get=MagicMock(return_value=None))):
        state = _make_state()
        result = await handle_mirror_capture({}, state)
        assert result["screenshot_b64"] is None
        assert "unavailable" in result["error"].lower()
