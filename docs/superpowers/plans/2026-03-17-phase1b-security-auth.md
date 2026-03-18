# Phase 1B: Security & Auth Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add security layer to the Phase 1A backend: JWT auth, 4-tier permissions, Docker sandbox, audit logging, two-stage kill switch, and cost controls.

**Architecture:** Six independent security modules under `nobla/security/`, each with a clear interface. Decorators (`@require_tier`, `@audit_logged`) wrap existing RPC handlers. Auth middleware intercepts all WebSocket messages before dispatch. Cost checks gate LLM calls.

**Tech Stack:** pyjwt, passlib[bcrypt], docker (Python SDK), existing FastAPI/SQLAlchemy/structlog

**Spec:** `docs/superpowers/specs/2026-03-17-phase1b-security-auth-design.md`

---

## Task 1: Add Phase 1B Dependencies + Security Package Structure

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/nobla/security/__init__.py`
- Create: `backend/nobla/db/models/audit.py`
- Modify: `backend/nobla/db/models/__init__.py`
- Modify: `backend/nobla/config/settings.py`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

Add to `dependencies` list:
```toml
"pyjwt>=2.9.0",
"passlib[bcrypt]>=1.7.4",
"docker>=7.0.0",
```

- [ ] **Step 2: Install new deps**

Run: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 3: Create security package**

Create `backend/nobla/security/__init__.py` (empty for now).

- [ ] **Step 4: Add AuditLog model**

Create `backend/nobla/db/models/audit.py`:
```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from nobla.db.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        Index("idx_audit_user_created", "user_id", "created_at"),
    )
```

- [ ] **Step 5: Update models __init__.py**

Add to `backend/nobla/db/models/__init__.py`:
```python
from nobla.db.models.audit import AuditLog
```
Add `"AuditLog"` to `__all__`.

- [ ] **Step 6: Add config sections for auth, security, sandbox, costs**

Add to `backend/nobla/config/settings.py`:
```python
class AuthSettings(BaseModel):
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12
    min_passphrase_length: int = 8


class SecuritySettings(BaseModel):
    default_tier: int = 1
    escalation_requires_passphrase: list[int] = [3, 4]


class SandboxSettings(BaseModel):
    enabled: bool = True
    runtime: str = "docker"
    memory_limit: str = "256m"
    cpu_limit: float = 1.0
    timeout_seconds: int = 30
    network_enabled: bool = False
    allowed_images: list[str] = ["python:3.12-slim"]


class CostSettings(BaseModel):
    daily_limit_usd: float = 5.0
    monthly_limit_usd: float = 50.0
    per_session_limit_usd: float = 1.0
    warning_threshold: float = 0.8
```

Add to `Settings` class:
```python
auth: AuthSettings = AuthSettings()
security: SecuritySettings = SecuritySettings()
sandbox: SandboxSettings = SandboxSettings()
costs: CostSettings = CostSettings()
```

- [ ] **Step 7: Verify models import**

Run: `cd backend && python -c "from nobla.db.models import AuditLog, Base; print('audit_logs' in {t.name for t in Base.metadata.sorted_tables})"`
Expected: `True`

- [ ] **Step 8: Run existing tests to make sure nothing broke**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All 32 tests pass

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/nobla/security/ backend/nobla/db/models/audit.py backend/nobla/db/models/__init__.py backend/nobla/config/settings.py
git commit -m "feat: add Phase 1B deps, AuditLog model, security config sections"
```

---

## Task 2: Auth System (JWT + Passphrase)

**Files:**
- Create: `backend/nobla/security/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing auth tests**

Create `backend/tests/test_auth.py`:
```python
import pytest
from nobla.security.auth import AuthService


@pytest.fixture
def auth():
    return AuthService(secret_key="test-secret", access_expire_minutes=60, refresh_expire_days=7, bcrypt_rounds=4)


