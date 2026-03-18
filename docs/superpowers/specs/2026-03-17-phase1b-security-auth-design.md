# Phase 1B: Security & Auth — Design Spec

**Date:** 2026-03-17
**Status:** Draft
**Scope:** Security layer on Phase 1A backend — JWT auth, 4-tier permissions, Docker sandbox, audit logging, kill switch, cost controls
**Depends on:** Phase 1A (backend foundation) — completed

## 1. Overview

Phase 1B adds the security backbone to the Nobla backend. After this phase, the system enforces authentication, permission tiers, sandboxed code execution, full audit trails, emergency kill switch, and budget controls. Every feature in this phase is security-critical and requires 90%+ test coverage.

### Design Decisions Made

- **Auth:** PIN/passphrase with bcrypt + JWT (access + refresh tokens)
- **Permissions:** Session-based 4-tier model with sudo-style escalation (passphrase re-entry for ELEVATED/ADMIN)
- **Sandbox:** Docker-only with abstraction layer for future gVisor swap
- **Kill Switch:** Two-stage (soft → 5s grace → hard kill)
- **Cost Controls:** Per-session, daily, monthly limits with auto-shutoff

## 2. Architecture

```
Incoming RPC Request
    |
    v
Auth Middleware
    |  Validate JWT token on ConnectionState
    |  Reject if not authenticated (except system.health, system.authenticate)
    |
    v
Permission Check
    |  Check ConnectionState.tier >= method's required tier
    |  Reject with -32010 if insufficient
    |
    v
Cost Check (for LLM methods only)
    |  Check budget not exceeded
    |  Reject with -32020 if over limit
    |
    v
Audit Log (pre-execution)
    |  Log: user, method, tier, params (sanitized)
    |
    v
Handler Execution
    |
    v
Audit Log (post-execution)
    |  Log: status (success/error), latency
    |
    v
Response to client
```

## 3. Auth System

### Registration Flow
```
Client sends: system.register { passphrase: "user-chosen-phrase", display_name: "Nabil" }
Server:
  1. Validate passphrase (min 8 chars)
  2. Hash with bcrypt (12 rounds)
  3. Create User row in PostgreSQL
  4. Issue JWT access token (1hr) + refresh token (7d)
  5. Return { user_id, access_token, refresh_token }
```

### Login Flow
```
Client sends: system.authenticate { passphrase: "user-phrase" }
Server:
  1. Find user (Phase 1B: single-user, so find the only user)
  2. Verify bcrypt hash
  3. Issue new JWT pair
  4. Set user_id on ConnectionState
  5. Return { authenticated: true, user_id, access_token, tier: 1 }
```

### Token Structure
```json
{
  "sub": "user-uuid",
  "exp": 1711234567,
  "iat": 1711230967,
  "type": "access"
}
```

### WebSocket Auth
- On WebSocket connect: connection is unauthenticated
- Client must call `system.authenticate` with passphrase or existing JWT
- All methods except `system.health`, `system.authenticate`, `system.register` require auth
- If JWT expired: client uses refresh token via `system.refresh`

### Dependencies
- `passlib[bcrypt]` for password hashing
- `python-jose` or `pyjwt` for JWT (pyjwt is lighter)

## 4. Permission System (4-Tier)

### Tier Definitions

| Tier | Name | Allowed Operations |
|------|------|--------------------|
| 1 | SAFE | Read-only: chat, search, summarize, view history, view costs |
| 2 | STANDARD | + File read/write (designated folders), code execution (sandbox), web browsing (controlled), whitelisted APIs |
| 3 | ELEVATED | + Full file system, code with network, package install, Git, SSH. Each action needs explicit approval. |
| 4 | ADMIN | + Full system control (keyboard/mouse, screen, processes). Every action logged + approved + undoable. |

### Escalation Flow
```
Session starts at TIER 1 (SAFE)

To escalate to TIER 2:
  Client: system.escalate { tier: 2 }
  Server: Sets ConnectionState.tier = 2, returns { tier: 2 }

To escalate to TIER 3 or 4:
  Client: system.escalate { tier: 3, passphrase: "user-phrase" }
  Server: Verifies passphrase, then sets tier
  If passphrase wrong: returns error, tier unchanged

To de-escalate:
  Client: system.escalate { tier: 1 }
  Server: Always allowed, sets tier immediately
```

