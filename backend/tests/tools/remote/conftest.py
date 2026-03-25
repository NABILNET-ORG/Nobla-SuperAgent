"""Shared fixtures and helpers for Phase 4D remote control tests."""

from __future__ import annotations

import pytest

from nobla.config.settings import ComputerControlSettings, RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolParams


def make_remote_settings(**rc_overrides) -> Settings:
    """Create a Settings object with remote control configured for testing."""
    cc = ComputerControlSettings(
        allowed_read_dirs=["/tmp/test-read"],
        allowed_write_dirs=["/tmp/test-read/write"],
    )
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com", "staging.example.com"],
        allowed_users=["deploy", "admin"],
        allowed_remote_dirs=["/home/deploy", "/var/www"],
        **rc_overrides,
    )
    return Settings(computer_control=cc, remote_control=rc)


def make_rc_settings(**overrides) -> RemoteControlSettings:
    """Create a standalone RemoteControlSettings for guard tests."""
    defaults = {
        "allowed_hosts": ["prod.example.com", "staging.example.com"],
        "allowed_users": ["deploy"],
        "max_connections": 3,
    }
    defaults.update(overrides)
    return RemoteControlSettings(**defaults)


def make_state() -> ConnectionState:
    """Create a test ConnectionState with ADMIN tier."""
    return ConnectionState(
        connection_id="conn-remote-test", user_id="u1", tier=Tier.ADMIN.value,
    )


def make_params(**kwargs) -> ToolParams:
    """Create ToolParams with ADMIN-tier connection state."""
    return ToolParams(args=kwargs, connection_state=make_state())


@pytest.fixture(autouse=True)
def _reset_remote_state():
    """Reset all remote module singletons before and after each test."""
    try:
        from nobla.tools.remote.safety import RemoteControlGuard
        import nobla.tools.remote.pool as pool_mod
        RemoteControlGuard.reset()
        pool_mod._pool_instance = None
        pool_mod._pool_override = None
    except (ImportError, AttributeError):
        pass
    yield
    try:
        from nobla.tools.remote.safety import RemoteControlGuard
        import nobla.tools.remote.pool as pool_mod
        RemoteControlGuard.reset()
        pool_mod._pool_instance = None
        pool_mod._pool_override = None
    except (ImportError, AttributeError):
        pass
