# Phase 1D: End-to-End Integration & Deployment — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the full stack with Docker Compose, add integration tests exercising the real WebSocket API, and set up GitHub Actions CI for automated quality gates.

**Architecture:** Docker Compose orchestrates backend + PostgreSQL + Redis. Integration tests connect via real WebSocket. GitHub Actions runs backend tests, Flutter tests, and integration tests.

**Tech Stack:** Docker, Docker Compose, pytest-asyncio, websockets (Python client), GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-17-phase1c-flutter-app-design.md` (Phase 1D section)

---

## File Structure

```
backend/
├── Dockerfile
docker-compose.yml
.env.example
tests/
└── integration/
    ├── conftest.py
    ├── test_auth_flow.py
    ├── test_chat_flow.py
    ├── test_security_flow.py
    └── test_concurrent.py
.github/
└── workflows/
    └── ci.yml
```

---

### Task 1: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

Create `backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
COPY nobla/ ./nobla/
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY nobla/ ./nobla/
RUN useradd -r nobla
USER nobla
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "nobla.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify Dockerfile builds**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent/backend" && docker build -t nobla-backend .
```

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: add backend Dockerfile with multi-stage build"
```

---

### Task 2: Docker Compose & Environment

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create docker-compose.yml**

Create `docker-compose.yml` at project root:
```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://nobla:nobla@postgres:5432/nobla
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=${JWT_SECRET:-dev-secret-change-in-production}
      - DAILY_BUDGET=${DAILY_BUDGET:-5.0}
      - MONTHLY_BUDGET=${MONTHLY_BUDGET:-50.0}
      - SESSION_BUDGET=${SESSION_BUDGET:-1.0}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: nobla
      POSTGRES_PASSWORD: nobla
      POSTGRES_DB: nobla
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nobla"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

- [ ] **Step 2: Create .env.example**

Create `.env.example` at project root:
```bash
# Nobla Agent Configuration
# Copy to .env and modify as needed

# Security
JWT_SECRET=change-this-to-a-random-secret

# Database (only needed if not using Docker Compose defaults)
# DATABASE_URL=postgresql+asyncpg://nobla:nobla@localhost:5432/nobla
# REDIS_URL=redis://localhost:6379/0

# Budget limits (USD)
DAILY_BUDGET=5.0
MONTHLY_BUDGET=50.0
SESSION_BUDGET=1.0

# LLM Providers (set API keys for providers you want to use)
# GEMINI_API_KEY=your-key-here
# GROQ_API_KEY=your-key-here
# OLLAMA_URL=http://localhost:11434

# Default provider: gemini, ollama, or groq
# DEFAULT_LLM_PROVIDER=gemini
```

- [ ] **Step 3: Verify Docker Compose starts**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent" && docker compose up -d && docker compose ps
```

Wait for health checks, then:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

Then shut down:
```bash
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add Docker Compose for full stack (backend + postgres + redis)"
```

---

### Task 3: Integration Test Infrastructure

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`

- [ ] **Step 1: Add websockets to dev dependencies**

Add `websockets` to `backend/pyproject.toml` dev dependencies for the integration test client:

In the `[project.optional-dependencies]` dev section, add: `"websockets>=12.0"`

- [ ] **Step 2: Create conftest with WebSocket helper**

Create `tests/integration/__init__.py` (empty file).

Create `tests/integration/conftest.py`:
```python
from __future__ import annotations

import asyncio
import json
import os
import pytest
import websockets


BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws")


class RpcClient:
    """Simple JSON-RPC 2.0 WebSocket client for integration tests."""

    def __init__(self, ws):
        self._ws = ws
        self._next_id = 1

    async def call(self, method: str, params: dict | None = None) -> dict:
        req_id = self._next_id
        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id,
        }
        await self._ws.send(json.dumps(request))
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        response = json.loads(raw)
        return response

    async def call_expect_result(self, method: str, params: dict | None = None) -> dict:
        resp = await self.call(method, params)
        assert "result" in resp, f"Expected result, got: {resp}"
        return resp["result"]

    async def call_expect_error(self, method: str, params: dict | None = None) -> dict:
        resp = await self.call(method, params)
        assert "error" in resp, f"Expected error, got: {resp}"
        return resp["error"]


@pytest.fixture
async def ws_client():
    """Provides a connected WebSocket RPC client."""
    async with websockets.connect(BACKEND_WS_URL) as ws:
        yield RpcClient(ws)