### Handler Decoration
```python
@rpc_method("code.execute")
@require_tier(Tier.STANDARD)
@audit_logged
async def handle_code_execute(params, state):
    ...
```

### Permission Error
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32010,
    "message": "Insufficient permissions",
    "data": {"required_tier": 2, "current_tier": 1}
  },
  "id": 1
}
```

## 5. Docker Sandbox

### SandboxManager
```python
class SandboxManager:
    async def execute(self, code: str, language: str, timeout: int = 30) -> SandboxResult
    async def cleanup(self) -> None
    async def kill_all(self) -> None  # Used by kill switch
```

### SandboxResult
```python
@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    timed_out: bool
```

### Container Configuration
- **Image:** `python:3.12-slim` (for Python), extensible per language
- **Memory:** 256MB limit (configurable)
- **CPU:** 1 core limit (configurable)
- **Timeout:** 30 seconds (configurable)
- **Network:** `--network none` by default
- **Filesystem:** Read-only root, temp writable volume for output
- **Runtime:** `runc` default, `runsc` (gVisor) when available

### SandboxConfig Abstraction
```python
class SandboxConfig(BaseModel):
    runtime: str = "docker"          # "docker" or "gvisor"
    memory_limit: str = "256m"
    cpu_limit: float = 1.0
    timeout_seconds: int = 30
    network_enabled: bool = False
    allowed_images: list[str] = ["python:3.12-slim"]
```

Swapping to gVisor is a config change: `runtime: "gvisor"` → Docker uses `--runtime=runsc`.

### RPC Method
```json
{
  "method": "code.execute",
  "params": {
    "code": "print('hello')",
    "language": "python",
    "timeout": 10
  }
}
```
Requires TIER 2 (STANDARD) minimum.

## 6. Audit Logging

### audit_logs Table
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id         UUID REFERENCES users(id)
action          TEXT NOT NULL
method          TEXT NOT NULL
tier            INTEGER NOT NULL
status          TEXT NOT NULL CHECK (status IN ('success', 'denied', 'error'))
ip_address      TEXT
latency_ms      INTEGER
metadata        JSONB DEFAULT '{}'
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Index: `CREATE INDEX idx_audit_user_created ON audit_logs(user_id, created_at);`

### What Gets Logged
- Every RPC method call (including denied ones)
- Auth attempts (success/failure)
- Tier escalations
- Kill switch activations
- Sandbox executions (with exit code, timed_out status)
- Cost limit events (warnings, shutoffs)

### Sanitization
- Passphrase fields replaced with `"[REDACTED]"` before logging
- Long message content truncated to 500 chars in logs
- Full content stays in the messages table, not audit logs

### @audit_logged Decorator
Wraps RPC handlers automatically:
```python
@audit_logged
async def handle_something(params, state):
    ...
# Logs: pre-execution (action started) and post-execution (result/error)
```

## 7. Kill Switch

### Two-Stage Design
```
Stage 1: SOFT KILL
  - Set global _shutdown flag
  - Cancel all running async tasks (LLM streams, sandbox executions)
  - Send notification to all WebSocket clients: {"method": "system.killed", "params": {"stage": "soft"}}
  - Wait 5 seconds for graceful cleanup

Stage 2: HARD KILL (after 5s or immediate if second kill request)
  - Force-close all WebSocket connections
  - Kill all Docker sandbox containers (docker kill)
  - Send final notification before disconnect
  - Server enters KILLED state: rejects all requests except system.resume and system.health
```

### Activation Methods
- **RPC:** `system.kill` (any authenticated user, any tier)
- **REST:** `POST /api/kill` (localhost only, no auth — emergency endpoint)
- **Second kill while soft-killing:** immediately triggers hard kill

### Resume
- `system.resume` (requires passphrase re-entry)
- Clears shutdown flag, accepts new connections again

### Kill State
```python
class KillState(Enum):
    RUNNING = "running"
    SOFT_KILLING = "soft_killing"
    KILLED = "killed"
```

## 8. Cost Controls

### Budget Configuration
```yaml
costs:
  daily_limit_usd: 5.0
  monthly_limit_usd: 50.0
  per_session_limit_usd: 1.0
  warning_threshold: 0.8
```

### Pre-Request Check
Before every LLM call:
1. Query `llm_usage` table for today's total (by user_id)
2. If daily total >= daily_limit → reject with -32020
3. If monthly total >= monthly_limit → reject with -32020
4. If session total >= per_session_limit → reject with -32020
5. If any total >= warning_threshold * limit → send warning notification

### Cost Error
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32020,
    "message": "Daily budget exceeded",
    "data": {"limit_usd": 5.0, "spent_usd": 5.12, "period": "daily"}
  },
  "id": 1
}
```