def test_hash_and_verify_passphrase(auth):
    hashed = auth.hash_passphrase("mypassphrase")
    assert auth.verify_passphrase("mypassphrase", hashed) is True
    assert auth.verify_passphrase("wrong", hashed) is False


def test_create_access_token(auth):
    token = auth.create_access_token(user_id="user-123")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_token(auth):
    token = auth.create_refresh_token(user_id="user-123")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_decode_invalid_token(auth):
    result = auth.decode_token("invalid.token.here")
    assert result is None


def test_decode_expired_token(auth):
    svc = AuthService(secret_key="test", access_expire_minutes=-1, refresh_expire_days=7, bcrypt_rounds=4)
    token = svc.create_access_token(user_id="user-123")
    assert svc.decode_token(token) is None


def test_validate_passphrase_too_short(auth):
    assert auth.validate_passphrase("short") == False
    assert auth.validate_passphrase("longenough") == True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement AuthService**

Create `backend/nobla/security/auth.py`:
```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
import jwt


class AuthService:
    def __init__(self, secret_key: str, access_expire_minutes: int = 60,
                 refresh_expire_days: int = 7, bcrypt_rounds: int = 12,
                 min_passphrase_length: int = 8):
        self.secret_key = secret_key
        self.access_expire_minutes = access_expire_minutes
        self.refresh_expire_days = refresh_expire_days
        self.min_passphrase_length = min_passphrase_length
        self._pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=bcrypt_rounds)

    def hash_passphrase(self, passphrase: str) -> str:
        return self._pwd_context.hash(passphrase)

    def verify_passphrase(self, passphrase: str, hashed: str) -> bool:
        return self._pwd_context.verify(passphrase, hashed)

    def validate_passphrase(self, passphrase: str) -> bool:
        return len(passphrase) >= self.min_passphrase_length

    def create_access_token(self, user_id: str) -> str:
        return self._create_token(user_id, "access",
                                  timedelta(minutes=self.access_expire_minutes))

    def create_refresh_token(self, user_id: str) -> str:
        return self._create_token(user_id, "refresh",
                                  timedelta(days=self.refresh_expire_days))

    def decode_token(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    def _create_token(self, user_id: str, token_type: str, expires_delta: timedelta) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: All 7 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/security/auth.py backend/tests/test_auth.py
git commit -m "feat: add JWT auth service with passphrase hashing"
```

---

## Task 3: Permission System (4-Tier)

**Files:**
- Create: `backend/nobla/security/permissions.py`
- Create: `backend/tests/test_permissions.py`

- [ ] **Step 1: Write failing permission tests**

Create `backend/tests/test_permissions.py`:
```python
import pytest
from nobla.security.permissions import Tier, PermissionChecker, InsufficientPermissions


def test_tier_ordering():
    assert Tier.SAFE < Tier.STANDARD < Tier.ELEVATED < Tier.ADMIN


def test_tier_from_int():
    assert Tier(1) == Tier.SAFE
    assert Tier(4) == Tier.ADMIN


def test_permission_check_passes():
    checker = PermissionChecker()
    checker.check(current_tier=Tier.STANDARD, required_tier=Tier.STANDARD)  # no exception


def test_permission_check_fails():
    checker = PermissionChecker()
    with pytest.raises(InsufficientPermissions) as exc_info:
        checker.check(current_tier=Tier.SAFE, required_tier=Tier.STANDARD)
    assert exc_info.value.required_tier == Tier.STANDARD
    assert exc_info.value.current_tier == Tier.SAFE


def test_escalation_tier2_no_passphrase():
    checker = PermissionChecker(escalation_requires_passphrase=[3, 4])
    assert checker.requires_passphrase_for_escalation(2) is False


def test_escalation_tier3_requires_passphrase():
    checker = PermissionChecker(escalation_requires_passphrase=[3, 4])
    assert checker.requires_passphrase_for_escalation(3) is True
    assert checker.requires_passphrase_for_escalation(4) is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_permissions.py -v`

