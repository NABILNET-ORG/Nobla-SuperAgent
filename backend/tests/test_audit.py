import pytest
from nobla.security.audit import sanitize_params, AuditEntry


def test_sanitize_removes_passphrase():
    params = {"passphrase": "secret123", "message": "hello"}
    clean = sanitize_params(params)
    assert clean["passphrase"] == "[REDACTED]"
    assert clean["message"] == "hello"


def test_sanitize_truncates_long_content():
    params = {"message": "x" * 1000}
    clean = sanitize_params(params, max_content_length=500)
    assert len(clean["message"]) == 503  # 500 + "..."


def test_sanitize_nested_passphrase():
    params = {"auth": {"passphrase": "secret", "user": "nabil"}}
    clean = sanitize_params(params)
    assert clean["auth"]["passphrase"] == "[REDACTED]"


def test_audit_entry_creation():
    entry = AuditEntry(
        user_id="user-123", action="rpc_call", method="chat.send",
        tier=1, status="success", latency_ms=50,
    )
    assert entry.method == "chat.send"
    assert entry.status == "success"
