# Phase 4D: Remote Control Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure SSH connection management, remote command execution, and SFTP file transfer to Nobla Agent's tool platform.

**Architecture:** Three focused tools (`ssh.connect`, `ssh.exec`, `sftp.manage`) built on `asyncssh`, sharing an `SSHConnectionPool` for persistent sessions and a `RemoteControlGuard` for safety checks. All operations are ADMIN-tier with conditional approval, deny-lists, and kill switch integration.

**Tech Stack:** Python 3.12+, asyncssh>=2.14.0,<3.0.0, pydantic, pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-03-25-phase4d-remote-control-design.md`

**Note on Settings cache pattern:** Phase 4B tools cache the nested settings object (e.g., `ComputerControlSettings`). Phase 4D tools cache the full `Settings` object instead because `sftp_manage.py` needs both `settings.remote_control` (for remote path validation) and `settings.computer_control` (for local path validation). For consistency, all three tools use the same full-Settings cache pattern. This is a deliberate deviation documented here.

---

## File Structure

```
Files to CREATE:
  backend/nobla/tools/remote/__init__.py       — Auto-registration imports + kill switch wiring
  backend/nobla/tools/remote/safety.py          — RemoteControlGuard (halt, blocked commands, connection caps)
  backend/nobla/tools/remote/pool.py            — SSHConnectionPool (lifecycle, cleanup, halt)
  backend/nobla/tools/remote/ssh_connect.py     — ssh.connect tool (connect, disconnect, list)
  backend/nobla/tools/remote/ssh_exec.py        — ssh.exec tool (run with conditional approval)
  backend/nobla/tools/remote/sftp_manage.py     — sftp.manage tool (upload, download, list, delete, stat)
  backend/tests/tools/remote/__init__.py         — Test package init
  backend/tests/tools/remote/conftest.py         — Shared test fixtures and helpers
  backend/tests/tools/remote/test_settings.py    — RemoteControlSettings tests
  backend/tests/tools/remote/test_safety.py      — RemoteControlGuard tests
  backend/tests/tools/remote/test_pool.py        — SSHConnectionPool tests
  backend/tests/tools/remote/test_ssh_connect.py — ssh.connect tests
  backend/tests/tools/remote/test_ssh_exec.py    — ssh.exec tests
  backend/tests/tools/remote/test_sftp_manage.py — sftp.manage tests

Files to MODIFY:
  backend/nobla/config/settings.py              — Add RemoteControlSettings + nest in Settings
  pyproject.toml (or requirements.txt)          — Add asyncssh dependency
```

---

## Task 1: Add RemoteControlSettings to config

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Test: `backend/tests/tools/remote/test_safety.py` (settings validation tests)

### Steps

- [ ] **Step 1: Create test package directory**

```bash
mkdir -p backend/nobla/tools/remote backend/tests/tools/remote
touch backend/nobla/tools/remote/__init__.py backend/tests/tools/remote/__init__.py
```

- [ ] **Step 1b: Create shared test conftest.py**

Create `backend/tests/tools/remote/conftest.py`:

```python
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
    from nobla.tools.remote.safety import RemoteControlGuard
    import nobla.tools.remote.pool as pool_mod

    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
```

- [ ] **Step 2: Write settings validation tests**

Create `backend/tests/tools/remote/test_settings.py`:

```python
"""Tests for RemoteControlSettings."""

import pytest
from pydantic import ValidationError


