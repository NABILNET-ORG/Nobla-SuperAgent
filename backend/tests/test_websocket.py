from starlette.testclient import TestClient
from nobla.gateway.app import create_app
from nobla.gateway.websocket import set_auth_service
from nobla.security import AuthService


def _app():
    return create_app()


def test_websocket_health():
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "system.health", "id": 1})
        data = ws.receive_json()
        assert data["result"]["status"] == "ok"
        assert data["id"] == 1


def test_websocket_invalid_json():
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not valid json{")
        data = ws.receive_json()
        assert data["error"]["code"] == -32700


def test_websocket_method_not_found():
    """Unauthenticated requests to unknown methods get AUTH_REQUIRED."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "nonexistent", "id": 1})
        data = ws.receive_json()
        assert data["error"]["code"] == -32011  # AUTH_REQUIRED (before method lookup)


def test_websocket_method_not_found_authenticated():
    """Authenticated requests to unknown methods get METHOD_NOT_FOUND."""
    set_auth_service(AuthService(
        secret_key="test-secret-key-for-testing-only",
        bcrypt_rounds=4,
    ))
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        # Register to get auth
        ws.send_json({
            "jsonrpc": "2.0", "method": "system.register",
            "params": {"passphrase": "mysecretphrase"},
            "id": 1,
        })
        ws.receive_json()

        ws.send_json({"jsonrpc": "2.0", "method": "nonexistent", "id": 2})
        data = ws.receive_json()
        assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_websocket_authenticate_no_credentials():
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "system.authenticate", "params": {}, "id": 1})
        data = ws.receive_json()
        assert data["result"]["authenticated"] is False