- [ ] **Step 3: Implement PermissionChecker**

Create `backend/nobla/security/permissions.py`:
```python
from __future__ import annotations
import enum


class Tier(enum.IntEnum):
    SAFE = 1
    STANDARD = 2
    ELEVATED = 3
    ADMIN = 4


class InsufficientPermissions(Exception):
    def __init__(self, required_tier: Tier, current_tier: Tier):
        self.required_tier = required_tier
        self.current_tier = current_tier
        super().__init__(f"Requires tier {required_tier.name}, current: {current_tier.name}")


class PermissionChecker:
    def __init__(self, escalation_requires_passphrase: list[int] | None = None):
        self.escalation_requires_passphrase = escalation_requires_passphrase or [3, 4]

    def check(self, current_tier: Tier, required_tier: Tier) -> None:
        if current_tier < required_tier:
            raise InsufficientPermissions(required_tier, current_tier)

    def requires_passphrase_for_escalation(self, target_tier: int) -> bool:
        return target_tier in self.escalation_requires_passphrase
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_permissions.py -v`
Expected: All 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/security/permissions.py backend/tests/test_permissions.py
git commit -m "feat: add 4-tier permission system with escalation rules"
```

---

## Task 4: Audit Logger

**Files:**
- Create: `backend/nobla/security/audit.py`
- Create: `backend/nobla/db/repositories/audit_repo.py`
- Modify: `backend/nobla/db/repositories/__init__.py`
- Create: `backend/tests/test_audit.py`

- [ ] **Step 1: Write failing audit tests**

Create `backend/tests/test_audit.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_audit.py -v`

- [ ] **Step 3: Implement audit module**

Create `backend/nobla/security/audit.py`:
```python
from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Any
import structlog

logger = structlog.get_logger()

SENSITIVE_KEYS = {"passphrase", "password", "token", "secret", "api_key"}


@dataclass
class AuditEntry:
    user_id: str | None
    action: str
    method: str
    tier: int
    status: str
    latency_ms: int | None = None
    ip_address: str | None = None
    metadata: dict = field(default_factory=dict)


def sanitize_params(params: dict, max_content_length: int = 500) -> dict:
    """Remove sensitive fields and truncate long values."""
    if not isinstance(params, dict):
        return params
    result = {}
    for key, value in params.items():
        if key.lower() in SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_params(value, max_content_length)
        elif isinstance(value, str) and len(value) > max_content_length:
            result[key] = value[:max_content_length] + "..."
        else:
            result[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
    return result
```

- [ ] **Step 4: Create AuditLogRepository**

Create `backend/nobla/db/repositories/audit_repo.py`:
```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from nobla.db.models.audit import AuditLog
from nobla.security.audit import AuditEntry


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, entry: AuditEntry) -> AuditLog:
        record = AuditLog(
            user_id=entry.user_id,
            action=entry.action,
            method=entry.method,
            tier=entry.tier,
            status=entry.status,
            ip_address=entry.ip_address,
            latency_ms=entry.latency_ms,
            metadata_=entry.metadata,
        )
        self.session.add(record)
        await self.session.flush()
        return record
```

Update `backend/nobla/db/repositories/__init__.py` to add:
```python
from nobla.db.repositories.audit_repo import AuditLogRepository
```
Add `"AuditLogRepository"` to `__all__`.

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_audit.py -v`
Expected: All 4 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/security/audit.py backend/nobla/db/repositories/audit_repo.py backend/nobla/db/repositories/__init__.py backend/tests/test_audit.py
git commit -m "feat: add audit logging with param sanitization"
```

---

## Task 5: Kill Switch

**Files:**
- Create: `backend/nobla/security/killswitch.py`
- Create: `backend/tests/test_killswitch.py`

- [ ] **Step 1: Write failing kill switch tests**

Create `backend/tests/test_killswitch.py`:
```python
import pytest
import asyncio
from nobla.security.killswitch import KillSwitch, KillState