class TestRemoteControlSettingsDefaults:
    def test_enabled_default_true(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.enabled is True

    def test_allowed_hosts_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_hosts == []

    def test_allowed_users_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_users == []

    def test_allowed_remote_dirs_default_empty(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allowed_remote_dirs == []

    def test_safe_commands_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert "ls" in s.safe_commands
        assert "cat" in s.safe_commands
        assert "whoami" in s.safe_commands

    def test_blocked_binaries_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert "mkfs" in s.blocked_binaries
        assert "shutdown" in s.blocked_binaries

    def test_blocked_patterns_has_defaults(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert len(s.blocked_patterns) > 0

    def test_allow_password_auth_default_false(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.allow_password_auth is False

    def test_known_hosts_policy_default_strict(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.known_hosts_policy == "strict"

    def test_max_connections_default_5(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_connections == 5

    def test_idle_timeout_default_300(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.idle_timeout_s == 300

    def test_max_lifetime_default_3600(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_lifetime_s == 3600

    def test_sftp_max_file_size_default_100mb(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.sftp_max_file_size == 104_857_600

    def test_max_output_bytes_default_1mb(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_output_bytes == 1_048_576

    def test_max_output_lines_default_10000(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings()
        assert s.max_output_lines == 10_000


class TestRemoteControlSettingsValidation:
    def test_invalid_known_hosts_policy_raises(self):
        from nobla.config.settings import RemoteControlSettings
        with pytest.raises(ValidationError, match="known_hosts_policy"):
            RemoteControlSettings(known_hosts_policy="yolo")

    def test_valid_known_hosts_policy_strict(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(known_hosts_policy="strict")
        assert s.known_hosts_policy == "strict"

    def test_valid_known_hosts_policy_ask_first_time(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(known_hosts_policy="ask_first_time")
        assert s.known_hosts_policy == "ask_first_time"

    def test_custom_allowed_hosts(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(allowed_hosts=["prod.example.com"])
        assert s.allowed_hosts == ["prod.example.com"]

    def test_custom_timeouts(self):
        from nobla.config.settings import RemoteControlSettings
        s = RemoteControlSettings(
            ssh_connect_timeout_s=10,
            default_command_timeout_s=30,
            max_command_timeout_s=120,
        )
        assert s.ssh_connect_timeout_s == 10
        assert s.default_command_timeout_s == 30
        assert s.max_command_timeout_s == 120


class TestSettingsNesting:
    def test_settings_has_remote_control(self):
        from nobla.config.settings import Settings
        s = Settings()
        assert hasattr(s, "remote_control")

    def test_settings_remote_control_is_remote_control_settings(self):
        from nobla.config.settings import RemoteControlSettings, Settings
        s = Settings()
        assert isinstance(s.remote_control, RemoteControlSettings)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_settings.py -v
```

Expected: FAIL — `RemoteControlSettings` does not exist yet.

- [ ] **Step 4: Implement RemoteControlSettings**

Add to `backend/nobla/config/settings.py`, after `ComputerControlSettings` class and before the `Settings` class:

```python
class RemoteControlSettings(BaseModel):
    """Configuration for Phase 4D remote control tools (SSH, SFTP)."""

    enabled: bool = True

    # --- Allow-lists (default deny) ---
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    allowed_remote_dirs: list[str] = Field(default_factory=list)

    # --- Command safety ---
    safe_commands: list[str] = Field(
        default_factory=lambda: [
            "ls", "cat", "head", "tail", "grep", "find", "wc",
            "df", "du", "whoami", "hostname", "date", "uptime",
            "ps", "top", "free", "uname", "env", "echo", "pwd",
        ]
    )
    blocked_binaries: list[str] = Field(
        default_factory=lambda: [
            "mkfs", "dd", "shutdown", "reboot", "halt", "poweroff",
        ]
    )
    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm\s+.*-.*r.*-.*f\s+/",
            r"dd\s+.*of=/dev/",
            r">\s*/dev/sd",
            r"init\s+[06]",
            r"systemctl\s+(poweroff|halt)",
        ]
    )

    # --- SSH settings ---
    ssh_key_path: str | None = None
    allow_password_auth: bool = False
    known_hosts_policy: str = "strict"
    known_hosts_path: str | None = None

    # --- Timeouts ---
    ssh_connect_timeout_s: int = 30
    default_command_timeout_s: int = 60
    max_command_timeout_s: int = 600

    # --- Connection pool ---
    max_connections: int = 5
    idle_timeout_s: int = 300
    max_lifetime_s: int = 3600

    # --- SFTP limits ---
    sftp_max_file_size: int = 104_857_600
    sftp_approval_threshold: int = 10_485_760

    # --- Output ---
    max_output_bytes: int = 1_048_576
    max_output_lines: int = 10_000

    # --- Safety ---
    failsafe_enabled: bool = True

    @model_validator(mode="after")
    def validate_known_hosts_policy(self):
        valid = {"strict", "ask_first_time"}
        if self.known_hosts_policy not in valid:
            raise ValueError(
                f"known_hosts_policy must be one of {valid}, "
                f"got '{self.known_hosts_policy}'"
            )
        return self
```

Then add to the `Settings` class (after `computer_control` field):

```python
    remote_control: RemoteControlSettings = Field(default_factory=RemoteControlSettings)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_settings.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/tools/remote/__init__.py backend/tests/tools/remote/
git commit -m "feat(remote): add RemoteControlSettings to config"
```

---

## Task 2: Implement RemoteControlGuard

**Files:**
- Create: `backend/nobla/tools/remote/safety.py`
- Test: `backend/tests/tools/remote/test_safety.py`

### Steps

- [ ] **Step 1: Write RemoteControlGuard tests**

Create `backend/tests/tools/remote/test_safety.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_safety.py -v
```

Expected: FAIL — `RemoteControlGuard` does not exist.

- [ ] **Step 3: Implement RemoteControlGuard**

Create `backend/nobla/tools/remote/safety.py`:

```python
"""Phase 4D: Safety guard for remote control operations.

Mirrors InputSafetyGuard from Phase 4B with SSH-specific checks:
halt/resume, host allow-list, connection caps, blocked commands, file size.
"""

from __future__ import annotations

import re
import shlex

from nobla.config.settings import RemoteControlSettings


class RemoteControlError(Exception):
    """Raised when a remote-control safety check fails."""


class RemoteControlGuard:
    """Singleton safety checks for SSH/SFTP operations.

    All methods are classmethods — no instance needed.
    """

    _halted: bool = False
    _active_connection_count: int = 0

    # ---- public API ----

    @classmethod
    def check(
        cls,
        operation: str,
        settings: RemoteControlSettings,
        **kwargs: object,
    ) -> None:
        """Unified safety check entry point.

        Args:
            operation: "connect", "command", or "transfer"
            settings: RemoteControlSettings instance
            **kwargs:
                connect  → host: str
                command  → command: str
                transfer → file_size: int
        """
        cls._check_halt()

        if operation == "connect":
            cls._check_host_allowed(str(kwargs["host"]), settings)
            cls._check_connection_cap(settings)
        elif operation == "command":
            cls._check_blocked_binary(str(kwargs["command"]), settings)
            cls._check_blocked_pattern(str(kwargs["command"]), settings)
        elif operation == "transfer":
            cls._check_file_size(int(kwargs["file_size"]), settings)

    @classmethod
    def halt(cls) -> None:
        """Emergency stop."""
        cls._halted = True

    @classmethod
    def resume(cls) -> None:
        """Clear halt flag."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Wipe all state (tests)."""
        cls._halted = False
        cls._active_connection_count = 0

    @classmethod
    def increment_connections(cls) -> None:
        cls._active_connection_count += 1

    @classmethod
    def decrement_connections(cls) -> None:
        cls._active_connection_count = max(0, cls._active_connection_count - 1)

    # ---- internal checks ----

    @classmethod
    def _check_halt(cls) -> None:
        if cls._halted:
            raise RemoteControlError(
                "Remote control is halted. Call resume() to re-enable."
            )

    @classmethod
    def _check_host_allowed(cls, host: str, settings: RemoteControlSettings) -> None:
        if not settings.allowed_hosts:
            raise RemoteControlError(
                "No allowed_hosts configured. "
                "Set remote_control.allowed_hosts in your settings."
            )
        if host not in settings.allowed_hosts:
            raise RemoteControlError(
                f"Host '{host}' is not in allowed_hosts: {settings.allowed_hosts}"
            )

    @classmethod
    def _check_connection_cap(cls, settings: RemoteControlSettings) -> None:
        if cls._active_connection_count >= settings.max_connections:
            raise RemoteControlError(
                f"Max connections ({settings.max_connections}) reached. "
                "Disconnect an existing session first."
            )

    @classmethod
    def _check_blocked_binary(
        cls, command: str, settings: RemoteControlSettings
    ) -> None:
        first_token = _parse_first_token(command)
        if first_token in settings.blocked_binaries:
            raise RemoteControlError(
                f"Command blocked: '{first_token}' is in blocked_binaries"
            )

    @classmethod
    def _check_blocked_pattern(
        cls, command: str, settings: RemoteControlSettings
    ) -> None:
        for pattern in settings.blocked_patterns:
            if re.search(pattern, command):
                raise RemoteControlError(
                    f"Command blocked: matches blocked pattern '{pattern}'"
                )

    @classmethod
    def _check_file_size(
        cls, file_size: int, settings: RemoteControlSettings
    ) -> None:
        if file_size > settings.sftp_max_file_size:
            raise RemoteControlError(
                f"File size {file_size} exceeds limit "
                f"({settings.sftp_max_file_size} bytes)"
            )


# ---- module-level helpers ----

_CHAINING_OPERATORS = {";", "&&", "||", "|", "`", "$(", "\n", "<<", "<("}


def _parse_first_token(command: str) -> str:
    """Extract the first command token (basename), ignoring env prefixes."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""
    for token in tokens:
        if "=" not in token:
            return token.split("/")[-1]
    return ""


def _has_chaining_operators(command: str) -> bool:
    """Check if *command* chains multiple operations."""
    return any(op in command for op in _CHAINING_OPERATORS)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_safety.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/remote/safety.py backend/tests/tools/remote/test_safety.py
git commit -m "feat(remote): add RemoteControlGuard with safety checks"
```

---

## Task 3: Implement SSHConnectionPool

**Files:**
- Create: `backend/nobla/tools/remote/pool.py`
- Test: `backend/tests/tools/remote/test_pool.py`

### Steps

- [ ] **Step 1: Write pool tests**

Create `backend/tests/tools/remote/test_pool.py`:

```python
"""Tests for SSHConnectionPool."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import RemoteControlSettings


def _make_settings(**overrides) -> RemoteControlSettings:
    defaults = {
        "allowed_hosts": ["host1.example.com"],
        "allowed_users": ["deploy"],
        "max_connections": 3,
        "idle_timeout_s": 300,
        "max_lifetime_s": 3600,
    }
    defaults.update(overrides)
    return RemoteControlSettings(**defaults)


@pytest.fixture(autouse=True)
def _reset_pool():
    from nobla.tools.remote import pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


def _mock_asyncssh_conn():
    """Create a mock asyncssh.SSHClientConnection."""
    conn = AsyncMock()
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    return conn


class TestPoolSingleton:
    def test_get_pool_returns_same_instance(self):
        from nobla.tools.remote.pool import _get_pool
        p1 = _get_pool()
        p2 = _get_pool()
        assert p1 is p2

    def test_pool_override_takes_precedence(self):
        from nobla.tools.remote import pool as pool_mod
        from nobla.tools.remote.pool import SSHConnectionPool, _get_pool
        override = SSHConnectionPool()
        pool_mod._pool_override = override
        assert _get_pool() is override


class TestPoolLifecycle:
    @pytest.mark.asyncio
    async def test_add_and_get_connection(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        assert cid is not None
        entry = pool.get(cid)
        assert entry.host == "host1.example.com"
        assert entry.user == "deploy"
        assert entry.conn is conn

    @pytest.mark.asyncio
    async def test_get_invalid_id_raises(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        with pytest.raises(KeyError, match="not found"):
            pool.get("nonexistent-id")

    @pytest.mark.asyncio
    async def test_disconnect_removes(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        await pool.disconnect(cid)
        with pytest.raises(KeyError):
            pool.get(cid)

    @pytest.mark.asyncio
    async def test_disconnect_calls_close(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        await pool.disconnect(cid)
        conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_connections_returns_metadata(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn1 = _mock_asyncssh_conn()
        conn2 = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn1)
        pool.add("host1.example.com", "admin", 22, conn2, label="staging")
        conns = pool.list_connections()
        assert len(conns) == 2

    @pytest.mark.asyncio
    async def test_list_connections_includes_label(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn, label="prod")
        conns = pool.list_connections()
        assert conns[0]["label"] == "prod"

    @pytest.mark.asyncio
    async def test_connection_count(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        assert pool.connection_count == 0
        pool.add("host1.example.com", "deploy", 22, conn)
        assert pool.connection_count == 1

    @pytest.mark.asyncio
    async def test_touch_updates_last_activity(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        entry = pool.get(cid)
        old_activity = entry.last_activity
        time.sleep(0.01)
        pool.touch(cid)
        entry = pool.get(cid)
        assert entry.last_activity > old_activity


class TestPoolHalt:
    @pytest.mark.asyncio
    async def test_halt_closes_all(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        c1 = _mock_asyncssh_conn()
        c2 = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, c1)
        pool.add("host1.example.com", "deploy", 22, c2)
        await pool.halt()
        assert pool.connection_count == 0
        c1.close.assert_called_once()
        c2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_clears_all(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn)
        pool.reset()
        assert pool.connection_count == 0


class TestPoolCleanup:
    @pytest.mark.asyncio
    async def test_prune_idle_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        # Manually age the connection
        entry = pool.get(cid)
        entry.last_activity = time.time() - 400  # older than 300s idle
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 1
        assert pool.connection_count == 0

    @pytest.mark.asyncio
    async def test_prune_expired_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        cid = pool.add("host1.example.com", "deploy", 22, conn)
        entry = pool.get(cid)
        entry.created_at = time.time() - 4000  # older than 3600s
        entry.last_activity = time.time()  # still active
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 1

    @pytest.mark.asyncio
    async def test_prune_keeps_active_connections(self):
        from nobla.tools.remote.pool import _get_pool
        pool = _get_pool()
        conn = _mock_asyncssh_conn()
        pool.add("host1.example.com", "deploy", 22, conn)
        pruned = await pool.prune(idle_timeout=300, max_lifetime=3600)
        assert pruned == 0
        assert pool.connection_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_pool.py -v
```

Expected: FAIL — `SSHConnectionPool` does not exist.

- [ ] **Step 3: Implement SSHConnectionPool**

Create `backend/nobla/tools/remote/pool.py`:

```python
"""Phase 4D: SSH Connection Pool.

Manages persistent asyncssh connections with lifecycle controls:
add, get, disconnect, list, halt, prune, reset.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SSHConnection:
    """Metadata for a pooled SSH connection."""

    id: str
    conn: Any  # asyncssh.SSHClientConnection
    host: str
    user: str
    port: int
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    label: str | None = None
    sftp_client: Any | None = None  # asyncssh.SFTPClient


class SSHConnectionPool:
    """Manages persistent SSH sessions with idle/lifetime timeouts."""

    def __init__(self) -> None:
        self._connections: dict[str, SSHConnection] = {}

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def add(
        self,
        host: str,
        user: str,
        port: int,
        conn: Any,
        *,
        label: str | None = None,
    ) -> str:
        """Register a new connection. Returns its UUID."""
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = SSHConnection(
            id=connection_id,
            conn=conn,
            host=host,
            user=user,
            port=port,
            label=label,
        )
        return connection_id

    def get(self, connection_id: str) -> SSHConnection:
        """Look up a connection by ID. Raises KeyError if not found."""
        try:
            return self._connections[connection_id]
        except KeyError:
            raise KeyError(
                f"Connection '{connection_id}' not found. "
                "It may have been disconnected or expired."
            )

    async def disconnect(self, connection_id: str) -> SSHConnection:
        """Close and remove a connection. Returns metadata."""
        entry = self.get(connection_id)
        try:
            entry.conn.close()
            await entry.conn.wait_closed()
        except Exception:
            pass  # Connection may already be dead
        del self._connections[connection_id]
        return entry

    def list_connections(self) -> list[dict]:
        """Return sanitised metadata for all active connections."""
        now = time.time()
        return [
            {
                "connection_id": c.id,
                "host": c.host,
                "user": c.user,
                "port": c.port,
                "label": c.label,
                "connected_at": c.created_at,
                "last_activity": c.last_activity,
                "idle_seconds": round(now - c.last_activity, 1),
            }
            for c in self._connections.values()
        ]

    def touch(self, connection_id: str) -> None:
        """Update last_activity timestamp for a connection."""
        entry = self.get(connection_id)
        entry.last_activity = time.time()

    async def halt(self) -> None:
        """Emergency: close ALL connections immediately."""
        for entry in list(self._connections.values()):
            try:
                entry.conn.close()
                await entry.conn.wait_closed()
            except Exception:
                pass
        self._connections.clear()

    async def prune(self, idle_timeout: int, max_lifetime: int) -> int:
        """Remove idle or expired connections. Returns count pruned."""
        now = time.time()
        to_remove: list[str] = []
        for cid, entry in self._connections.items():
            idle = now - entry.last_activity
            age = now - entry.created_at
            if idle > idle_timeout or age > max_lifetime:
                to_remove.append(cid)
        for cid in to_remove:
            await self.disconnect(cid)
        return len(to_remove)

    def reset(self) -> None:
        """Wipe all state without closing connections (tests)."""
        self._connections.clear()


# ---- module-level singleton ----

_pool_instance: SSHConnectionPool | None = None
_pool_override: SSHConnectionPool | None = None


def _get_pool() -> SSHConnectionPool:
    """Return (and cache) the pool singleton."""
    global _pool_instance
    if _pool_override is not None:
        return _pool_override
    if _pool_instance is None:
        _pool_instance = SSHConnectionPool()
    return _pool_instance
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_pool.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/remote/pool.py backend/tests/tools/remote/test_pool.py
git commit -m "feat(remote): add SSHConnectionPool with lifecycle management"
```

---

## Task 4: Implement ssh.connect tool

**Files:**
- Create: `backend/nobla/tools/remote/ssh_connect.py`
- Test: `backend/tests/tools/remote/test_ssh_connect.py`

### Steps

- [ ] **Step 1: Write ssh.connect tests**

Create `backend/tests/tools/remote/test_ssh_connect.py`:

```python
"""Tests for ssh.connect tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com", "staging.example.com"],
        allowed_users=["deploy", "admin"],
        allowed_remote_dirs=["/home/deploy"],
        **rc_overrides,
    )
    return Settings(remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-ssh-test", user_id="u1", tier=Tier.ADMIN.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset():
    RemoteControlGuard.reset()
    import nobla.tools.remote.pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


class TestSSHConnectMetadata:
    def test_name(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.name == "ssh.connect"

    def test_category(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.tier == Tier.ADMIN

    def test_requires_approval_false(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        assert SSHConnectTool.requires_approval is False


class TestSSHConnectApproval:
    def test_connect_needs_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="connect", host="prod.example.com", user="deploy")
        assert tool.needs_approval(params) is True

    def test_disconnect_no_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="disconnect", connection_id="abc")
        assert tool.needs_approval(params) is False

    def test_list_no_approval(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(action="list")
        assert tool.needs_approval(params) is False


class TestSSHConnectValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(action="connect", host="prod.example.com", user="deploy")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="hack")
        with pytest.raises(ValueError, match="Invalid action"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_missing_host_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", user="deploy")
        with pytest.raises(ValueError, match="host"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_missing_user_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="prod.example.com")
        with pytest.raises(ValueError, match="user"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_host_not_allowed_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="evil.com", user="deploy")
        with pytest.raises(ValueError, match="not in allowed_hosts"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_user_not_allowed_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="connect", host="prod.example.com", user="root")
        with pytest.raises(ValueError, match="not in allowed_users"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_invalid_port_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy", port=99999
        )
        with pytest.raises(ValueError, match="port"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_connect_password_without_opt_in_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings(allow_password_auth=False)
        params = _make_params(
            action="connect", host="prod.example.com",
            user="deploy", password="secret",
        )
        with pytest.raises(ValueError, match="password"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_disconnect_missing_connection_id_raises(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="disconnect")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)


class TestSSHConnectExecute:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()

        mock_conn = AsyncMock()
        mock_conn.get_extra_info = MagicMock(return_value=b"sha256:abc123")

        with patch(
            "nobla.tools.remote.ssh_connect._async_connect",
            return_value=mock_conn,
        ):
            params = _make_params(
                action="connect", host="prod.example.com", user="deploy",
            )
            result = await tool.execute(params)

        assert result.success is True
        assert "connection_id" in result.data

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_connect import SSHConnectTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()
        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="disconnect", connection_id=cid)
        result = await tool.execute(params)
        assert result.success is True
        assert result.data["disconnected"] is True

    @pytest.mark.asyncio
    async def test_list_returns_connections(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_connect import SSHConnectTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        pool.add("prod.example.com", "deploy", 22, mock_conn, label="prod")

        tool = SSHConnectTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list")
        result = await tool.execute(params)
        assert result.success is True
        assert len(result.data["connections"]) == 1


class TestSSHConnectGracefulDegradation:
    @pytest.mark.asyncio
    async def test_connect_without_asyncssh_returns_error(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        tool._settings_override = _make_settings()

        with patch(
            "nobla.tools.remote.ssh_connect._async_connect",
            side_effect=RuntimeError("asyncssh is not installed"),
        ):
            params = _make_params(
                action="connect", host="prod.example.com", user="deploy",
            )
            result = await tool.execute(params)

        assert result.success is False
        assert "asyncssh" in result.error


class TestSSHConnectDescribeAction:
    def test_connect_description(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy", port=22,
        )
        desc = tool.describe_action(params)
        assert "deploy@prod.example.com:22" in desc

    def test_connect_password_warning(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com", user="deploy",
            password="secret",
        )
        desc = tool.describe_action(params)
        assert "password" in desc.lower()


class TestSSHConnectParamsSummary:
    def test_password_not_in_summary(self):
        from nobla.tools.remote.ssh_connect import SSHConnectTool
        tool = SSHConnectTool()
        params = _make_params(
            action="connect", host="prod.example.com",
            user="deploy", password="secret123", passphrase="key-pass",
        )
        summary = tool.get_params_summary(params)
        assert "secret123" not in str(summary)
        assert "key-pass" not in str(summary)
        assert summary["auth_method"] == "password"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_ssh_connect.py -v
```

Expected: FAIL — `SSHConnectTool` does not exist.

- [ ] **Step 3: Implement ssh.connect tool**

Create `backend/nobla/tools/remote/ssh_connect.py`:

```python
"""Phase 4D: ssh.connect — SSH connection lifecycle management.

Actions: connect, disconnect, list.
"""

from __future__ import annotations

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import RemoteControlError, RemoteControlGuard

_VALID_ACTIONS = {"connect", "disconnect", "list"}
_APPROVAL_ACTIONS = {"connect"}

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- lazy asyncssh import ----


def _async_connect(*args, **kwargs):
    """Wrapper for asyncssh.connect — enables mocking in tests."""
    try:
        import asyncssh
    except ImportError:
        raise RuntimeError(
            "asyncssh is not installed. Run: pip install asyncssh"
        )
    return asyncssh.connect(*args, **kwargs)


# ---- tool ----


@register_tool
class SSHConnectTool(BaseTool):
    """Manage SSH connections: connect, disconnect, list."""

    name = "ssh.connect"
    description = "SSH connection management: connect, disconnect, list active sessions"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        return params.args.get("action") in _APPROVAL_ACTIONS

    async def validate(self, params: ToolParams) -> None:
        settings = self._settings()
        rc = settings.remote_control

        if not rc.enabled:
            raise ValueError("Remote control tools are disabled in settings")

        action = params.args.get("action", "")
        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
            )

        if action == "connect":
            host = params.args.get("host")
            user = params.args.get("user")
            port = params.args.get("port", 22)

            if not host:
                raise ValueError("host is required for connect")
            if not user:
                raise ValueError("user is required for connect")
            if not isinstance(port, int) or port < 1 or port > 65535:
                raise ValueError(f"port must be 1-65535, got {port}")
            if host not in rc.allowed_hosts:
                raise ValueError(
                    f"'{host}' is not in allowed_hosts: {rc.allowed_hosts}"
                )
            if user not in rc.allowed_users:
                raise ValueError(
                    f"'{user}' is not in allowed_users: {rc.allowed_users}"
                )
            if params.args.get("password") and not rc.allow_password_auth:
                raise ValueError(
                    "password auth is disabled. Set "
                    "remote_control.allow_password_auth=true or use SSH keys."
                )

            RemoteControlGuard.check("connect", rc, host=host)

        elif action == "disconnect":
            if not params.args.get("connection_id"):
                raise ValueError("connection_id is required for disconnect")

    def describe_action(self, params: ToolParams) -> str:
        action = params.args.get("action", "")
        if action == "connect":
            host = params.args.get("host", "?")
            user = params.args.get("user", "?")
            port = params.args.get("port", 22)
            auth = "password" if params.args.get("password") else "key"
            desc = f"Connect to {user}@{host}:{port} via SSH ({auth}-based auth)"
            if auth == "password":
                desc += " — less secure, consider SSH keys"
            return desc
        if action == "disconnect":
            return f"Disconnect SSH session {params.args.get('connection_id', '?')}"
        return "List active SSH connections"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        return {
            "action": args.get("action"),
            "host": args.get("host"),
            "user": args.get("user"),
            "port": args.get("port", 22),
            "label": args.get("label"),
            "auth_method": "password" if args.get("password") else "key",
            "connection_id": args.get("connection_id"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        action = params.args["action"]
        try:
            if action == "connect":
                return await self._do_connect(params)
            elif action == "disconnect":
                return await self._do_disconnect(params)
            else:
                return self._do_list()
        except RemoteControlError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SSH error: {exc}")

    async def _do_connect(self, params: ToolParams) -> ToolResult:
        args = params.args
        host = args["host"]
        user = args["user"]
        port = args.get("port", 22)
        label = args.get("label")

        rc = self._settings().remote_control

        connect_kwargs: dict = {
            "host": host,
            "port": port,
            "username": user,
            "connect_timeout": rc.ssh_connect_timeout_s,
        }

        if args.get("password"):
            connect_kwargs["password"] = args["password"]
        elif args.get("key_path"):
            connect_kwargs["client_keys"] = [args["key_path"]]
            if args.get("passphrase"):
                connect_kwargs["passphrase"] = args["passphrase"]
        elif rc.ssh_key_path:
            connect_kwargs["client_keys"] = [rc.ssh_key_path]

        if rc.known_hosts_path:
            connect_kwargs["known_hosts"] = rc.known_hosts_path

        conn = await _async_connect(**connect_kwargs)

        pool = _get_pool()
        connection_id = pool.add(host, user, port, conn, label=label)
        RemoteControlGuard.increment_connections()

        fingerprint = ""
        try:
            raw = conn.get_extra_info("server_host_key")
            if raw:
                fingerprint = raw.hex() if isinstance(raw, bytes) else str(raw)
        except Exception:
            pass

        return ToolResult(
            success=True,
            data={
                "connection_id": connection_id,
                "host": host,
                "user": user,
                "port": port,
                "label": label,
                "host_key_fingerprint": fingerprint,
            },
        )

    async def _do_disconnect(self, params: ToolParams) -> ToolResult:
        connection_id = params.args["connection_id"]
        pool = _get_pool()
        try:
            entry = await pool.disconnect(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        RemoteControlGuard.decrement_connections()
        return ToolResult(
            success=True,
            data={"disconnected": True, "host": entry.host},
        )

    def _do_list(self) -> ToolResult:
        pool = _get_pool()
        return ToolResult(
            success=True,
            data={"connections": pool.list_connections()},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_ssh_connect.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/remote/ssh_connect.py backend/tests/tools/remote/test_ssh_connect.py
git commit -m "feat(remote): add ssh.connect tool with connection lifecycle"
```

---

## Task 5: Implement ssh.exec tool

**Files:**
- Create: `backend/nobla/tools/remote/ssh_exec.py`
- Test: `backend/tests/tools/remote/test_ssh_exec.py`

### Steps

- [ ] **Step 1: Write ssh.exec tests**

Create `backend/tests/tools/remote/test_ssh_exec.py`:

```python
"""Tests for ssh.exec tool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from nobla.config.settings import RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com"],
        allowed_users=["deploy"],
        allowed_remote_dirs=["/home/deploy"],
        **rc_overrides,
    )
    return Settings(remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-exec-test", user_id="u1", tier=Tier.ADMIN.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset():
    RemoteControlGuard.reset()
    import nobla.tools.remote.pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


class TestSSHExecMetadata:
    def test_name(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.name == "ssh.exec"

    def test_category(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        assert SSHExecTool.tier == Tier.ADMIN


class TestSSHExecApproval:
    def test_safe_command_no_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="ls -la")
        assert tool.needs_approval(params) is False

    def test_unknown_command_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="deploy.sh")
        assert tool.needs_approval(params) is True

    def test_chained_command_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="ls; rm -rf /")
        assert tool.needs_approval(params) is True

    def test_pipe_needs_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="cat file | grep secret")
        assert tool.needs_approval(params) is True

    def test_safe_command_with_args_no_approval(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="whoami")
        assert tool.needs_approval(params) is False

    def test_env_prefix_safe_command(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="FOO=bar ls")
        assert tool.needs_approval(params) is False


class TestSSHExecValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(connection_id="abc", command="ls")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_connection_id_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(command="ls")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_command_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc")
        with pytest.raises(ValueError, match="command"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_timeout_exceeds_max_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings(max_command_timeout_s=60)
        params = _make_params(connection_id="abc", command="ls", timeout=120)
        with pytest.raises(ValueError, match="timeout"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_blocked_binary_raises(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="abc", command="mkfs /dev/sda1")
        with pytest.raises(ValueError, match="blocked"):
            await tool.validate(params)


class TestSSHExecExecute:
    @pytest.mark.asyncio
    async def test_run_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()

        # Mock the SSH process result
        mock_result = MagicMock()
        mock_result.stdout = "file1.txt\nfile2.txt\n"
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id=cid, command="ls")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["exit_code"] == 0
        assert "file1.txt" in result.data["stdout"]
        assert result.data["truncated"] is False

    @pytest.mark.asyncio
    async def test_run_with_nonzero_exit(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "No such file"
        mock_result.exit_status = 1
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id=cid, command="cat missing.txt")
        result = await tool.execute(params)

        assert result.success is True  # Command ran, just failed
        assert result.data["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_run_connection_not_found(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        tool._settings_override = _make_settings()
        params = _make_params(connection_id="nonexistent", command="ls")
        result = await tool.execute(params)
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.ssh_exec import SSHExecTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.stdout = "x" * 2_000_000  # 2MB, over 1MB limit
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SSHExecTool()
        tool._settings_override = _make_settings(max_output_bytes=1000)
        params = _make_params(connection_id=cid, command="cat bigfile")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["truncated"] is True
        assert len(result.data["stdout"]) <= 1000


class TestSSHExecParamsSummary:
    def test_command_truncated_in_summary(self):
        from nobla.tools.remote.ssh_exec import SSHExecTool
        tool = SSHExecTool()
        long_cmd = "x" * 300
        params = _make_params(connection_id="abc", command=long_cmd)
        summary = tool.get_params_summary(params)
        assert len(summary["command"]) <= 203  # 200 + "..."
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_ssh_exec.py -v
```

Expected: FAIL — `SSHExecTool` does not exist.

- [ ] **Step 3: Implement ssh.exec tool**

Create `backend/nobla/tools/remote/ssh_exec.py`:

```python
"""Phase 4D: ssh.exec — Remote command execution.

Single action: run. Conditional approval based on safe_commands list
and chaining operator detection.
"""

from __future__ import annotations

import asyncio
import time

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import (
    RemoteControlError,
    RemoteControlGuard,
    _parse_first_token,
    _has_chaining_operators,
)

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- output helpers ----


def _truncate_output(
    text: str, max_bytes: int, max_lines: int
) -> tuple[str, bool]:
    """Truncate text by byte or line count. Returns (text, was_truncated)."""
    truncated = False
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        text = "\n".join(lines)
        truncated = True
    if len(text.encode("utf-8", errors="replace")) > max_bytes:
        text = text[:max_bytes]
        truncated = True
    return text, truncated


# ---- tool ----


@register_tool
class SSHExecTool(BaseTool):
    """Execute commands on remote hosts via SSH."""

    name = "ssh.exec"
    description = "Execute a command on a remote host via an active SSH connection"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        command = params.args.get("command", "")
        rc = self._settings().remote_control

        if _has_chaining_operators(command):
            return True

        first_token = _parse_first_token(command)
        if first_token in rc.safe_commands:
            return False

        return True

    async def validate(self, params: ToolParams) -> None:
        rc = self._settings().remote_control

        if not rc.enabled:
            raise ValueError("Remote control tools are disabled in settings")

        if not params.args.get("connection_id"):
            raise ValueError("connection_id is required")
        if not params.args.get("command"):
            raise ValueError("command is required")

        timeout = params.args.get("timeout")
        if timeout is not None and timeout > rc.max_command_timeout_s:
            raise ValueError(
                f"timeout ({timeout}s) exceeds max ({rc.max_command_timeout_s}s)"
            )

        command = params.args["command"]
        try:
            RemoteControlGuard.check("command", rc, command=command)
        except RemoteControlError as exc:
            raise ValueError(f"Command blocked: {exc}") from exc

    def describe_action(self, params: ToolParams) -> str:
        command = params.args.get("command", "?")
        cid = params.args.get("connection_id", "?")
        pool = _get_pool()
        try:
            entry = pool.get(cid)
            host = entry.host
        except KeyError:
            host = "unknown"
        short_cmd = command[:80] + ("..." if len(command) > 80 else "")
        return f"Execute on {host}: {short_cmd}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        cmd = args.get("command", "")
        return {
            "action": "run",
            "connection_id": args.get("connection_id"),
            "command": cmd[:200] + ("..." if len(cmd) > 200 else ""),
            "timeout": args.get("timeout"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        rc = self._settings().remote_control
        connection_id = params.args["connection_id"]
        command = params.args["command"]
        timeout = params.args.get("timeout", rc.default_command_timeout_s)
        timeout = min(timeout, rc.max_command_timeout_s)

        pool = _get_pool()
        try:
            entry = pool.get(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        start = time.time()
        try:
            result = await asyncio.wait_for(
                entry.conn.run(command, check=False),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.time() - start) * 1000)
            return ToolResult(
                success=False,
                data={"duration_ms": elapsed, "truncated": False},
                error=f"Command timed out after {timeout}s",
            )
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SSH exec error: {exc}")

        pool.touch(connection_id)
        elapsed = int((time.time() - start) * 1000)

        stdout, stdout_trunc = _truncate_output(
            result.stdout or "", rc.max_output_bytes, rc.max_output_lines,
        )
        stderr, stderr_trunc = _truncate_output(
            result.stderr or "", rc.max_output_bytes, rc.max_output_lines,
        )

        return ToolResult(
            success=True,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.exit_status,
                "duration_ms": elapsed,
                "truncated": stdout_trunc or stderr_trunc,
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_ssh_exec.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/remote/ssh_exec.py backend/tests/tools/remote/test_ssh_exec.py
git commit -m "feat(remote): add ssh.exec tool with conditional approval"
```

---

## Task 6: Implement sftp.manage tool

**Files:**
- Create: `backend/nobla/tools/remote/sftp_manage.py`
- Test: `backend/tests/tools/remote/test_sftp_manage.py`

### Steps

- [ ] **Step 1: Write sftp.manage tests**

Create `backend/tests/tools/remote/test_sftp_manage.py`:

```python
"""Tests for sftp.manage tool."""

from __future__ import annotations

import os
import posixpath
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.config.settings import ComputerControlSettings, RemoteControlSettings, Settings
from nobla.gateway.websocket import ConnectionState
from nobla.security.permissions import Tier
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.remote.safety import RemoteControlGuard


def _make_settings(**rc_overrides) -> Settings:
    cc = ComputerControlSettings(
        allowed_read_dirs=["/tmp/test-read"],
        allowed_write_dirs=["/tmp/test-read/write"],
    )
    rc = RemoteControlSettings(
        allowed_hosts=["prod.example.com"],
        allowed_users=["deploy"],
        allowed_remote_dirs=["/home/deploy", "/var/www"],
        **rc_overrides,
    )
    return Settings(computer_control=cc, remote_control=rc)


def _make_state() -> ConnectionState:
    return ConnectionState(
        connection_id="conn-sftp-test", user_id="u1", tier=Tier.ADMIN.value,
    )


def _make_params(**kwargs) -> ToolParams:
    return ToolParams(args=kwargs, connection_state=_make_state())


@pytest.fixture(autouse=True)
def _reset():
    RemoteControlGuard.reset()
    import nobla.tools.remote.pool as pool_mod
    pool_mod._pool_instance = None
    pool_mod._pool_override = None
    yield
    RemoteControlGuard.reset()
    pool_mod._pool_instance = None
    pool_mod._pool_override = None


class TestSFTPManageMetadata:
    def test_name(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.name == "sftp.manage"

    def test_category(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.category == ToolCategory.SSH

    def test_tier_admin(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        assert SFTPManageTool.tier == Tier.ADMIN


class TestSFTPManageApproval:
    def test_upload_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="upload", connection_id="x",
                              local_path="/tmp/f", remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is True

    def test_delete_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="delete", connection_id="x",
                              remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is True

    def test_list_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy")
        assert tool.needs_approval(params) is False

    def test_stat_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="stat", connection_id="x",
                              remote_path="/home/deploy/f")
        assert tool.needs_approval(params) is False

    def test_small_download_no_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(sftp_approval_threshold=1000)
        params = _make_params(action="download", connection_id="x",
                              remote_path="/home/deploy/small.txt",
                              local_path="/tmp/test-read/write/small.txt",
                              file_size=500)
        assert tool.needs_approval(params) is False

    def test_large_download_needs_approval(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(sftp_approval_threshold=1000)
        params = _make_params(action="download", connection_id="x",
                              remote_path="/home/deploy/big.tar",
                              local_path="/tmp/test-read/write/big.tar",
                              file_size=1500)
        assert tool.needs_approval(params) is True


class TestSFTPManageValidation:
    @pytest.mark.asyncio
    async def test_disabled_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings(enabled=False)
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy")
        with pytest.raises(ValueError, match="disabled"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="hack", connection_id="x")
        with pytest.raises(ValueError, match="Invalid action"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_relative_remote_path_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="../../etc/passwd")
        with pytest.raises(ValueError, match="absolute"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_remote_path_outside_allowed_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/etc/shadow")
        with pytest.raises(ValueError, match="not within"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_path_traversal_normalised(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id="x",
                              remote_path="/home/deploy/../../../etc/passwd")
        with pytest.raises(ValueError, match="not within"):
            await tool.validate(params)

    @pytest.mark.asyncio
    async def test_missing_connection_id_raises(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", remote_path="/home/deploy")
        with pytest.raises(ValueError, match="connection_id"):
            await tool.validate(params)


class TestSFTPManageExecute:
    @pytest.mark.asyncio
    async def test_list_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()

        mock_entry = MagicMock()
        mock_entry.filename = "test.txt"
        mock_entry.attrs.size = 1024
        mock_entry.attrs.mtime = 1700000000
        mock_entry.attrs.permissions = 0o644
        mock_sftp.readdir = AsyncMock(return_value=[mock_entry])
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="list", connection_id=cid,
                              remote_path="/home/deploy")
        result = await tool.execute(params)

        assert result.success is True
        assert len(result.data["entries"]) == 1

    @pytest.mark.asyncio
    async def test_stat_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()

        mock_attrs = MagicMock()
        mock_attrs.size = 2048
        mock_attrs.mtime = 1700000000
        mock_attrs.permissions = 0o644
        mock_attrs.uid = 1000
        mock_attrs.gid = 1000
        mock_sftp.stat = AsyncMock(return_value=mock_attrs)
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="stat", connection_id=cid,
                              remote_path="/home/deploy/file.txt")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["size"] == 2048

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.sftp_manage import SFTPManageTool

        pool = _get_pool()
        mock_conn = AsyncMock()
        mock_sftp = AsyncMock()
        mock_sftp.remove = AsyncMock()
        mock_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        cid = pool.add("prod.example.com", "deploy", 22, mock_conn)

        tool = SFTPManageTool()
        tool._settings_override = _make_settings()
        params = _make_params(action="delete", connection_id=cid,
                              remote_path="/home/deploy/old.log")
        result = await tool.execute(params)

        assert result.success is True
        assert result.data["deleted"] is True
        mock_sftp.remove.assert_called_once()


class TestSFTPManageParamsSummary:
    def test_summary_has_paths(self):
        from nobla.tools.remote.sftp_manage import SFTPManageTool
        tool = SFTPManageTool()
        params = _make_params(action="upload", connection_id="x",
                              local_path="/tmp/f.txt",
                              remote_path="/home/deploy/f.txt")
        summary = tool.get_params_summary(params)
        assert summary["local_path"] == "/tmp/f.txt"
        assert summary["remote_path"] == "/home/deploy/f.txt"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/tools/remote/test_sftp_manage.py -v
```

Expected: FAIL — `SFTPManageTool` does not exist.

- [ ] **Step 3: Implement sftp.manage tool**

Create `backend/nobla/tools/remote/sftp_manage.py`:

```python
"""Phase 4D: sftp.manage — Remote file transfer via SFTP.

Actions: upload, download, list, delete, stat.
"""

from __future__ import annotations

import os
import posixpath
import stat as stat_module
import time
from pathlib import Path

from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool
from nobla.tools.remote.pool import _get_pool
from nobla.tools.remote.safety import RemoteControlError, RemoteControlGuard

_VALID_ACTIONS = {"upload", "download", "list", "delete", "stat"}
_APPROVAL_ACTIONS = {"upload", "delete"}

# ---- settings cache ----

_settings_cache: Settings | None = None


def _get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings()
    return _settings_cache


# ---- remote path validation ----


def _validate_remote_path(
    path_str: str, allowed_dirs: list[str]
) -> str:
    """Validate remote path: must be absolute, normalised, within allowed dirs."""
    if not path_str.startswith("/"):
        raise ValueError(
            f"Remote path must be absolute (start with /), got: '{path_str}'"
        )

    normalised = posixpath.normpath(path_str)

    if not allowed_dirs:
        raise ValueError(
            "No allowed_remote_dirs configured. "
            "Set remote_control.allowed_remote_dirs in your settings."
        )

    for allowed in allowed_dirs:
        allowed_norm = posixpath.normpath(allowed)
        if normalised == allowed_norm or normalised.startswith(allowed_norm + "/"):
            return normalised

    raise ValueError(
        f"Remote path '{normalised}' is not within any allowed remote dirs: "
        f"{allowed_dirs}"
    )


def _validate_local_path(
    path_str: str, allowed_dirs: list[str], label: str
) -> Path:
    """Validate local path against ComputerControlSettings allow-lists."""
    if not allowed_dirs:
        raise ValueError(
            f"No {label} configured. "
            f"Set computer_control.{label} in your settings."
        )
    resolved = Path(path_str).resolve()
    for allowed in allowed_dirs:
        try:
            resolved.relative_to(Path(allowed).resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"Local path '{resolved}' is not within any allowed {label}: "
        f"{[str(Path(d).resolve()) for d in allowed_dirs]}"
    )


# ---- tool ----


@register_tool
class SFTPManageTool(BaseTool):
    """Remote file operations via SFTP: upload, download, list, delete, stat."""

    name = "sftp.manage"
    description = "SFTP file operations: upload, download, list, delete, stat"
    category = ToolCategory.SSH
    tier = Tier.ADMIN
    requires_approval = False

    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()

    def needs_approval(self, params: ToolParams) -> bool:
        action = params.args.get("action", "")
        if action in _APPROVAL_ACTIONS:
            return True
        if action == "download":
            file_size = params.args.get("file_size", 0)
            threshold = self._settings().remote_control.sftp_approval_threshold
            return file_size > threshold
        return False

    async def validate(self, params: ToolParams) -> None:
        settings = self._settings()
        rc = settings.remote_control

        if not rc.enabled:
            raise ValueError("Remote control tools are disabled in settings")

        action = params.args.get("action", "")
        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
            )

        if not params.args.get("connection_id"):
            raise ValueError("connection_id is required")

        remote_path = params.args.get("remote_path", "")
        if remote_path:
            _validate_remote_path(remote_path, rc.allowed_remote_dirs)

        if action == "upload":
            local_path = params.args.get("local_path", "")
            if not local_path:
                raise ValueError("local_path is required for upload")
            _validate_local_path(
                local_path, settings.computer_control.allowed_read_dirs,
                "allowed_read_dirs",
            )
            local = Path(local_path)
            if local.exists():
                size = local.stat().st_size
                try:
                    RemoteControlGuard.check("transfer", rc, file_size=size)
                except RemoteControlError as exc:
                    raise ValueError(str(exc)) from exc

        elif action == "download":
            local_path = params.args.get("local_path", "")
            if not local_path:
                raise ValueError("local_path is required for download")
            _validate_local_path(
                local_path, settings.computer_control.allowed_write_dirs,
                "allowed_write_dirs",
            )

    def describe_action(self, params: ToolParams) -> str:
        action = params.args.get("action", "")
        cid = params.args.get("connection_id", "?")
        pool = _get_pool()
        try:
            entry = pool.get(cid)
            host = entry.host
        except KeyError:
            host = "unknown"

        remote = params.args.get("remote_path", "?")
        if action == "upload":
            local = params.args.get("local_path", "?")
            return f"Upload {os.path.basename(local)} to {host}:{remote}"
        if action == "download":
            return f"Download {host}:{remote}"
        if action == "delete":
            return f"Delete {host}:{remote}"
        if action == "list":
            return f"List {host}:{remote}"
        return f"Stat {host}:{remote}"

    def get_params_summary(self, params: ToolParams) -> dict:
        args = params.args
        return {
            "action": args.get("action"),
            "connection_id": args.get("connection_id"),
            "local_path": args.get("local_path"),
            "remote_path": args.get("remote_path"),
        }

    async def execute(self, params: ToolParams) -> ToolResult:
        action = params.args["action"]
        connection_id = params.args["connection_id"]

        pool = _get_pool()
        try:
            entry = pool.get(connection_id)
        except KeyError as exc:
            return ToolResult(success=False, data={}, error=str(exc))

        try:
            sftp = await entry.conn.start_sftp_client()

            if action == "upload":
                return await self._do_upload(sftp, params, pool, connection_id)
            elif action == "download":
                return await self._do_download(sftp, params, pool, connection_id)
            elif action == "list":
                return await self._do_list(sftp, params, pool, connection_id)
            elif action == "delete":
                return await self._do_delete(sftp, params, pool, connection_id)
            else:
                return await self._do_stat(sftp, params, pool, connection_id)
        except RemoteControlError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, data={}, error=f"SFTP error: {exc}")

    async def _do_upload(self, sftp, params, pool, cid) -> ToolResult:
        local_path = params.args["local_path"]
        remote_path = params.args["remote_path"]
        start = time.time()
        await sftp.put(local_path, remote_path)
        pool.touch(cid)
        elapsed = int((time.time() - start) * 1000)
        size = Path(local_path).stat().st_size
        return ToolResult(
            success=True,
            data={
                "uploaded": True,
                "local_path": local_path,
                "remote_path": remote_path,
                "size": size,
                "duration_ms": elapsed,
            },
        )

    async def _do_download(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        local_path = params.args["local_path"]
        start = time.time()
        await sftp.get(remote_path, local_path)
        pool.touch(cid)
        elapsed = int((time.time() - start) * 1000)
        size = Path(local_path).stat().st_size
        return ToolResult(
            success=True,
            data={
                "downloaded": True,
                "remote_path": remote_path,
                "local_path": local_path,
                "size": size,
                "duration_ms": elapsed,
            },
        )

    async def _do_list(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        entries_raw = await sftp.readdir(remote_path)
        pool.touch(cid)
        entries = []
        for e in entries_raw:
            attrs = e.attrs
            entries.append({
                "name": e.filename,
                "size": getattr(attrs, "size", 0),
                "modified": getattr(attrs, "mtime", 0),
                "permissions": oct(getattr(attrs, "permissions", 0)),
                "is_dir": stat_module.S_ISDIR(getattr(attrs, "permissions", 0)),
            })
        return ToolResult(
            success=True,
            data={"entries": entries, "path": remote_path},
        )

    async def _do_delete(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        await sftp.remove(remote_path)
        pool.touch(cid)
        return ToolResult(
            success=True,
            data={"deleted": True, "path": remote_path},
        )

    async def _do_stat(self, sftp, params, pool, cid) -> ToolResult:
        remote_path = params.args["remote_path"]
        attrs = await sftp.stat(remote_path)
        pool.touch(cid)
        return ToolResult(
            success=True,
            data={
                "path": remote_path,
                "size": getattr(attrs, "size", 0),
                "modified": getattr(attrs, "mtime", 0),
                "permissions": oct(getattr(attrs, "permissions", 0)),
                "is_dir": stat_module.S_ISDIR(getattr(attrs, "permissions", 0)),
                "uid": getattr(attrs, "uid", None),
                "gid": getattr(attrs, "gid", None),
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/tools/remote/test_sftp_manage.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/tools/remote/sftp_manage.py backend/tests/tools/remote/test_sftp_manage.py
git commit -m "feat(remote): add sftp.manage tool with path validation"
```

---

## Task 7: Wire up __init__.py and kill switch

**Files:**
- Modify: `backend/nobla/tools/remote/__init__.py`
- Modify: `pyproject.toml` or `requirements.txt` (add asyncssh)

### Steps

- [ ] **Step 1: Update remote __init__.py with auto-registration and kill switch**

Update `backend/nobla/tools/remote/__init__.py`:

```python
"""Phase 4D: Remote Control tools.

Auto-discovery imports trigger @register_tool decorators.
Kill switch callbacks close SSH sessions on emergency stop.
"""

from nobla.tools.remote import ssh_connect  # noqa: F401
from nobla.tools.remote import ssh_exec  # noqa: F401
from nobla.tools.remote import sftp_manage  # noqa: F401

# ---- kill switch integration ----

def _register_kill_switch() -> None:
    """Register remote control callbacks with the kill switch."""
    try:
        from nobla.security.killswitch import kill_switch
        from nobla.tools.remote.pool import _get_pool
        from nobla.tools.remote.safety import RemoteControlGuard

        kill_switch.on_soft_kill(RemoteControlGuard.halt)

        async def _halt_pool():
            await _get_pool().halt()

        kill_switch.on_hard_kill(_halt_pool)
    except Exception:
        pass  # Kill switch may not be initialised yet

_register_kill_switch()
```

- [ ] **Step 2: Add asyncssh to dependencies**

Add to `pyproject.toml` (under `[project.dependencies]` or `install_requires`):

```
asyncssh>=2.14.0,<3.0.0
```

Or if using `requirements.txt`, add the line `asyncssh>=2.14.0,<3.0.0`.

- [ ] **Step 3: Run all Phase 4D tests together**

```bash
pytest backend/tests/tools/remote/ -v --tb=short
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/nobla/tools/remote/__init__.py pyproject.toml
git commit -m "feat(remote): wire tool registration and kill switch integration"
```

---

## Task 8: Run full test suite and update docs

**Files:**
- Modify: `CLAUDE.md` (update phase status)
- Modify: `Plan.md` (mark Phase 4D complete)

### Steps

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All existing tests still pass, Phase 4D tests pass.

- [ ] **Step 2: Count Phase 4D tests**

```bash
pytest backend/tests/tools/remote/ -v --tb=short 2>&1 | grep -c "PASSED"
```

Expected: ~150 tests passing.

- [ ] **Step 3: Update CLAUDE.md Phase 4D status**

In `CLAUDE.md`, update the Phase 4 sub-phases table to mark 4D as complete:

```markdown
| 4D: Remote Control | ✅ Complete | ssh.connect, ssh.exec, sftp.manage (~150 tests) |
```

Also update the "Completed Phases" section to include Phase 4D.

- [ ] **Step 4: Update Plan.md**

Mark Phase 4D tasks as complete:

```markdown
- [x] SSH integration: connect to remote machines
- [x] Remote command execution with audit logging
- [x] File transfer: upload/download via SCP/SFTP
```

- [ ] **Step 5: Commit docs**

```bash
git add CLAUDE.md Plan.md
git commit -m "docs: update all documentation for Phase 4D completion"
```

---

## Dependency Graph

```
Task 1: RemoteControlSettings
    ↓
Task 2: RemoteControlGuard (depends on settings)
    ↓
Task 3: SSHConnectionPool (standalone, but used by tools)
    ↓
Task 4: ssh.connect (depends on settings, guard, pool)
    ↓
Task 5: ssh.exec (depends on settings, guard, pool, safety helpers)
    ↓
Task 6: sftp.manage (depends on settings, guard, pool)
    ↓
Task 7: __init__.py wiring (depends on all tools)
    ↓
Task 8: Full test suite + docs (final verification)
```

Tasks 2 and 3 can run in parallel (both depend only on Task 1).
Tasks 4, 5, 6 can run in parallel (each depends on 1+2+3 but not each other).
