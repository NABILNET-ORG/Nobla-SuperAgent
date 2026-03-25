# Phase 4D: Remote Control — Design Specification

**Date:** 2026-03-25
**Status:** Draft
**Author:** Claude (AI) + Human review
**Phase:** 4D of 7-phase Nobla Agent roadmap

## 1. Overview

Phase 4D adds secure remote control capabilities to Nobla Agent: SSH connections, remote command execution, and SFTP file transfers. All operations are ADMIN-tier with multi-layered security, conditional approval flows, and full audit trails.

### Scope

- SSH connection management with pooling and lifecycle controls
- Remote command execution with output capture and timeout enforcement
- SFTP file operations (upload, download, list, delete, stat)
- Secure credential handling (agent forwarding, key files, opt-in password)
- Host key verification with MITM protection

### Out of Scope (Future Work)

- SSH tunneling / port forwarding
- Interactive shells (PTY)
- Jump hosts / proxy chains
- Remote desktop / VNC

## 2. Architecture

### 2.1 Tool Structure

Three focused tools following the Phase 4B pattern (separate tools per concern):

| Tool | Purpose | Actions |
|------|---------|---------|
| `ssh.connect` | Connection lifecycle | `connect`, `disconnect`, `list` |
| `ssh.exec` | Remote command execution | `run` |
| `sftp.manage` | Remote file transfer | `upload`, `download`, `list`, `delete`, `stat` |

### 2.2 Shared Infrastructure

| Component | File | Purpose |
|-----------|------|---------|
| `SSHConnectionPool` | `pool.py` | Manages persistent asyncssh sessions with idle/lifetime timeouts |
| `RemoteControlSettings` | `settings.py` | Allow-lists, deny-lists, timeouts, size limits |
| `RemoteControlGuard` | `safety.py` | Rate limiting, kill switch, connection caps, halt/resume |

### 2.3 Library Choice

**`asyncssh`** — async-native SSH library. Fits the FastAPI + async architecture without `run_in_executor()` wrappers. Supports SSH2, SFTP, agent forwarding, and known_hosts natively.

### 2.4 File Structure

```
backend/nobla/tools/remote/
├── __init__.py           # Import all tools for auto-registration
├── ssh_connect.py        # ssh.connect tool (~200 lines)
├── ssh_exec.py           # ssh.exec tool (~250 lines)
├── sftp_manage.py        # sftp.manage tool (~300 lines)
├── pool.py               # SSHConnectionPool (~200 lines)
├── safety.py             # RemoteControlGuard (~150 lines)

backend/tests/tools/remote/
├── test_ssh_connect.py
├── test_ssh_exec.py
├── test_sftp_manage.py
├── test_pool.py
├── test_safety.py
```

## 3. Tool Specifications

### 3.1 `ssh.connect` — Connection Management

**Class:** `SSHConnectTool(BaseTool)`
**Category:** `ToolCategory.SSH`
**Tier:** `Tier.ADMIN`
**Default approval:** `False` (conditional via `needs_approval()`)

#### Actions

**`connect`** — Establish SSH session
- **Params:** `{host: str, user: str, port?: int=22, key_path?: str, passphrase?: str, password?: str, label?: str}`
- **Approval:** Always required
- **Returns:** `{connection_id: str, host: str, user: str, port: int, host_key_fingerprint: str, label: str|null}`
- **Validation:**
  - `settings.remote_control.enabled` must be `True` (checked first in all tools — **C3 fix**)
  - `host` must be in `allowed_hosts`
  - `user` must be in `allowed_users`
  - `port` must be 1-65535
  - If `password` provided, `allow_password_auth` must be `True` in settings
  - Host key verified against `~/.ssh/known_hosts` (see Section 5.2)
- **Label:** Optional human-readable label (e.g., "production-web") for UX in activity feed and `list` output

**`disconnect`** — Close SSH session
- **Params:** `{connection_id: str}`
- **Approval:** Never
- **Returns:** `{disconnected: true, host: str}`