@pytest.fixture
def ks():
    return KillSwitch()


def test_initial_state(ks):
    assert ks.state == KillState.RUNNING


@pytest.mark.asyncio
async def test_soft_kill(ks):
    await ks.soft_kill()
    assert ks.state == KillState.SOFT_KILLING


@pytest.mark.asyncio
async def test_hard_kill(ks):
    await ks.hard_kill()
    assert ks.state == KillState.KILLED


@pytest.mark.asyncio
async def test_resume(ks):
    await ks.hard_kill()
    assert ks.state == KillState.KILLED
    await ks.resume()
    assert ks.state == KillState.RUNNING


def test_is_accepting_requests(ks):
    assert ks.is_accepting_requests is True


@pytest.mark.asyncio
async def test_killed_not_accepting(ks):
    await ks.hard_kill()
    assert ks.is_accepting_requests is False


@pytest.mark.asyncio
async def test_double_kill_triggers_hard(ks):
    await ks.soft_kill()
    assert ks.state == KillState.SOFT_KILLING
    await ks.soft_kill()  # second call during soft = hard kill
    assert ks.state == KillState.KILLED
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_killswitch.py -v`

- [ ] **Step 3: Implement KillSwitch**

Create `backend/nobla/security/killswitch.py`:
```python
from __future__ import annotations
import asyncio
import enum
import structlog

logger = structlog.get_logger()


class KillState(enum.Enum):
    RUNNING = "running"
    SOFT_KILLING = "soft_killing"
    KILLED = "killed"


class KillSwitch:
    def __init__(self, grace_period: float = 5.0):
        self.state = KillState.RUNNING
        self.grace_period = grace_period
        self._hard_kill_task: asyncio.Task | None = None
        self._on_soft_kill_callbacks: list[callable] = []
        self._on_hard_kill_callbacks: list[callable] = []

    @property
    def is_accepting_requests(self) -> bool:
        return self.state == KillState.RUNNING

    def on_soft_kill(self, callback: callable) -> None:
        self._on_soft_kill_callbacks.append(callback)

    def on_hard_kill(self, callback: callable) -> None:
        self._on_hard_kill_callbacks.append(callback)

    async def soft_kill(self) -> None:
        if self.state == KillState.SOFT_KILLING:
            await self.hard_kill()
            return
        if self.state == KillState.KILLED:
            return

        logger.warning("kill_switch_soft", state="soft_killing")
        self.state = KillState.SOFT_KILLING

        for cb in self._on_soft_kill_callbacks:
            try:
                await cb() if asyncio.iscoroutinefunction(cb) else cb()
            except Exception as e:
                logger.error("soft_kill_callback_error", error=str(e))

        self._hard_kill_task = asyncio.create_task(self._delayed_hard_kill())

    async def hard_kill(self) -> None:
        if self._hard_kill_task and not self._hard_kill_task.done():
            self._hard_kill_task.cancel()

        logger.warning("kill_switch_hard", state="killed")
        self.state = KillState.KILLED

        for cb in self._on_hard_kill_callbacks:
            try:
                await cb() if asyncio.iscoroutinefunction(cb) else cb()
            except Exception as e:
                logger.error("hard_kill_callback_error", error=str(e))

    async def resume(self) -> None:
        logger.info("kill_switch_resume", state="running")
        self.state = KillState.RUNNING

    async def _delayed_hard_kill(self) -> None:
        try:
            await asyncio.sleep(self.grace_period)
            if self.state == KillState.SOFT_KILLING:
                await self.hard_kill()
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_killswitch.py -v`
Expected: All 7 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/security/killswitch.py backend/tests/test_killswitch.py
git commit -m "feat: add two-stage kill switch (soft → hard)"
```

---

## Task 6: Cost Controls

**Files:**
- Create: `backend/nobla/security/costs.py`
- Create: `backend/tests/test_costs.py`

