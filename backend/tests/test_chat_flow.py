from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient
from nobla.gateway.app import create_app
from nobla.gateway.websocket import set_auth_service
from nobla.brain.base_provider import LLMResponse
from nobla.security import AuthService


def test_chat_send_returns_response():
    mock_response = LLMResponse(
        content="Hello from test!",
        model="test-model",
        tokens_input=5,
        tokens_output=10,
        cost_usd=0.0,
        latency_ms=50,
    )
    app = create_app()
    # Set up auth service for registration
    set_auth_service(AuthService(
        secret_key="test-secret-key-for-testing-only",
        bcrypt_rounds=4,
    ))

    with patch("nobla.gateway.websocket.get_router") as mock_get_router:
        mock_router = AsyncMock()
        mock_router.route.return_value = mock_response
        mock_get_router.return_value = mock_router

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            # Register first (auth required for chat.send)
            ws.send_json({
                "jsonrpc": "2.0", "method": "system.register",
                "params": {"passphrase": "testpassphrase"},
                "id": 0,
            })
            ws.receive_json()

            ws.send_json({
                "jsonrpc": "2.0",
                "method": "chat.send",
                "params": {"message": "hello"},
                "id": 1,
            })
            data = ws.receive_json()
            assert data["result"]["message"] == "Hello from test!"
            assert data["result"]["model"] == "test-model"
            assert data["id"] == 1