@pytest.fixture
async def authenticated_client(ws_client: RpcClient):
    """Provides an authenticated WebSocket RPC client."""
    result = await ws_client.call_expect_result("system.register", {
        "passphrase": "integration-test-passphrase-12345",
        "display_name": "Integration Test User",
    })
    assert "user_id" in result
    assert "access_token" in result
    return ws_client
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/ backend/pyproject.toml
git commit -m "feat: add integration test infrastructure with WebSocket RPC client"
```

---

### Task 4: Auth Flow Integration Tests

**Files:**
- Create: `tests/integration/test_auth_flow.py`

- [ ] **Step 1: Write auth integration tests**

Create `tests/integration/test_auth_flow.py`:
```python
from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestAuthFlow:
    async def test_register_returns_tokens(self, ws_client: RpcClient):
        result = await ws_client.call_expect_result("system.register", {
            "passphrase": "test-passphrase-12345678",
            "display_name": "Test User",
        })
        assert "user_id" in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["display_name"] == "Test User"

    async def test_register_rejects_short_passphrase(self, ws_client: RpcClient):
        result = await ws_client.call_expect_result("system.register", {
            "passphrase": "short",
            "display_name": "Test User",
        })
        assert "error" in result or "min_length" in result

    async def test_authenticate_with_token(self, authenticated_client: RpcClient):
        """Auth already done in fixture — verify we can call authenticated methods."""
        result = await authenticated_client.call_expect_result("system.status")
        assert result["version"] == "0.1.0"

    async def test_unauthenticated_chat_rejected(self, ws_client: RpcClient):
        """Without auth, chat.send should return AUTH_REQUIRED error."""
        error = await ws_client.call_expect_error("chat.send", {
            "message": "hello",
        })
        assert error["code"] == -32011  # AUTH_REQUIRED

    async def test_unauthenticated_surface(self, ws_client: RpcClient):
        """system.health, system.register, system.authenticate should work without auth."""
        health = await ws_client.call_expect_result("system.health")
        assert "status" in health

    async def test_token_refresh(self, ws_client: RpcClient):
        reg = await ws_client.call_expect_result("system.register", {
            "passphrase": "test-passphrase-refresh",
            "display_name": "Refresh Test",
        })
        refresh_result = await ws_client.call_expect_result("system.refresh", {
            "refresh_token": reg["refresh_token"],
        })
        assert "access_token" in refresh_result
        assert "refresh_token" in refresh_result
