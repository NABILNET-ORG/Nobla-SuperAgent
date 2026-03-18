"""Integration tests for Phase 1B security wiring."""

from starlette.testclient import TestClient
from nobla.gateway.app import create_app
from nobla.gateway.websocket import (
    set_auth_service,
    set_kill_switch,
    set_cost_tracker,
    set_permission_checker,
    set_sandbox_manager,
)
from nobla.security import (
    AuthService, KillSwitch, CostTracker, PermissionChecker,
    SandboxConfig, SandboxManager,
)


def _setup_security():
    """Initialize security services for testing (bypasses lifespan)."""
    set_auth_service(AuthService(
        secret_key="test-secret-key-for-testing-only",
        access_expire_minutes=60,
        refresh_expire_days=7,
        bcrypt_rounds=4,  # Fast for tests
    ))
    set_kill_switch(KillSwitch())
    set_cost_tracker(CostTracker())
    set_permission_checker(PermissionChecker(escalation_requires_passphrase=[3, 4]))
    set_sandbox_manager(SandboxManager(SandboxConfig()))


def _app():
    _setup_security()
    return create_app()


def _register(ws):
    """Helper: register a user and return the result."""
    ws.send_json({
        "jsonrpc": "2.0", "method": "system.register",
        "params": {"passphrase": "mysecretphrase", "display_name": "Nabil"},
        "id": 99,
    })
    return ws.receive_json()


def test_unauthenticated_chat_rejected():
    """chat.send should fail without authentication."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "chat.send", "params": {"message": "hi"}, "id": 1})
        data = ws.receive_json()
        assert data["error"]["code"] == -32011  # AUTH_REQUIRED


def test_health_works_without_auth():
    """system.health should work without authentication."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "system.health", "id": 1})
        data = ws.receive_json()
        assert data["result"]["status"] == "ok"


def test_register_and_authenticate():
    """Register a user then use authenticated methods."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        data = _register(ws)
        assert "user_id" in data["result"]
        assert "access_token" in data["result"]

        # After register, user_id is set — costs should work
        ws.send_json({"jsonrpc": "2.0", "method": "system.costs", "id": 2})
        data = ws.receive_json()
        assert "session_usd" in data["result"]


def test_register_short_passphrase():
    """Registration with short passphrase should fail."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_json({
            "jsonrpc": "2.0", "method": "system.register",
            "params": {"passphrase": "short"},
            "id": 1,
        })
        data = ws.receive_json()
        assert "error" in data["result"]


def test_system_kill_changes_state():
    """system.kill should trigger kill switch."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        _register(ws)
        ws.send_json({"jsonrpc": "2.0", "method": "system.kill", "id": 2})
        data = ws.receive_json()
        assert data["result"]["state"] in ["soft_killing", "killed"]


def test_killed_server_rejects_requests():
    """After kill, non-exempt methods should be rejected."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        _register(ws)

        # Kill
        ws.send_json({"jsonrpc": "2.0", "method": "system.kill", "id": 2})
        ws.receive_json()

        # Try costs (should be rejected)
        ws.send_json({"jsonrpc": "2.0", "method": "system.costs", "id": 3})
        data = ws.receive_json()
        assert data["error"]["code"] == -32030  # SERVER_KILLED

        # Health should still work
        ws.send_json({"jsonrpc": "2.0", "method": "system.health", "id": 4})
        data = ws.receive_json()
        assert data["result"]["status"] == "ok"


def test_escalation_flow():
    """Test tier escalation with passphrase requirement."""
    client = TestClient(_app())
    with client.websocket_connect("/ws") as ws:
        _register(ws)

        # Escalate to tier 2 (no passphrase needed)
        ws.send_json({
            "jsonrpc": "2.0", "method": "system.escalate",
            "params": {"tier": 2}, "id": 2,
        })
        data = ws.receive_json()
        assert data["result"]["tier"] == 2

        # Escalate to tier 3 without passphrase (should fail)
        ws.send_json({
            "jsonrpc": "2.0", "method": "system.escalate",
            "params": {"tier": 3}, "id": 3,
        })
        data = ws.receive_json()
        assert "error" in data["result"]

        # Escalate to tier 3 with passphrase
        ws.send_json({
            "jsonrpc": "2.0", "method": "system.escalate",
            "params": {"tier": 3, "passphrase": "mysecretphrase"},
            "id": 4,
        })
        data = ws.receive_json()
        assert data["result"]["tier"] == 3