- [ ] **Step 1: Write failing cost tests**

Create `backend/tests/test_costs.py`:
```python
import pytest
from nobla.security.costs import CostTracker, BudgetExceeded


@pytest.fixture
def tracker():
    return CostTracker(daily_limit=5.0, monthly_limit=50.0, session_limit=1.0, warning_threshold=0.8)


def test_initial_spend(tracker):
    assert tracker.session_spend == 0.0


def test_record_spend(tracker):
    tracker.record(0.50)
    assert tracker.session_spend == 0.50


def test_session_limit_exceeded(tracker):
    tracker.record(0.90)
    with pytest.raises(BudgetExceeded, match="session"):
        tracker.check_budget(estimated_cost=0.20)


def test_session_limit_exact(tracker):
    tracker.record(0.80)
    tracker.check_budget(estimated_cost=0.20)  # exactly at limit, should pass


def test_warning_at_threshold(tracker):
    tracker.record(0.80)  # 80% of 1.0
    warnings = tracker.get_warnings()
    assert any("session" in w for w in warnings)


def test_no_warning_below_threshold(tracker):
    tracker.record(0.50)
    warnings = tracker.get_warnings()
    assert len(warnings) == 0


def test_get_dashboard(tracker):
    tracker.record(0.42)
    data = tracker.get_dashboard()
    assert data["session_usd"] == 0.42
    assert data["limits"]["session"] == 1.0


def test_set_daily_spend(tracker):
    tracker.set_daily_spend(4.50)
    with pytest.raises(BudgetExceeded, match="daily"):
        tracker.check_budget(estimated_cost=0.60)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_costs.py -v`

- [ ] **Step 3: Implement CostTracker**

Create `backend/nobla/security/costs.py`:
```python
from __future__ import annotations
import structlog

logger = structlog.get_logger()


class BudgetExceeded(Exception):
    def __init__(self, period: str, limit: float, spent: float):
        self.period = period
        self.limit = limit
        self.spent = spent
        super().__init__(f"{period.capitalize()} budget exceeded: ${spent:.2f} / ${limit:.2f}")


class CostTracker:
    def __init__(self, daily_limit: float = 5.0, monthly_limit: float = 50.0,
                 session_limit: float = 1.0, warning_threshold: float = 0.8):
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.session_limit = session_limit
        self.warning_threshold = warning_threshold
        self.session_spend: float = 0.0
        self._daily_spend: float = 0.0
        self._monthly_spend: float = 0.0

    def record(self, cost_usd: float) -> None:
        self.session_spend += cost_usd
        self._daily_spend += cost_usd
        self._monthly_spend += cost_usd

    def set_daily_spend(self, amount: float) -> None:
        self._daily_spend = amount

    def set_monthly_spend(self, amount: float) -> None:
        self._monthly_spend = amount

    def check_budget(self, estimated_cost: float = 0.0) -> None:
        checks = [
            ("session", self.session_spend + estimated_cost, self.session_limit),
            ("daily", self._daily_spend + estimated_cost, self.daily_limit),
            ("monthly", self._monthly_spend + estimated_cost, self.monthly_limit),
        ]
        for period, projected, limit in checks:
            if projected > limit:
                raise BudgetExceeded(period, limit, projected)

    def get_warnings(self) -> list[str]:
        warnings = []
        checks = [
            ("session", self.session_spend, self.session_limit),
            ("daily", self._daily_spend, self.daily_limit),
            ("monthly", self._monthly_spend, self.monthly_limit),
        ]
        for period, spent, limit in checks:
            if limit > 0 and spent >= self.warning_threshold * limit:
                warnings.append(f"{period}: ${spent:.2f} / ${limit:.2f} ({spent/limit*100:.0f}%)")
        return warnings

    def get_dashboard(self) -> dict:
        return {
            "session_usd": self.session_spend,
            "daily_usd": self._daily_spend,
            "monthly_usd": self._monthly_spend,
            "limits": {
                "session": self.session_limit,
                "daily": self.daily_limit,
                "monthly": self.monthly_limit,
            },
            "warnings": self.get_warnings(),
        }
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_costs.py -v`
Expected: All 8 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/security/costs.py backend/tests/test_costs.py
git commit -m "feat: add cost controls with budget tracking and auto-shutoff"
```

---

## Task 7: Docker Sandbox

**Files:**
- Create: `backend/nobla/security/sandbox.py`
- Create: `backend/tests/test_sandbox.py`

- [ ] **Step 1: Write sandbox tests (unit, no Docker required)**

Create `backend/tests/test_sandbox.py`:
```python
import pytest
from nobla.security.sandbox import SandboxConfig, SandboxResult, SandboxManager