**`list`** — List active connections
- **Params:** `{}`
- **Approval:** Never
- **Returns:** `{connections: [{connection_id, host, user, port, label, connected_at, last_activity, idle_seconds}]}`

#### Approval Dialog Description

```
"Connect to [user]@[host]:[port] via SSH (key-based auth)"
"Connect to [user]@[host]:[port] via SSH (password auth — less secure, consider SSH keys)"
```

#### Params Summary (Audit-Safe)

```python
def get_params_summary(self, params):
    args = params.args
    return {
        "action": args.get("action"),
        "host": args.get("host"),
        "user": args.get("user"),
        "port": args.get("port", 22),
        "auth_method": "password" if args.get("password") else "key",
        # NEVER include: passphrase, password, key_path
    }
```

### 3.2 `ssh.exec` — Remote Command Execution

**Class:** `SSHExecTool(BaseTool)`
**Category:** `ToolCategory.SSH`
**Tier:** `Tier.ADMIN`
**Default approval:** `False` (conditional via `needs_approval()`)

#### Actions

**`run`** — Execute a command on a remote host
- **Params:** `{connection_id: str, command: str, timeout?: int, cwd?: str}`
- **Approval:** Conditional (see below)
- **Returns:** `{stdout: str, stderr: str, exit_code: int, duration_ms: int, truncated: bool}`

#### Enabled Check (C3 Fix)

All three tools check `settings.remote_control.enabled` at the start of `validate()`:

```python
async def validate(self, params: ToolParams) -> None:
    settings = self._settings()
    if not settings.remote_control.enabled:
        raise ValueError("Remote control tools are disabled in settings")
    # ... action-specific validation ...
```

#### Conditional Approval Logic

```python
def needs_approval(self, params):
    command = params.args.get("command", "")
    settings = self._settings()

    # Step 1: Check blocked binaries — always deny (raise in validate())
    # Step 2: Parse first token
    first_token = _parse_first_token(command)

    # Step 3: If command contains chaining operators, always approve
    if _has_chaining_operators(command):
        return True

    # Step 4: If first token is in safe_commands, skip approval
    if first_token in settings.remote_control.safe_commands:
        return False

    # Step 5: Everything else needs approval
    return True
```

#### Command Parsing Safety

**Design limitation (documented per C2 fix):** The chaining detection is intentionally conservative (biased toward requiring approval). False positives (operators inside quoted strings trigger approval unnecessarily) are acceptable. False negatives in novel bypass vectors are mitigated by the ADMIN tier and approval flow. Perfect shell parsing is impossible — this is defense-in-depth, not a guarantee.

