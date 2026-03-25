"""Tests for RemoteControlGuard."""

import re

import pytest

from nobla.config.settings import RemoteControlSettings


# --------------- helpers ---------------

def _make_settings(**overrides) -> RemoteControlSettings:
    defaults = {
        "allowed_hosts": ["prod.example.com", "staging.example.com"],
        "allowed_users": ["deploy"],
        "max_connections": 3,
    }
    defaults.update(overrides)
    return RemoteControlSettings(**defaults)


@pytest.fixture(autouse=True)
def _reset_guard():
    from nobla.tools.remote.safety import RemoteControlGuard
    RemoteControlGuard.reset()
    yield
    RemoteControlGuard.reset()


# --------------- halt / resume ---------------

class TestHaltResume:
    def test_check_connect_raises_when_halted(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        RemoteControlGuard.halt()
        with pytest.raises(RemoteControlError, match="halted"):
            RemoteControlGuard.check("connect", _make_settings(), host="prod.example.com")

    def test_check_command_raises_when_halted(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        RemoteControlGuard.halt()
        with pytest.raises(RemoteControlError, match="halted"):
            RemoteControlGuard.check("command", _make_settings(), command="ls")

    def test_check_transfer_raises_when_halted(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        RemoteControlGuard.halt()
        with pytest.raises(RemoteControlError, match="halted"):
            RemoteControlGuard.check("transfer", _make_settings(), file_size=100)

    def test_resume_clears_halt(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.halt()
        RemoteControlGuard.resume()
        # Should not raise
        RemoteControlGuard.check("connect", _make_settings(), host="prod.example.com")

    def test_reset_clears_halt(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.halt()
        RemoteControlGuard.reset()
        RemoteControlGuard.check("connect", _make_settings(), host="prod.example.com")


# --------------- connect checks ---------------

class TestConnectChecks:
    def test_host_allowed_passes(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.check("connect", _make_settings(), host="prod.example.com")

    def test_host_not_allowed_raises(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        with pytest.raises(RemoteControlError, match="not in allowed_hosts"):
            RemoteControlGuard.check("connect", _make_settings(), host="evil.com")

    def test_empty_allowed_hosts_raises(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        with pytest.raises(RemoteControlError, match="No allowed_hosts"):
            RemoteControlGuard.check(
                "connect", _make_settings(allowed_hosts=[]), host="any.com"
            )

    def test_connection_cap_enforced(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        s = _make_settings(max_connections=2)
        RemoteControlGuard.increment_connections()
        RemoteControlGuard.increment_connections()
        with pytest.raises(RemoteControlError, match="Max connections"):
            RemoteControlGuard.check("connect", s, host="prod.example.com")

    def test_connection_cap_allows_under_limit(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        s = _make_settings(max_connections=5)
        for _ in range(4):
            RemoteControlGuard.increment_connections()
        RemoteControlGuard.check("connect", s, host="prod.example.com")


# --------------- command checks ---------------

class TestCommandChecks:
    def test_safe_command_passes(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.check("command", _make_settings(), command="ls -la")

    def test_blocked_binary_raises(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        with pytest.raises(RemoteControlError, match="blocked"):
            RemoteControlGuard.check("command", _make_settings(), command="mkfs /dev/sda1")

    def test_blocked_pattern_raises(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        with pytest.raises(RemoteControlError, match="blocked"):
            RemoteControlGuard.check(
                "command", _make_settings(), command="rm -rf /"
            )

    def test_blocked_pattern_dd_to_device(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        with pytest.raises(RemoteControlError, match="blocked"):
            RemoteControlGuard.check(
                "command", _make_settings(), command="dd if=/dev/zero of=/dev/sda"
            )

    def test_normal_command_passes(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.check("command", _make_settings(), command="python app.py")


# --------------- transfer checks ---------------

class TestTransferChecks:
    def test_file_under_limit_passes(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        RemoteControlGuard.check("transfer", _make_settings(), file_size=100)

    def test_file_over_limit_raises(self):
        from nobla.tools.remote.safety import RemoteControlGuard, RemoteControlError
        s = _make_settings(sftp_max_file_size=1000)
        with pytest.raises(RemoteControlError, match="exceeds"):
            RemoteControlGuard.check("transfer", s, file_size=1001)

    def test_file_at_exact_limit_passes(self):
        from nobla.tools.remote.safety import RemoteControlGuard
        s = _make_settings(sftp_max_file_size=1000)
        RemoteControlGuard.check("transfer", s, file_size=1000)