def test_sandbox_config_defaults():
    cfg = SandboxConfig()
    assert cfg.runtime == "docker"
    assert cfg.memory_limit == "256m"
    assert cfg.timeout_seconds == 30
    assert cfg.network_enabled is False


def test_sandbox_result_success():
    result = SandboxResult(stdout="hello\n", stderr="", exit_code=0, execution_time_ms=150, timed_out=False)
    assert result.exit_code == 0
    assert result.timed_out is False


def test_sandbox_result_timeout():
    result = SandboxResult(stdout="", stderr="", exit_code=-1, execution_time_ms=30000, timed_out=True)
    assert result.timed_out is True


def test_sandbox_manager_creation():
    cfg = SandboxConfig()
    mgr = SandboxManager(cfg)
    assert mgr.config.runtime == "docker"


def test_sandbox_validate_language():
    cfg = SandboxConfig()
    mgr = SandboxManager(cfg)
    assert mgr.get_image("python") == "python:3.12-slim"
    assert mgr.get_image("unknown") is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`

- [ ] **Step 3: Implement SandboxManager**

Create `backend/nobla/security/sandbox.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

LANGUAGE_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
    "bash": "bash:5",
}


class SandboxConfig(BaseModel):
    runtime: str = "docker"
    memory_limit: str = "256m"
    cpu_limit: float = 1.0
    timeout_seconds: int = 30
    network_enabled: bool = False
    allowed_images: list[str] = ["python:3.12-slim", "node:20-slim", "bash:5"]


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    timed_out: bool


