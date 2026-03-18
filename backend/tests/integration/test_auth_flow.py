from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestAuthFlow:
    async def test_register_returns_tokens(self, ws_client: RpcClient):
        result = await ws_client.call_expect_result("system.register", {
            "passphrase": "test-passphrase-12345678",
            "display_name": "Test User",
        })
        assert "user_id" in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["display_name"] == "Test User"

    async def test_register_rejects_short_passphrase(self, ws_client: RpcClient):
        result = await ws_client.call_expect_result("system.register", {
            "passphrase": "short",
            "display_name": "Test User",
        })
        assert "error" in result or "min_length" in result

    async def test_authenticate_with_token(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("system.status")
        assert result["version"] == "0.1.0"

    async def test_unauthenticated_chat_rejected(self, ws_client: RpcClient):
        error = await ws_client.call_expect_error("chat.send", {"message": "hello"})
        assert error["code"] == -32011

    async def test_unauthenticated_surface(self, ws_client: RpcClient):
        health = await ws_client.call_expect_result("system.health")
        assert "status" in health

    async def test_token_refresh(self, ws_client: RpcClient):
        reg = await ws_client.call_expect_result("system.register", {
            "passphrase": "test-passphrase-refresh",
            "display_name": "Refresh Test",
        })
        refresh_result = await ws_client.call_expect_result("system.refresh", {
            "refresh_token": reg["refresh_token"],
        })
        assert "access_token" in refresh_result
        assert "refresh_token" in refresh_result