### Dashboard RPC
`system.costs` returns:
```json
{
  "today_usd": 1.23,
  "week_usd": 4.56,
  "month_usd": 12.34,
  "session_usd": 0.45,
  "limits": {"daily": 5.0, "monthly": 50.0, "session": 1.0},
  "warnings": []
}
```

## 9. New RPC Methods

| Method | Min Tier | Description |
|--------|----------|-------------|
| `system.register` | none | Create user with passphrase |
| `system.authenticate` | none | Login with passphrase or JWT |
| `system.refresh` | none | Refresh expired access token |
| `system.escalate` | SAFE | Change permission tier |
| `system.kill` | SAFE | Trigger kill switch |
| `system.resume` | SAFE | Resume after kill (requires passphrase) |
| `system.costs` | SAFE | Get cost dashboard data |
| `code.execute` | STANDARD | Run code in Docker sandbox |

### Updated Error Codes
| Code | Meaning |
|------|---------|
| -32010 | Insufficient permissions (tier too low) |
| -32011 | Authentication required |
| -32012 | Authentication failed (wrong passphrase) |
| -32013 | Token expired |
| -32020 | Budget exceeded |
| -32021 | Budget warning (notification) |
| -32030 | Server killed (in shutdown state) |

## 10. Config Additions

Added to `config.yaml`:
```yaml
auth:
  access_token_expire_minutes: 60
  refresh_token_expire_days: 7
  bcrypt_rounds: 12
  min_passphrase_length: 8

security:
  default_tier: 1
  escalation_requires_passphrase: [3, 4]

sandbox:
  enabled: true
  runtime: "docker"
  memory_limit: "256m"
  cpu_limit: 1.0
  timeout_seconds: 30
  network_enabled: false
  allowed_images: ["python:3.12-slim"]

costs:
  daily_limit_usd: 5.0
  monthly_limit_usd: 50.0
  per_session_limit_usd: 1.0
  warning_threshold: 0.8
```

## 11. Project Structure (new files)

```
backend/nobla/security/
    __init__.py
    auth.py              # JWT generation/validation, passphrase hashing
    permissions.py       # Tier enum, require_tier decorator, escalation logic
    sandbox.py           # SandboxManager, SandboxConfig, SandboxResult
    audit.py             # AuditLogger, audit_logged decorator, sanitization
    killswitch.py        # KillSwitch class, two-stage logic, state management
    costs.py             # CostTracker, budget checks, dashboard data

backend/nobla/db/models/
    audit.py             # AuditLog ORM model (new table)

backend/nobla/db/repositories/
    audit_repo.py        # AuditLogRepository

backend/tests/
    test_auth.py
    test_permissions.py
    test_sandbox.py
    test_audit.py
    test_killswitch.py
    test_costs.py
```

## 12. Dependencies (new for Phase 1B)

```toml
# Add to pyproject.toml dependencies
"pyjwt>=2.9.0",
"passlib[bcrypt]>=1.7.4",
"docker>=7.0.0",
```

## 13. Acceptance Criteria

1. User can register with a passphrase and receive JWT tokens
2. WebSocket methods (except health/auth) require valid JWT
3. Permission tiers enforced: SAFE user cannot execute code
4. Escalation to TIER 3+ requires passphrase re-entry
5. Code executes inside Docker container with resource limits
6. Sandbox container cannot access host network
7. Every RPC call is logged in audit_logs with user, method, tier, status
8. Kill switch (soft) stops all running tasks within 5 seconds
9. Kill switch (hard) terminates everything immediately
10. Cost controls reject LLM calls when budget exceeded
11. `system.costs` returns accurate spend data
12. 90%+ test coverage on all security/ modules
13. All files under 750 lines

## 14. What's NOT in Phase 1B

| Deferred To | Feature |
|------------|---------|
| Phase 1C | Flutter app (auth UI, dashboard, kill switch button) |
| Phase 1D | End-to-end integration tests |
| Phase 2 | Per-action approval for TIER 3/4 (currently just tier check) |
| Phase 2 | Undo system for reversible actions |
| Phase 4 | gVisor runtime (config-ready but not implemented) |
| Phase 5 | Multi-user support (currently single-user) |