```

- [ ] **Step 2: Run tests (requires running backend)**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent"
docker compose up -d
sleep 5
pytest tests/integration/test_auth_flow.py -m integration -v
docker compose down
```
Expected: ALL PASS (or skip if backend not running)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_auth_flow.py
git commit -m "test: add auth flow integration tests"
```

---

### Task 5: Chat & Security Integration Tests

**Files:**
- Create: `tests/integration/test_chat_flow.py`
- Create: `tests/integration/test_security_flow.py`

- [ ] **Step 1: Write chat flow integration tests**

Create `tests/integration/test_chat_flow.py`:
```python
from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestChatFlow:
    async def test_send_message_returns_response(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "What is 2 + 2?",
        })
        assert "message" in result
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    async def test_response_includes_metadata(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "Say hello",
        })
        assert "model" in result
        assert "tokens_used" in result
        assert "cost_usd" in result

    async def test_chat_with_conversation_id(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("chat.send", {
            "message": "Hello",
            "conversation_id": "test-conv-123",
        })
        assert result.get("conversation_id") == "test-conv-123" or "message" in result
```

- [ ] **Step 2: Write security flow integration tests**

Create `tests/integration/test_security_flow.py`:
```python
from __future__ import annotations

import pytest
from tests.integration.conftest import RpcClient


@pytest.mark.integration
class TestSecurityFlow:
    async def test_escalation_to_standard(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("system.escalate", {
            "tier": 2,
        })
        assert result["tier"] == 2

    async def test_de_escalation(self, authenticated_client: RpcClient):
        await authenticated_client.call_expect_result("system.escalate", {"tier": 2})
        result = await authenticated_client.call_expect_result("system.escalate", {"tier": 1})
        assert result["tier"] == 1

    async def test_kill_switch_flow(self, authenticated_client: RpcClient):
        # Kill
        kill_result = await authenticated_client.call_expect_result("system.kill")
        assert kill_result["state"] in ("soft_killing", "killed")

        # Verify requests are rejected during kill
        resp = await authenticated_client.call("chat.send", {"message": "test"})
        assert "error" in resp
        assert resp["error"]["code"] == -32030  # SERVER_KILLED

        # Resume
        resume_result = await authenticated_client.call_expect_result("system.resume")
        assert resume_result["state"] == "running"

        # Verify requests work again
        health = await authenticated_client.call_expect_result("system.health")
        assert health["status"] == "ok"

    async def test_cost_dashboard(self, authenticated_client: RpcClient):
        result = await authenticated_client.call_expect_result("system.costs")
        assert "session_usd" in result
        assert "limits" in result
        assert "warnings" in result
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_chat_flow.py tests/integration/test_security_flow.py
git commit -m "test: add chat and security flow integration tests"
```

---

### Task 6: Concurrent Connection Tests

**Files:**
- Create: `tests/integration/test_concurrent.py`

- [ ] **Step 1: Write concurrent connection tests**

Create `tests/integration/test_concurrent.py`:
```python
from __future__ import annotations

import asyncio
import json
import os
import pytest
import websockets

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws")


async def create_authenticated_client():
    """Create and authenticate a WebSocket connection."""
    ws = await websockets.connect(BACKEND_WS_URL)
    register_req = {
        "jsonrpc": "2.0",
        "method": "system.register",
        "params": {
            "passphrase": f"concurrent-test-{id(ws)}",
            "display_name": "Concurrent User",
        },
        "id": 1,
    }
    await ws.send(json.dumps(register_req))
    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    assert "result" in resp
    return ws


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrentConnections:
    async def test_multiple_clients_simultaneous(self):
        clients = await asyncio.gather(*[
            create_authenticated_client() for _ in range(3)
        ])
        try:
            # All clients send health check simultaneously
            for i, ws in enumerate(clients):
                req = {"jsonrpc": "2.0", "method": "system.health", "id": 100 + i}
                await ws.send(json.dumps(req))

            # All should get responses
            for ws in clients:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                resp = json.loads(raw)
                assert "result" in resp
                assert resp["result"]["status"] == "ok"
        finally:
            for ws in clients:
                await ws.close()
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_concurrent.py
git commit -m "test: add concurrent WebSocket connection integration tests"
```

---

### Task 7: GitHub Actions CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

Create `.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: backend/pyproject.toml

      - name: Install dependencies
        working-directory: backend
        run: pip install -e ".[dev]"

      - name: Lint
        working-directory: backend
        run: ruff check nobla/

      - name: Unit tests
        run: pytest tests/ -v --cov=nobla --ignore=tests/integration -x

  flutter:
    name: Flutter Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Flutter
        uses: subosito/flutter-action@v2
        with:
          channel: stable
          cache: true

      - name: Install dependencies
        working-directory: app
        run: flutter pub get

      - name: Analyze
        working-directory: app
        run: flutter analyze

      - name: Test
        working-directory: app
        run: flutter test --coverage

      - name: Build web
        working-directory: app
        run: flutter build web

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: [backend]
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: nobla
          POSTGRES_PASSWORD: nobla
          POSTGRES_DB: nobla
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready -U nobla"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ['6379:6379']
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: backend/pyproject.toml

      - name: Install dependencies
        working-directory: backend
        run: pip install -e ".[dev]"

      - name: Start backend
        run: |
          cd backend
          uvicorn nobla.main:app --host 0.0.0.0 --port 8000 &
          sleep 5
          curl -f http://localhost:8000/health
        env:
          DATABASE_URL: postgresql+asyncpg://nobla:nobla@localhost:5432/nobla
          REDIS_URL: redis://localhost:6379/0
          JWT_SECRET: ci-test-secret

      - name: Run integration tests
        run: pytest tests/integration/ -m integration -v
        env:
          BACKEND_WS_URL: ws://localhost:8000/ws
```

- [ ] **Step 2: Create directory and commit**

```bash
mkdir -p ".github/workflows"
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for backend, Flutter, and integration tests"
```

---

### Task 8: Update Backend Routes for Phase 1C

**Files:**
- Modify: `backend/nobla/gateway/routes.py`

The backend's REST `/status` endpoint still says `"phase": "1A"`. Update it to reflect completion through 1D.

- [ ] **Step 1: Update status endpoint**

In `backend/nobla/gateway/routes.py`, change `"phase": "1A"` to `"phase": "1D"`.

- [ ] **Step 2: Run backend tests to verify no breakage**

```bash
cd "C:/Users/saeee/Downloads/Nobla Agent" && pytest tests/ --ignore=tests/integration -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/nobla/gateway/routes.py
git commit -m "chore: update phase marker to 1D"
```

---

## Summary

| Task | Description | Tests |
|------|------------|-------|
| 1 | Backend Dockerfile | Docker build verification |
| 2 | Docker Compose + .env.example | Stack health check |
| 3 | Integration test infrastructure | conftest + fixtures |
| 4 | Auth flow integration tests | 6 tests |
| 5 | Chat & security integration tests | 7 tests |
| 6 | Concurrent connection tests | 1 test |
| 7 | GitHub Actions CI workflow | CI pipeline |
| 8 | Update phase marker | Backend test verification |

**Total: 8 tasks, ~14 integration tests, 8 commits**

## Acceptance Criteria

- [ ] `docker compose up` starts all services and backend responds to health check
- [ ] All integration tests pass against running backend
- [ ] GitHub Actions CI workflow defined with 3 jobs (backend, flutter, integration)
- [ ] `.env.example` documents all environment variables
- [ ] Backend Dockerfile builds successfully with multi-stage build
- [ ] Phase marker updated to 1D
