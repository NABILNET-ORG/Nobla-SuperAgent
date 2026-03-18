from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestChatFlow:
    async def test_send_message_returns_response(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "What is 2 + 2?",
        })
        assert "message" in result
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    async def test_response_includes_metadata(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "Say hello",
        })
        assert "model" in result
        assert "tokens_used" in result
        assert "cost_usd" in result

    async def test_chat_with_conversation_id(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "Hello",
            "conversation_id": "test-conv-123",
        })
        assert "message" in result