class SandboxManager:
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._client = None

    def get_image(self, language: str) -> str | None:
        image = LANGUAGE_IMAGES.get(language)
        if image and image in self.config.allowed_images:
            return image
        return None

    async def execute(self, code: str, language: str = "python", timeout: int | None = None) -> SandboxResult:
        """Execute code in a Docker container. Requires Docker daemon running."""
        import time
        image = self.get_image(language)
        if not image:
            return SandboxResult(stdout="", stderr=f"Unsupported language: {language}", exit_code=1, execution_time_ms=0, timed_out=False)

        timeout = timeout or self.config.timeout_seconds

        try:
            import docker
            if not self._client:
                self._client = docker.from_env()

            start = time.monotonic()
            container = self._client.containers.run(
                image=image,
                command=self._build_command(code, language),
                detach=True,
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                network_mode="none" if not self.config.network_enabled else "bridge",
                runtime="runsc" if self.config.runtime == "gvisor" else None,
                read_only=True,
                tmpfs={"/tmp": "size=64m"},
            )

            try:
                result = container.wait(timeout=timeout)
                elapsed = int((time.monotonic() - start) * 1000)
                logs = container.logs(stdout=True, stderr=True).decode()
                stdout = container.logs(stdout=True, stderr=False).decode()
                stderr = container.logs(stdout=False, stderr=True).decode()
                return SandboxResult(
                    stdout=stdout, stderr=stderr,
                    exit_code=result.get("StatusCode", -1),
                    execution_time_ms=elapsed, timed_out=False,
                )
            except Exception:
                elapsed = int((time.monotonic() - start) * 1000)
                container.kill()
                return SandboxResult(stdout="", stderr="Execution timed out", exit_code=-1, execution_time_ms=elapsed, timed_out=True)
            finally:
                container.remove(force=True)

        except ImportError:
            return SandboxResult(stdout="", stderr="Docker SDK not available", exit_code=1, execution_time_ms=0, timed_out=False)
        except Exception as e:
            logger.error("sandbox_error", error=str(e))
            return SandboxResult(stdout="", stderr=str(e), exit_code=1, execution_time_ms=0, timed_out=False)

    def _build_command(self, code: str, language: str) -> list[str]:
        if language == "python":
            return ["python", "-c", code]
        elif language == "javascript":
            return ["node", "-e", code]
        elif language == "bash":
            return ["bash", "-c", code]
        return ["echo", "unsupported"]

    async def kill_all(self) -> None:
        """Kill all running sandbox containers. Used by kill switch."""
        try:
            import docker
            if not self._client:
                self._client = docker.from_env()
            containers = self._client.containers.list(filters={"ancestor": list(LANGUAGE_IMAGES.values())})
            for c in containers:
                try:
                    c.kill()
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error("kill_all_error", error=str(e))

    async def cleanup(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "feat: add Docker sandbox with resource limits and gVisor-ready config"
```

---

## Task 8: Wire Security into WebSocket Handler

**Files:**
- Modify: `backend/nobla/gateway/websocket.py`
- Modify: `backend/nobla/gateway/app.py`
- Create: `backend/nobla/security/__init__.py` (re-exports)
- Create: `backend/tests/test_security_integration.py`

This is the integration task — connecting auth, permissions, audit, kill switch, and costs into the existing WebSocket handler and app lifespan.

- [ ] **Step 1: Write integration tests**

Create `backend/tests/test_security_integration.py`:
```python
from unittest.mock import patch, AsyncMock
from starlette.testclient import TestClient
from nobla.gateway.app import create_app


def _app():
    return create_app()


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


def test_system_kill_changes_state():
    """system.kill should trigger kill switch."""
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"jsonrpc": "2.0", "method": "system.kill", "id": 1})
        data = ws.receive_json()
        assert data["result"]["state"] in ["soft_killing", "killed"]
```

- [ ] **Step 2: Update security __init__.py**

```python
from nobla.security.auth import AuthService
from nobla.security.permissions import Tier, PermissionChecker, InsufficientPermissions
from nobla.security.audit import AuditEntry, sanitize_params
from nobla.security.killswitch import KillSwitch, KillState
from nobla.security.costs import CostTracker, BudgetExceeded
from nobla.security.sandbox import SandboxManager, SandboxConfig, SandboxResult

__all__ = [
    "AuthService", "Tier", "PermissionChecker", "InsufficientPermissions",
    "AuditEntry", "sanitize_params", "KillSwitch", "KillState",
    "CostTracker", "BudgetExceeded", "SandboxManager", "SandboxConfig", "SandboxResult",
]
```

- [ ] **Step 3: Update websocket.py — add auth check, kill check, new handlers**

Key changes to `backend/nobla/gateway/websocket.py`:
- Add module-level references: `_auth_service`, `_kill_switch`, `_cost_tracker`, `_permission_checker` with getters/setters
- Add `AUTH_REQUIRED = -32011`, `AUTH_FAILED = -32012`, `SERVER_KILLED = -32030`, `PERMISSION_DENIED = -32010`, `BUDGET_EXCEEDED = -32020` error codes
- Define `NO_AUTH_METHODS = {"system.health", "system.authenticate", "system.register"}`
- In `handle_message`: before dispatching, check:
  1. Kill switch state (reject with -32030 if killed, except system.health/resume)
  2. Auth (reject with -32011 if not authenticated and method not in NO_AUTH_METHODS)
- Add `ConnectionState.tier` field (default: Tier.SAFE)
- Add new handlers: `system.register`, `system.refresh`, `system.escalate`, `system.kill`, `system.resume`, `system.costs`, `code.execute`
- Update `system.authenticate` to actually validate passphrase via AuthService

- [ ] **Step 4: Update app.py lifespan — init security services**

Add to lifespan in `backend/nobla/gateway/app.py`:
```python
from nobla.security import AuthService, KillSwitch, CostTracker, PermissionChecker, SandboxConfig, SandboxManager