```python
_CHAINING_OPERATORS = {";", "&&", "||", "|", "`", "$(", "\n", "<<", "<("}

def _parse_first_token(command: str) -> str:
    """Extract the first command token, ignoring env var prefixes.

    Note: shlex.split() can raise ValueError on malformed input
    (unterminated quotes). In that case, treat as needing approval.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""  # Malformed → not in safe_commands → approval required
    for token in tokens:
        if "=" not in token:
            return token.split("/")[-1]  # basename
    return ""

def _has_chaining_operators(command: str) -> bool:
    """Check if command chains multiple operations."""
    return any(op in command for op in _CHAINING_OPERATORS)
```

#### Output Handling

- Output truncated to `max_output_bytes` (default 1MB) OR `max_output_lines` (default 10,000) — whichever is hit first
- `truncated: bool` flag in response indicates partial output
- stderr captured separately
- Exit code always returned
- Timeout enforced: `min(params.timeout, settings.max_command_timeout_s)`

### 3.3 `sftp.manage` — Remote File Transfer

**Class:** `SFTPManageTool(BaseTool)`
**Category:** `ToolCategory.SSH`
**Tier:** `Tier.ADMIN`
**Default approval:** `False` (conditional via `needs_approval()`)

#### Actions

**`upload`** — Upload local file to remote host
- **Params:** `{connection_id: str, local_path: str, remote_path: str}`
- **Approval:** Always
- **Validation:** Local path in `allowed_read_dirs`, remote path in `allowed_remote_dirs`, file size under `sftp_max_file_size`

**`download`** — Download remote file to local path
- **Params:** `{connection_id: str, remote_path: str, local_path: str}`
- **Approval:** Conditional — if file size > `sftp_approval_threshold` (10MB)
- **Validation:** Local path in `allowed_write_dirs`, remote path in `allowed_remote_dirs`

**`list`** — List remote directory contents
- **Params:** `{connection_id: str, remote_path: str}`
- **Approval:** Never
- **Returns:** `{entries: [{name, size, modified, is_dir, permissions}]}`

**`delete`** — Delete remote file
- **Params:** `{connection_id: str, remote_path: str}`
- **Approval:** Always
- **Returns:** `{deleted: true, path: str}`

**`stat`** — Get remote file metadata
- **Params:** `{connection_id: str, remote_path: str}`
- **Approval:** Never
- **Returns:** `{name, size, modified, is_dir, permissions, owner, group}`

#### Params Summary (Audit-Safe) — I5 Fix

```python
# ssh.exec
def get_params_summary(self, params):
    args = params.args
    cmd = args.get("command", "")
    return {
        "action": "run",
        "connection_id": args.get("connection_id"),
        "command": cmd[:200] + ("..." if len(cmd) > 200 else ""),
        "timeout": args.get("timeout"),
        # NEVER include: stdout, stderr, output
    }

# sftp.manage
def get_params_summary(self, params):
    args = params.args
    return {
        "action": args.get("action"),
        "connection_id": args.get("connection_id"),
        "local_path": args.get("local_path"),
        "remote_path": args.get("remote_path"),
        # NEVER include: file contents
    }
```

#### Settings Override Pattern — I6 Fix

All three tools use the `_settings_override` pattern from Phase 4B for test injection:

```python
class SFTPManageTool(BaseTool):
    _settings_override: Settings | None = None

    def _settings(self) -> Settings:
        if self._settings_override is not None:
            return self._settings_override
        return _get_settings()
```

#### Path Validation (I4 Fix)

Local paths validated against existing `ComputerControlSettings.allowed_read_dirs` / `allowed_write_dirs`. Remote paths validated against `RemoteControlSettings.allowed_remote_dirs`.

**Remote path security:**
- Remote paths MUST be absolute (must start with `/`) — reject relative paths
- Apply `posixpath.normpath()` before prefix matching to collapse `..` segments
- This cannot prevent all symlink-based escapes on the remote side; the ADMIN tier + approval flow is the ultimate safeguard
- Uses string prefix matching (not `Path.is_relative_to()`) since remote filesystem is inaccessible

## 4. Settings

### 4.1 `RemoteControlSettings`

Added to `backend/nobla/config/settings.py` as a nested model in the main `Settings` class.

```python
class RemoteControlSettings(BaseModel):
    """Configuration for Phase 4D remote control tools."""

    enabled: bool = True

    # --- Allow-lists (default deny) ---
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    allowed_remote_dirs: list[str] = Field(default_factory=list)

    # --- Command safety (C1 fix: split into binaries + patterns) ---
    safe_commands: list[str] = Field(
        default_factory=lambda: [
            "ls", "cat", "head", "tail", "grep", "find", "wc",
            "df", "du", "whoami", "hostname", "date", "uptime",
            "ps", "top", "free", "uname", "env", "echo", "pwd",
        ]
    )
    blocked_binaries: list[str] = Field(
        default_factory=lambda: [
            "mkfs", "dd", "shutdown", "reboot",
            "halt", "poweroff",
        ]
    )
    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm\s+.*-.*r.*-.*f\s+/",    # rm -rf /
            r"dd\s+.*of=/dev/",            # dd writing to devices
            r">\s*/dev/sd",                # redirect to block devices
            r"init\s+[06]",                # init 0 / init 6
            r"systemctl\s+(poweroff|halt)", # systemd shutdown
        ]
    )

    # --- SSH settings ---
    ssh_key_path: str | None = None
    allow_password_auth: bool = False
    known_hosts_policy: str = "strict"  # "strict", "ask_first_time"
    known_hosts_path: str | None = None  # defaults to ~/.ssh/known_hosts

    # --- Timeouts ---
    ssh_connect_timeout_s: int = 30
    default_command_timeout_s: int = 60
    max_command_timeout_s: int = 600

    # --- Connection pool ---
    max_connections: int = 5
    idle_timeout_s: int = 300
    max_lifetime_s: int = 3600

    # --- SFTP limits ---
    sftp_max_file_size: int = 104_857_600      # 100MB
    sftp_approval_threshold: int = 10_485_760   # 10MB — downloads over this need approval

    # --- Output ---
    max_output_bytes: int = 1_048_576  # 1MB
    max_output_lines: int = 10_000     # line-count cap in addition to byte cap

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

### 4.2 Integration with Main Settings

```python
class Settings(BaseModel):
    # ... existing fields ...
    computer_control: ComputerControlSettings = Field(default_factory=ComputerControlSettings)
    remote_control: RemoteControlSettings = Field(default_factory=RemoteControlSettings)
```

## 5. Security Model

### 5.1 Six-Layer Security (Matching Phase 4B)

| Layer | Mechanism | Details |
|-------|-----------|---------|
| 1. Tier gating | ADMIN tier | Requires passphrase authentication at the platform level |
| 2. Allow-lists | Hosts, users, remote dirs | Default deny — empty allow-list = all blocked |
| 3. Deny-lists | Blocked binaries + patterns | Safety net — first-token binary matching + regex patterns for dangerous argument combos. Not the primary protection (approval flow is). |
| 4. Conditional approval | `needs_approval()` | Per-action approval based on operation and params |
| 5. Rate limiting + caps | `RemoteControlGuard` | Max connections, idle timeouts, halt/resume |
| 6. Kill switch | Immediate termination | Closes all SSH sessions, halts guard, denies pending approvals |

### 5.2 Host Key Verification

**Policy: `strict` (default)**
- Known host: allow connection
- Unknown host: BLOCK — user must manually add to `~/.ssh/known_hosts`
- Changed host key: BLOCK — surface loud warning about potential MITM

**Policy: `ask_first_time`**
- Known host: allow connection
- Unknown host: show fingerprint in approval dialog, user accepts → added to known_hosts
- Changed host key: BLOCK — same as strict (never auto-accept changed keys)

Implementation uses `asyncssh.read_known_hosts()` and custom `known_hosts` callback.

### 5.3 Credential Handling

| Method | Priority | Storage | Logged? |
|--------|----------|---------|---------|
| SSH agent forwarding | 1 (preferred) | OS agent | No credentials touch Nobla |
| Key file | 2 | Local file, path in settings | Path logged, key content never |
| Password (opt-in) | 3 (last resort) | Passed in params only | Never logged, warning in approval |

- `allow_password_auth` defaults to `False` — must be explicitly enabled
- Passphrase for key files passed in connect params, never persisted
- `get_params_summary()` redacts all credential fields

### 5.4 Audit Trail

Every operation is logged via the existing executor pipeline:

```
{
    "tool": "ssh.exec",
    "action": "run",
    "host": "prod.example.com",
    "user": "deploy",
    "command": "ls -la /var/www",  // truncated if long
    "exit_code": 0,
    "duration_ms": 245,
    "truncated": false,
    "approval_required": true,
    "approval_result": "approved",
    "timestamp": "2026-03-25T14:30:00Z"
}
```

Command output (stdout/stderr) is NOT logged — it may contain secrets. Only exit code and truncation flag.

## 6. SSHConnectionPool

### 6.1 Design

```python
class SSHConnectionPool:
    """Manages persistent asyncssh connections with lifecycle controls."""

    _instance: SSHConnectionPool | None = None
    _lock: asyncio.Lock

    # Connection storage
    _connections: dict[str, SSHConnection]  # connection_id -> SSHConnection

    @dataclass
    class SSHConnection:
        id: str                          # UUID
        conn: asyncssh.SSHClientConnection
        host: str
        user: str
        port: int
        created_at: float                # time.time()
        last_activity: float
        sftp_client: asyncssh.SFTPClient | None = None
```

### 6.2 Access Pattern (I3 Fix)

Module-level lazy singleton matching Phase 4B's `_get_settings()` pattern:

```python
_pool_instance: SSHConnectionPool | None = None
_pool_override: SSHConnectionPool | None = None  # Test injection

def _get_pool() -> SSHConnectionPool:
    global _pool_instance
    if _pool_override is not None:
        return _pool_override
    if _pool_instance is None:
        _pool_instance = SSHConnectionPool()
    return _pool_instance
```

### 6.3 Lifecycle

- **Create:** `pool.connect(host, user, port, **auth)` → returns connection_id
- **Get:** `pool.get(connection_id)` → returns SSHConnection or raises
- **Release:** `pool.disconnect(connection_id)` → closes and removes
- **List:** `pool.list_connections()` → returns metadata for all active
- **Halt:** `pool.halt()` → closes ALL connections immediately (kill switch)
- **Reset:** `pool.reset()` → clear all state (tests) — S3 fix
- **Cleanup:** Background task runs every 60s, prunes idle (>300s) and expired (>3600s) connections

### 6.4 Concurrency

- `asyncio.Lock` protects pool mutations
- Each connection is independent — concurrent commands on different connections are safe
- Same connection: sequential execution (asyncssh handles this internally)
- Max connections enforced at `connect()` time

## 7. RemoteControlGuard

### 7.1 Interface (I1 Fix: Unified Entry Point)

Following `InputSafetyGuard`'s single `check()` pattern, the guard uses a unified entry point that dispatches internally based on operation type:

```python
class RemoteControlGuard:
    _halted: bool = False

    @classmethod
    def check(cls, operation: str, settings: RemoteControlSettings, **kwargs) -> None:
        """Unified safety check entry point.

        Args:
            operation: "connect", "command", or "transfer"
            settings: RemoteControlSettings instance
            **kwargs: Operation-specific params:
                - connect: host=str
                - command: command=str
                - transfer: file_size=int
        """
        cls._check_halt()
        if operation == "connect":
            cls._check_host_allowed(kwargs["host"], settings)
            cls._check_connection_cap(settings)
        elif operation == "command":
            cls._check_blocked_binary(kwargs["command"], settings)
            cls._check_blocked_pattern(kwargs["command"], settings)
        elif operation == "transfer":
            cls._check_file_size(kwargs["file_size"], settings)

    @classmethod
    def halt(cls) -> None:
        """Emergency stop — also calls SSHConnectionPool.halt()."""
        cls._halted = True
        _get_pool().halt()

    @classmethod
    def resume(cls) -> None:
        """Clear halt flag."""
        cls._halted = False

    @classmethod
    def reset(cls) -> None:
        """Reset all state (tests)."""
        cls._halted = False
```

### 7.2 Kill Switch Integration (I2 Fix: Wiring)

Registration happens during tool module initialization, matching the `InputSafetyGuard` pattern:

```python
# In backend/nobla/tools/remote/__init__.py
from nobla.security.killswitch import kill_switch
from .safety import RemoteControlGuard
from .pool import _get_pool

# Register kill switch callbacks
kill_switch.on_soft_kill(RemoteControlGuard.halt)

async def _halt_pool():
    await _get_pool().halt()

kill_switch.on_hard_kill(_halt_pool)
```

When the kill switch fires:
1. `RemoteControlGuard.halt()` sets `_halted = True`
2. `SSHConnectionPool.halt()` closes all active SSH sessions
3. `ApprovalManager.deny_all()` rejects pending approvals
4. All subsequent tool calls fail immediately with "Remote control halted"

## 8. Error Handling

| Error | Source | Handling |
|-------|--------|----------|
| Host not in allow-list | `validate()` | `ValueError` → `ToolResult(success=False)` |
| Connection refused | `asyncssh` | Catch, return clear error with host:port |
| Authentication failed | `asyncssh` | Catch, return error (no credential details) |
| Host key mismatch | `asyncssh` / known_hosts | BLOCK, warn about MITM |
| Command timeout | `asyncio.wait_for` | Kill command, return partial output + error |
| Connection lost mid-command | `asyncssh` | Remove from pool, return error |
| File too large | `validate()` | `ValueError` with size details |
| Pool exhausted | `RemoteControlGuard` | Error: "Max connections (5) reached" |
| Kill switch | `RemoteControlGuard` | `ToolExecutionError`: "Remote control halted" |
| asyncssh not installed | Import check | Graceful error: "pip install asyncssh" |

### Graceful Degradation

If `asyncssh` is not installed, all three tools register but return a clear error on any action:
```python
try:
    import asyncssh
except ImportError:
    asyncssh = None

# In execute():
if asyncssh is None:
    return ToolResult(
        success=False,
        error="asyncssh is not installed. Run: pip install asyncssh"
    )
```

## 9. Flutter Integration

**No new Flutter code required.** Phase 4D reuses existing Phase 4B components:

| Component | File | Reuse |
|-----------|------|-------|
| Approval bottom sheet | `approval_sheet.dart` | Shows SSH operation descriptions |
| Activity feed | `activity_feed.dart` | Displays SSH tool events |
| Security dashboard | `security_dashboard.dart` | Already wired to activity feed |

Tool-specific display strings are provided by `describe_action()` overrides:
- `"Connect to deploy@prod.example.com:22 via SSH"`
- `"Execute on prod.example.com: ls -la /var/www"`
- `"Upload config.yml to prod.example.com:/etc/app/"`
- `"Delete prod.example.com:/tmp/old-backup.tar.gz"`

**Future enhancement (S2):** SFTP progress tracking for large transfers via WebSocket events. Deferred to a future iteration — v1 shows a spinner until complete.

## 10. Testing Strategy

### 10.1 Approach

TDD throughout — tests first, implementation second. All tests use mocked asyncssh (no real SSH connections in tests).

### 10.2 Test Structure

| File | Coverage | Est. Tests |
|------|----------|------------|
| `test_ssh_connect.py` | connect/disconnect/list, allow-lists, host keys, auth methods | ~30 |
| `test_ssh_exec.py` | run, safe/blocked commands, chaining detection, timeouts, output truncation | ~35 |
| `test_sftp_manage.py` | upload/download/list/delete/stat, path validation, size limits | ~35 |
| `test_pool.py` | lifecycle, idle/lifetime cleanup, halt, concurrency, max connections | ~25 |
| `test_safety.py` | guard checks, halt/resume/reset, blocked commands, kill switch | ~25 |
| **Total** | | **~150** |

### 10.3 Test Patterns (from Phase 4B)

- Lazy singleton override: `_settings_override` for test injection
- Mock asyncssh connections with `AsyncMock`
- Each test file independent — no shared mutable state between tests
- `RemoteControlGuard.reset()` in setUp/tearDown
- `SSHConnectionPool.reset()` for clean pool state

## 11. Dependencies

### New Python Dependencies

```
asyncssh>=2.14.0,<3.0.0    # SSH2 client/server, SFTP, agent forwarding (ceiling prevents breaking changes)
```

### Existing Dependencies Used

- `pydantic` — settings models
- `asyncio` — concurrency, locks, timeouts
- `uuid` — connection IDs
- `shlex` — command parsing
- `pathlib` — local path validation
- `time` — timestamps for pool lifecycle

## 12. Estimated Size

| Component | Lines |
|-----------|-------|
| `ssh_connect.py` | ~200 |
| `ssh_exec.py` | ~250 |
| `sftp_manage.py` | ~300 |
| `pool.py` | ~200 |
| `safety.py` | ~150 |
| `__init__.py` | ~10 |
| Settings additions | ~60 |
| **Source total** | **~1170** |
| **Test total** | **~1500** |
| **Tests count** | **~150** |

All source files well under the 750-line hard limit.