# Init security services
auth_service = AuthService(
    secret_key=settings.secret_key,
    access_expire_minutes=settings.auth.access_token_expire_minutes,
    refresh_expire_days=settings.auth.refresh_token_expire_days,
    bcrypt_rounds=settings.auth.bcrypt_rounds,
)
kill_switch = KillSwitch()
cost_tracker = CostTracker(
    daily_limit=settings.costs.daily_limit_usd,
    monthly_limit=settings.costs.monthly_limit_usd,
    session_limit=settings.costs.per_session_limit_usd,
    warning_threshold=settings.costs.warning_threshold,
)
permission_checker = PermissionChecker(
    escalation_requires_passphrase=settings.security.escalation_requires_passphrase,
)
sandbox_mgr = SandboxManager(SandboxConfig(**settings.sandbox.model_dump()))

# Set on websocket module
set_auth_service(auth_service)
set_kill_switch(kill_switch)
set_cost_tracker(cost_tracker)
set_permission_checker(permission_checker)
set_sandbox_manager(sandbox_mgr)
```

Add REST kill endpoint:
```python
from fastapi import Request

@rest_router.post("/api/kill")
async def emergency_kill(request: Request):
    # Localhost only
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "::1", "localhost"):
        return {"error": "Localhost only"}
    from nobla.gateway.websocket import get_kill_switch
    ks = get_kill_switch()
    if ks:
        await ks.soft_kill()
    return {"state": ks.state.value if ks else "unknown"}
```

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass (existing 32 + new integration tests).

Note: Some existing tests (like test_chat_flow.py) may need updating since chat.send now requires auth. Update those tests to either:
- Mock the auth check, OR
- Set ConnectionState with a user_id before calling chat.send

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/gateway/ backend/nobla/security/__init__.py backend/tests/test_security_integration.py
git commit -m "feat: wire security into WebSocket handler and app lifespan

- Auth required for all methods except health/authenticate/register
- Kill switch accessible via RPC and REST endpoint
- Permission tier check before handler dispatch
- Cost tracker initialized from config
- Sandbox manager initialized from config"
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | Dependencies + Structure | 5 files | 0 (verify only) |
| 2 | Auth (JWT + passphrase) | 2 files | 7 |
| 3 | Permissions (4-tier) | 2 files | 6 |
| 4 | Audit Logging | 4 files | 4 |
| 5 | Kill Switch | 2 files | 7 |
| 6 | Cost Controls | 2 files | 8 |
| 7 | Docker Sandbox | 2 files | 5 |
| 8 | Security Wiring | 4+ files | 3+ |
| **Total** | | **~23 files** | **40+ new tests** |

**Acceptance criteria from spec:**
1. Register + JWT auth ✓ (Task 2)
2. WebSocket methods require auth ✓ (Task 8)
3. Permission tiers enforced ✓ (Task 3 + 8)
4. TIER 3+ escalation needs passphrase ✓ (Task 3)
5. Docker sandbox execution ✓ (Task 7)
6. Sandbox network isolation ✓ (Task 7)
7. All RPC calls audit logged ✓ (Task 4 + 8)
8. Soft kill stops tasks ✓ (Task 5)
9. Hard kill terminates everything ✓ (Task 5)
10. Cost controls block overspend ✓ (Task 6)
11. system.costs dashboard data ✓ (Task 6 + 8)
12. 90%+ coverage on security/ ✓ (40+ tests)
13. All files under 750 lines ✓ (enforced by structure)
