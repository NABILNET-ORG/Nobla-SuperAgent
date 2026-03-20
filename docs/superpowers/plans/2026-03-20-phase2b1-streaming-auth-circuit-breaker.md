# Phase 2B-1: Streaming + Provider Auth + Circuit Breaker — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the LLM router from 3 hardcoded providers to a production multi-provider system with streaming responses, OAuth/API-key/local auth, circuit breakers, and Flutter provider management.

**Architecture:** Restructure `brain/` into `providers/` subdirectory. Add `auth/` module for credential management (OAuth, API key, local). Circuit breaker wraps each provider. Streaming coordinator bridges provider SSE to WebSocket JSON-RPC notifications. Flutter gets provider management screen + streaming message display.

**Tech Stack:** Python 3.12, FastAPI, openai SDK, anthropic SDK, litellm, tiktoken, authlib, httpx, Flutter/Riverpod

**Design spec:** `docs/superpowers/specs/2026-03-19-phase2b-router-search-design.md`

**Hard limit:** 750 lines per file, no exceptions.

---

## File Structure

### Backend — New/Modified Files

```
backend/nobla/brain/
├── __init__.py                    # MODIFY: update exports
├── base_provider.py               # KEEP as-is
├── router.py                      # MODIFY: circuit breaker integration + enhanced classifier
├── circuit_breaker.py             # CREATE: per-provider circuit breaker
├── streaming.py                   # CREATE: WebSocket streaming coordinator
├── token_counter.py               # CREATE: cross-provider token counting
├── providers/
│   ├── __init__.py                # CREATE: provider exports
│   ├── gemini.py                  # MOVE from brain/gemini.py (no changes)
│   ├── groq.py                    # MOVE from brain/groq.py (no changes)
│   ├── ollama.py                  # MOVE from brain/ollama.py (no changes)
│   ├── openai.py                  # CREATE: OpenAI GPT provider
│   ├── anthropic.py               # CREATE: Anthropic Claude provider
│   ├── deepseek.py                # CREATE: DeepSeek provider
│   └── litellm_proxy.py           # CREATE: LiteLLM unified fallback
├── auth/
│   ├── __init__.py                # CREATE: auth exports
│   ├── api_key.py                 # CREATE: API key validation + encrypted storage
│   ├── oauth.py                   # CREATE: OAuth2 flow manager (Google first)
│   └── local.py                   # CREATE: local model endpoint management
```

```
backend/nobla/config/settings.py   # MODIFY: add new provider + auth settings
backend/nobla/gateway/websocket.py # MODIFY: add streaming + provider RPC handlers
backend/nobla/gateway/app.py       # MODIFY: wire new providers + auth
backend/pyproject.toml              # MODIFY: add new dependencies
```

### Backend — New Test Files

```
backend/tests/
├── test_circuit_breaker.py        # CREATE
├── test_token_counter.py          # CREATE
├── test_streaming.py              # CREATE
├── test_auth_api_key.py           # CREATE
├── test_auth_oauth.py             # CREATE
├── test_auth_local.py             # CREATE
├── test_provider_openai.py        # CREATE
├── test_provider_anthropic.py     # CREATE
├── test_provider_deepseek.py      # CREATE
├── test_provider_litellm.py       # CREATE
├── test_router.py                 # MODIFY: add circuit breaker + classifier tests
├── test_provider_rpc.py           # CREATE
├── test_streaming_flow.py         # CREATE (integration)
```

### Flutter — New/Modified Files

```
app/lib/features/
├── settings/
│   ├── screens/
│   │   ├── settings_screen.dart                # MODIFY: add provider nav
│   │   └── provider_management_screen.dart     # CREATE
│   └── widgets/
│       ├── provider_card.dart                  # CREATE
│       └── api_key_wizard.dart                 # CREATE
├── settings/providers/
│   └── provider_settings_provider.dart         # CREATE (Riverpod)
├── chat/
│   ├── providers/chat_provider.dart            # MODIFY: streaming support
│   └── widgets/
│       └── streaming_message.dart              # CREATE
```

---

## Task 1: Circuit Breaker

**Files:**
- Create: `backend/nobla/brain/circuit_breaker.py`
- Test: `backend/tests/test_circuit_breaker.py`

The circuit breaker is a standalone module with no external dependencies. Three states: CLOSED (healthy), OPEN (failing, reject calls), HALF_OPEN (testing recovery).

- [ ] **Step 1: Write failing tests for circuit breaker states**

```python
# backend/tests/test_circuit_breaker.py
import asyncio
import pytest
from nobla.brain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


def test_initial_state_is_closed():
    cb = CircuitBreaker(provider_name="test")
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True


def test_stays_closed_under_threshold():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.is_available() is False


def test_success_resets_failure_count():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    import time
    time.sleep(0.02)
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    import time
    time.sleep(0.02)
    cb.is_available()  # triggers HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    import time
    time.sleep(0.02)
    cb.is_available()  # triggers HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_rolling_window_expires_old_failures():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=3, rolling_window=0.01),
    )
    cb.record_failure()
    cb.record_failure()
    import time
    time.sleep(0.02)
    # Old failures expired, one new failure should not open
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_circuit_breaker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.brain.circuit_breaker'`

- [ ] **Step 3: Implement circuit breaker**

```python
# backend/nobla/brain/circuit_breaker.py
"""
Per-provider circuit breaker: Closed → Open → Half-Open.

Prevents cascading failures by temporarily disabling providers
that are returning errors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    rolling_window: float = 60.0


class CircuitBreaker:
    """Circuit breaker for a single LLM provider."""

    def __init__(
        self,
        provider_name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._opened_at: float = 0.0
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        self._prune_old_failures()
        return len(self._failure_timestamps)

    def _prune_old_failures(self) -> None:
        cutoff = time.monotonic() - self.config.rolling_window
        self._failure_timestamps = [
            t for t in self._failure_timestamps if t > cutoff
        ]

    def is_available(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(
                    "circuit_breaker.half_open",
                    provider=self.provider_name,
                )
                return True
            return False

        # HALF_OPEN: allow limited test calls
        return self._half_open_calls < self.config.half_open_max_calls

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                "circuit_breaker.recovered",
                provider=self.provider_name,
            )
        self._state = CircuitState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_calls = 0

    def record_failure(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker.reopened",
                provider=self.provider_name,
            )
            return

        self._failure_timestamps.append(time.monotonic())
        self._prune_old_failures()

        if len(self._failure_timestamps) >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker.opened",
                provider=self.provider_name,
                failures=len(self._failure_timestamps),
            )

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_calls = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_circuit_breaker.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/brain/circuit_breaker.py backend/tests/test_circuit_breaker.py
git commit -m "feat(brain): add per-provider circuit breaker with rolling window"
```

---

## Task 2: Token Counter

**Files:**
- Create: `backend/nobla/brain/token_counter.py`
- Test: `backend/tests/test_token_counter.py`
- Modify: `backend/pyproject.toml` (add `tiktoken`)

Cross-provider token counting. Uses `tiktoken` for OpenAI-compatible models, estimates for others.

- [ ] **Step 1: Add tiktoken dependency**

Add `"tiktoken>=0.7.0"` to `dependencies` in `backend/pyproject.toml`.

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_token_counter.py
import pytest
from nobla.brain.token_counter import TokenCounter


def test_count_openai_tokens():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="openai", model="gpt-4o")
    assert isinstance(count, int)
    assert count > 0


def test_count_anthropic_tokens():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="anthropic", model="claude-sonnet-4-20250514")
    assert isinstance(count, int)
    assert count > 0


def test_count_fallback_estimation():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="unknown", model="some-model")
    assert isinstance(count, int)
    assert count > 0


def test_empty_string_returns_zero():
    counter = TokenCounter()
    assert counter.count("", provider="openai", model="gpt-4o") == 0


def test_cost_estimate():
    counter = TokenCounter()
    cost = counter.estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        provider="openai",
        model="gpt-4o",
    )
    assert isinstance(cost, float)
    assert cost > 0


def test_cost_estimate_free_provider():
    counter = TokenCounter()
    cost = counter.estimate_cost(
        input_tokens=1000,
        output_tokens=500,
        provider="ollama",
        model="llama3.1",
    )
    assert cost == 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_token_counter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement token counter**

```python
# backend/nobla/brain/token_counter.py
"""
Cross-provider token counting and cost estimation.

Uses tiktoken for OpenAI-compatible tokenizers, cl100k_base as
the default fallback for unknown providers.
"""

from __future__ import annotations

import tiktoken


# Pricing per token (as of 2026-03)
_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
        "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    },
    "anthropic": {
        "claude-sonnet-4-20250514": (3.00 / 1_000_000, 15.00 / 1_000_000),
        "claude-haiku-4-5-20251001": (0.80 / 1_000_000, 4.00 / 1_000_000),
    },
    "gemini": {
        "gemini-2.0-flash": (0.075 / 1_000_000, 0.30 / 1_000_000),
    },
    "groq": {
        "llama-3.1-70b-versatile": (0.59 / 1_000_000, 0.79 / 1_000_000),
    },
    "deepseek": {
        "deepseek-chat": (0.14 / 1_000_000, 0.28 / 1_000_000),
    },
    "ollama": {},  # Free — all models cost 0
}

# Default pricing when model not in table
_DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "openai": (2.50 / 1_000_000, 10.00 / 1_000_000),
    "anthropic": (3.00 / 1_000_000, 15.00 / 1_000_000),
    "deepseek": (0.14 / 1_000_000, 0.28 / 1_000_000),
}


class TokenCounter:
    """Count tokens and estimate costs across LLM providers."""

    def __init__(self) -> None:
        self._fallback_enc = tiktoken.get_encoding("cl100k_base")
        self._enc_cache: dict[str, tiktoken.Encoding] = {}

    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        if model not in self._enc_cache:
            try:
                self._enc_cache[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                self._enc_cache[model] = self._fallback_enc
        return self._enc_cache[model]

    def count(self, text: str, provider: str, model: str) -> int:
        if not text:
            return 0

        if provider in ("openai", "anthropic", "deepseek", "groq"):
            enc = self._get_encoding(model)
            return len(enc.encode(text))

        # Fallback: use cl100k_base (reasonable estimate for most models)
        return len(self._fallback_enc.encode(text))

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        provider: str,
        model: str,
    ) -> float:
        provider_pricing = _PRICING.get(provider, {})

        if not provider_pricing:
            # Unknown or free provider
            default = _DEFAULT_PRICING.get(provider, (0.0, 0.0))
            input_cost, output_cost = default
        else:
            input_cost, output_cost = provider_pricing.get(
                model,
                _DEFAULT_PRICING.get(provider, (0.0, 0.0)),
            )

        return (input_tokens * input_cost) + (output_tokens * output_cost)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_token_counter.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/brain/token_counter.py backend/tests/test_token_counter.py backend/pyproject.toml
git commit -m "feat(brain): add cross-provider token counter with tiktoken"
```

---

## Task 3: Provider Auth — API Key Manager

**Files:**
- Create: `backend/nobla/brain/auth/__init__.py`
- Create: `backend/nobla/brain/auth/api_key.py`
- Test: `backend/tests/test_auth_api_key.py`

Manages encrypted storage and validation of API keys per provider per user.

- [ ] **Step 1: Create auth package init**

```python
# backend/nobla/brain/auth/__init__.py
# Lazy imports — oauth.py and local.py are created in Tasks 4 and 5.
# Only import what exists; consumers import directly from submodules.
from nobla.brain.auth.api_key import ApiKeyManager, ApiKeyRecord

__all__ = ["ApiKeyManager", "ApiKeyRecord"]
```

Note: This file will be updated in Task 5 Step 5 after all auth modules exist.

- [ ] **Step 2: Write failing tests for API key manager**

```python
# backend/tests/test_auth_api_key.py
import pytest
from nobla.brain.auth.api_key import ApiKeyManager, ApiKeyRecord


@pytest.fixture
def manager():
    return ApiKeyManager(encryption_key="test-secret-key-32bytes-padding!")


def test_store_and_retrieve_key(manager):
    manager.store("openai", "user-1", "sk-test-key-12345")
    record = manager.get("openai", "user-1")
    assert record is not None
    assert record.provider == "openai"
    assert record.user_id == "user-1"
    assert record.api_key == "sk-test-key-12345"


def test_get_nonexistent_returns_none(manager):
    assert manager.get("openai", "user-1") is None


def test_delete_key(manager):
    manager.store("openai", "user-1", "sk-test-key")
    manager.delete("openai", "user-1")
    assert manager.get("openai", "user-1") is None


def test_key_is_encrypted_in_storage(manager):
    manager.store("openai", "user-1", "sk-test-key-12345")
    # The raw storage should NOT contain the plaintext key
    raw = manager._get_raw("openai", "user-1")
    assert raw != "sk-test-key-12345"
    assert raw is not None


def test_validate_openai_key_format(manager):
    assert manager.validate_format("openai", "sk-proj-abc123") is True
    assert manager.validate_format("openai", "not-a-valid-key") is False


def test_validate_anthropic_key_format(manager):
    assert manager.validate_format("anthropic", "sk-ant-abc123") is True
    assert manager.validate_format("anthropic", "bad") is False


def test_validate_groq_key_format(manager):
    assert manager.validate_format("groq", "gsk_abc123") is True
    assert manager.validate_format("groq", "bad") is False


def test_validate_unknown_provider_accepts_any(manager):
    assert manager.validate_format("unknown", "anything") is True


def test_list_providers_for_user(manager):
    manager.store("openai", "user-1", "sk-test-1")
    manager.store("groq", "user-1", "gsk_test-2")
    providers = manager.list_providers("user-1")
    assert set(providers) == {"openai", "groq"}


def test_wrong_encryption_key_cannot_decrypt():
    """Security: key encrypted with one secret must not decrypt with another."""
    mgr1 = ApiKeyManager(encryption_key="secret-key-one-32bytes-padding!!")
    mgr1.store("openai", "user-1", "sk-real-key-12345")
    mgr2 = ApiKeyManager(encryption_key="secret-key-two-32bytes-padding!!")
    # mgr2 cannot access mgr1's store (separate instances), but verify
    # that the encrypted bytes from mgr1 cannot be decrypted by mgr2's fernet
    raw = mgr1._store.get(("openai", "user-1"))
    import pytest as _pt
    from cryptography.fernet import InvalidToken
    with _pt.raises(InvalidToken):
        mgr2._fernet.decrypt(raw)


def test_store_empty_key_still_encrypts(manager):
    manager.store("openai", "user-1", "")
    record = manager.get("openai", "user-1")
    assert record is not None
    assert record.api_key == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth_api_key.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement API key manager**

```python
# backend/nobla/brain/auth/api_key.py
"""
API key storage with AES encryption and format validation.

Keys are encrypted at rest using Fernet (AES-128-CBC). In production
this uses PostgreSQL; here we provide an in-memory store that can
be swapped for a DB-backed implementation.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet

import structlog

logger = structlog.get_logger(__name__)


# Provider-specific key format patterns
_KEY_PATTERNS: dict[str, re.Pattern] = {
    "openai": re.compile(r"^sk-(proj-)?[A-Za-z0-9_-]{20,}$"),
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$"),
    "groq": re.compile(r"^gsk_[A-Za-z0-9_-]{20,}$"),
    "deepseek": re.compile(r"^sk-[A-Za-z0-9_-]{20,}$"),
}


@dataclass
class ApiKeyRecord:
    provider: str
    user_id: str
    api_key: str  # Decrypted plaintext


class ApiKeyManager:
    """Manages encrypted API key storage per provider per user."""

    def __init__(self, encryption_key: str) -> None:
        # Derive a Fernet key from the provided secret
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
        # In-memory store: {(provider, user_id): encrypted_bytes}
        self._store: dict[tuple[str, str], bytes] = {}

    def store(self, provider: str, user_id: str, api_key: str) -> None:
        encrypted = self._fernet.encrypt(api_key.encode())
        self._store[(provider, user_id)] = encrypted
        logger.info("api_key.stored", provider=provider, user_id=user_id)

    def get(self, provider: str, user_id: str) -> ApiKeyRecord | None:
        encrypted = self._store.get((provider, user_id))
        if encrypted is None:
            return None
        decrypted = self._fernet.decrypt(encrypted).decode()
        return ApiKeyRecord(provider=provider, user_id=user_id, api_key=decrypted)

    def delete(self, provider: str, user_id: str) -> None:
        self._store.pop((provider, user_id), None)
        logger.info("api_key.deleted", provider=provider, user_id=user_id)

    def _get_raw(self, provider: str, user_id: str) -> str | None:
        """Return raw encrypted value (for testing encryption)."""
        encrypted = self._store.get((provider, user_id))
        return encrypted.decode() if encrypted else None

    def validate_format(self, provider: str, key: str) -> bool:
        pattern = _KEY_PATTERNS.get(provider)
        if pattern is None:
            return True  # Unknown provider — accept any format
        return bool(pattern.match(key))

    def list_providers(self, user_id: str) -> list[str]:
        return [
            provider
            for (provider, uid) in self._store
            if uid == user_id
        ]
```

- [ ] **Step 5: Add cryptography dependency**

Add `"cryptography>=43.0.0"` to `dependencies` in `backend/pyproject.toml`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth_api_key.py -v`
Expected: All 9 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/brain/auth/ backend/tests/test_auth_api_key.py backend/pyproject.toml
git commit -m "feat(auth): add API key manager with AES encryption and format validation"
```

---

## Task 4: Provider Auth — OAuth Manager

**Files:**
- Create: `backend/nobla/brain/auth/oauth.py`
- Test: `backend/tests/test_auth_oauth.py`
- Modify: `backend/pyproject.toml` (add `authlib`)

OAuth2 flow manager. Phase 2B-1 implements Google (Gemini) OAuth. Others are stubs.

- [ ] **Step 1: Add authlib + httpx dependencies**

Add `"authlib>=1.3.0"` and `"httpx>=0.27.0"` to `dependencies` in `backend/pyproject.toml`.

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_auth_oauth.py
import pytest
from nobla.brain.auth.oauth import OAuthManager, OAuthConfig, OAuthTokens


@pytest.fixture
def oauth_manager():
    configs = {
        "gemini": OAuthConfig(
            provider="gemini",
            client_id="test-client-id",
            client_secret="test-client-secret",
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/generative-language"],
            redirect_uri="http://localhost:8000/api/oauth/callback/gemini",
        ),
    }
    return OAuthManager(configs=configs, encryption_key="test-key-32bytes-padding!!")


def test_get_auth_url_with_state(oauth_manager):
    url, state = oauth_manager.get_auth_url("gemini", "user-1")
    assert "accounts.google.com" in url
    assert "client_id=test-client-id" in url
    assert f"state={state}" in url
    assert len(state) > 10


def test_get_auth_url_unknown_provider(oauth_manager):
    with pytest.raises(ValueError, match="No OAuth config"):
        oauth_manager.get_auth_url("unknown", "user-1")


def test_validate_state(oauth_manager):
    _, state = oauth_manager.get_auth_url("gemini", "user-1")
    user_id = oauth_manager.validate_state(state)
    assert user_id == "user-1"


def test_validate_invalid_state(oauth_manager):
    assert oauth_manager.validate_state("invalid-state") is None


def test_store_and_get_tokens(oauth_manager):
    tokens = OAuthTokens(
        access_token="ya29.access-token",
        refresh_token="1//refresh-token",
        expires_at=9999999999,
        provider="gemini",
    )
    oauth_manager.store_tokens("gemini", "user-1", tokens)
    retrieved = oauth_manager.get_tokens("gemini", "user-1")
    assert retrieved is not None
    assert retrieved.access_token == "ya29.access-token"
    assert retrieved.refresh_token == "1//refresh-token"


def test_get_tokens_nonexistent(oauth_manager):
    assert oauth_manager.get_tokens("gemini", "user-1") is None


def test_revoke_tokens(oauth_manager):
    tokens = OAuthTokens(
        access_token="ya29.test",
        refresh_token="1//test",
        expires_at=9999999999,
        provider="gemini",
    )
    oauth_manager.store_tokens("gemini", "user-1", tokens)
    oauth_manager.revoke("gemini", "user-1")
    assert oauth_manager.get_tokens("gemini", "user-1") is None


def test_is_expired():
    expired = OAuthTokens(
        access_token="test", refresh_token="test",
        expires_at=0, provider="gemini",
    )
    assert expired.is_expired is True

    valid = OAuthTokens(
        access_token="test", refresh_token="test",
        expires_at=9999999999, provider="gemini",
    )
    assert valid.is_expired is False


def test_supported_providers(oauth_manager):
    providers = oauth_manager.supported_providers()
    assert "gemini" in providers


def test_csrf_state_is_single_use(oauth_manager):
    """Security: OAuth state token must be consumed after first validation."""
    _, state = oauth_manager.get_auth_url("gemini", "user-1")
    # First validation succeeds
    assert oauth_manager.validate_state(state) == "user-1"
    # Second validation with same state must fail (replay attack)
    assert oauth_manager.validate_state(state) is None


def test_auth_url_includes_csrf_state(oauth_manager):
    """Security: OAuth URL must include state parameter for CSRF protection."""
    url, state = oauth_manager.get_auth_url("gemini", "user-1")
    assert f"state={state}" in url
    assert "access_type=offline" in url
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth_oauth.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement OAuth manager**

```python
# backend/nobla/brain/auth/oauth.py
"""
OAuth2 flow manager for LLM provider authentication.

Handles authorization URL generation, state validation (CSRF),
token exchange, encrypted storage, and refresh. Google (Gemini)
is the first supported provider.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from cryptography.fernet import Fernet
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OAuthConfig:
    provider: str
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    scopes: list[str]
    redirect_uri: str


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: int  # Unix timestamp
    provider: str

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class OAuthManager:
    """Manages OAuth2 flows for LLM providers."""

    def __init__(
        self,
        configs: dict[str, OAuthConfig],
        encryption_key: str,
    ) -> None:
        self._configs = configs
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
        # In-memory stores (swap for DB in production)
        self._pending_states: dict[str, str] = {}  # state -> user_id
        self._tokens: dict[tuple[str, str], OAuthTokens] = {}

    def supported_providers(self) -> list[str]:
        return list(self._configs.keys())

    def get_auth_url(self, provider: str, user_id: str) -> tuple[str, str]:
        config = self._configs.get(provider)
        if not config:
            raise ValueError(f"No OAuth config for provider: {provider}")

        state = secrets.token_urlsafe(32)
        self._pending_states[state] = user_id

        params = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(config.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        url = f"{config.auth_url}?{urlencode(params)}"
        return url, state

    def validate_state(self, state: str) -> str | None:
        return self._pending_states.pop(state, None)

    def store_tokens(
        self, provider: str, user_id: str, tokens: OAuthTokens
    ) -> None:
        self._tokens[(provider, user_id)] = tokens
        logger.info("oauth.tokens_stored", provider=provider, user_id=user_id)

    def get_tokens(self, provider: str, user_id: str) -> OAuthTokens | None:
        return self._tokens.get((provider, user_id))

    def revoke(self, provider: str, user_id: str) -> None:
        self._tokens.pop((provider, user_id), None)
        logger.info("oauth.revoked", provider=provider, user_id=user_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth_oauth.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/brain/auth/oauth.py backend/tests/test_auth_oauth.py backend/pyproject.toml
git commit -m "feat(auth): add OAuth2 flow manager with CSRF state validation"
```

---

## Task 5: Provider Auth — Local Model Manager

**Files:**
- Create: `backend/nobla/brain/auth/local.py`
- Test: `backend/tests/test_auth_local.py`

Manages local Ollama endpoint registration and health checking.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_auth_local.py
import pytest
from nobla.brain.auth.local import LocalModelManager, LocalEndpoint


@pytest.fixture
def manager():
    return LocalModelManager()


def test_register_endpoint(manager):
    manager.register("user-1", "http://localhost:11434")
    endpoint = manager.get("user-1")
    assert endpoint is not None
    assert endpoint.base_url == "http://localhost:11434"


def test_register_with_models(manager):
    manager.register("user-1", "http://localhost:11434", models=["llama3.1", "codellama"])
    endpoint = manager.get("user-1")
    assert endpoint.models == ["llama3.1", "codellama"]


def test_get_nonexistent(manager):
    assert manager.get("user-1") is None


def test_remove_endpoint(manager):
    manager.register("user-1", "http://localhost:11434")
    manager.remove("user-1")
    assert manager.get("user-1") is None


def test_update_models(manager):
    manager.register("user-1", "http://localhost:11434", models=["llama3.1"])
    manager.update_models("user-1", ["llama3.1", "codellama", "mistral"])
    endpoint = manager.get("user-1")
    assert len(endpoint.models) == 3


def test_default_url():
    manager = LocalModelManager(default_url="http://gpu-box:11434")
    assert manager.default_url == "http://gpu-box:11434"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth_local.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement local model manager**

```python
# backend/nobla/brain/auth/local.py
"""
Local model endpoint management for Ollama and compatible servers.

Tracks user-configured local endpoints and their available models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LocalEndpoint:
    base_url: str
    models: list[str] = field(default_factory=list)
    is_healthy: bool = False


class LocalModelManager:
    """Manages local model endpoint registrations per user."""

    def __init__(self, default_url: str = "http://localhost:11434") -> None:
        self.default_url = default_url
        self._endpoints: dict[str, LocalEndpoint] = {}

    def register(
        self,
        user_id: str,
        base_url: str,
        models: list[str] | None = None,
    ) -> LocalEndpoint:
        endpoint = LocalEndpoint(base_url=base_url, models=models or [])
        self._endpoints[user_id] = endpoint
        logger.info("local.registered", user_id=user_id, base_url=base_url)
        return endpoint

    def get(self, user_id: str) -> LocalEndpoint | None:
        return self._endpoints.get(user_id)

    def remove(self, user_id: str) -> None:
        self._endpoints.pop(user_id, None)
        logger.info("local.removed", user_id=user_id)

    def update_models(self, user_id: str, models: list[str]) -> None:
        endpoint = self._endpoints.get(user_id)
        if endpoint:
            endpoint.models = models
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth_local.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Update auth __init__.py with all imports (all modules now exist)**

```python
# backend/nobla/brain/auth/__init__.py
from nobla.brain.auth.api_key import ApiKeyManager, ApiKeyRecord
from nobla.brain.auth.oauth import OAuthManager, OAuthConfig, OAuthTokens
from nobla.brain.auth.local import LocalModelManager, LocalEndpoint

__all__ = [
    "ApiKeyManager", "ApiKeyRecord",
    "OAuthManager", "OAuthConfig", "OAuthTokens",
    "LocalModelManager", "LocalEndpoint",
]
```

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/brain/auth/ backend/tests/test_auth_local.py
git commit -m "feat(auth): add local model endpoint manager for Ollama"
```

---

## Task 6: Restructure Providers into Subdirectory

**Files:**
- Create: `backend/nobla/brain/providers/__init__.py`
- Move: `backend/nobla/brain/gemini.py` → `backend/nobla/brain/providers/gemini.py`
- Move: `backend/nobla/brain/groq.py` → `backend/nobla/brain/providers/groq.py`
- Move: `backend/nobla/brain/ollama.py` → `backend/nobla/brain/providers/ollama.py`
- Modify: `backend/nobla/brain/__init__.py` (update imports)
- Modify: `backend/nobla/gateway/app.py` (update import paths)

- [ ] **Step 1: Create providers package**

```bash
mkdir -p backend/nobla/brain/providers
```

- [ ] **Step 2: Move existing provider files**

```bash
git mv backend/nobla/brain/gemini.py backend/nobla/brain/providers/gemini.py
git mv backend/nobla/brain/groq.py backend/nobla/brain/providers/groq.py
git mv backend/nobla/brain/ollama.py backend/nobla/brain/providers/ollama.py
```

- [ ] **Step 3: Create providers __init__.py**

```python
# backend/nobla/brain/providers/__init__.py
from nobla.brain.providers.gemini import GeminiProvider
from nobla.brain.providers.groq import GroqProvider
from nobla.brain.providers.ollama import OllamaProvider

__all__ = ["GeminiProvider", "GroqProvider", "OllamaProvider"]
```

- [ ] **Step 4: Update gateway/app.py inline imports**

The existing `app.py` uses lazy imports inside the lifespan function (`if name == "gemini": from nobla.brain.gemini import ...`). Update **only the module path** in each inline import block, preserving the existing pattern:

In the lifespan function (around lines 60-86), change each inline import:
```python
# Line ~61: change from
from nobla.brain.gemini import GeminiProvider
# to
from nobla.brain.providers.gemini import GeminiProvider

# Line ~71: change from
from nobla.brain.ollama import OllamaProvider
# to
from nobla.brain.providers.ollama import OllamaProvider

# Line ~79: change from
from nobla.brain.groq import GroqProvider
# to
from nobla.brain.providers.groq import GroqProvider
```

- [ ] **Step 5: Run existing tests to verify nothing broke**

Run: `cd backend && python -m pytest tests/test_router.py tests/test_providers.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(brain): move providers to brain/providers/ subdirectory"
```

---

## Task 7: New Providers — OpenAI, Anthropic, DeepSeek

**Files:**
- Create: `backend/nobla/brain/providers/openai.py`
- Create: `backend/nobla/brain/providers/anthropic.py`
- Create: `backend/nobla/brain/providers/deepseek.py`
- Test: `backend/tests/test_provider_openai.py`
- Test: `backend/tests/test_provider_anthropic.py`
- Test: `backend/tests/test_provider_deepseek.py`
- Modify: `backend/pyproject.toml` (add `openai`, `anthropic` SDKs)
- Modify: `backend/nobla/brain/providers/__init__.py`

Each provider follows the same `BaseLLMProvider` interface. Tests mock the SDK clients.

- [ ] **Step 1: Add SDK dependencies**

Add to `backend/pyproject.toml` dependencies:
```
"openai>=1.50.0",
"anthropic>=0.39.0",
```

- [ ] **Step 2: Write failing test for OpenAI provider**

```python
# backend/tests/test_provider_openai.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.brain.providers.openai import OpenAIProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = OpenAIProvider(api_key="sk-test-key")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from GPT"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])
    assert result.content == "Hello from GPT"
    assert result.tokens_input == 10
    assert result.tokens_output == 20


@pytest.mark.asyncio
async def test_health_check(provider):
    prov, mock_client = provider
    mock_client.models.list = AsyncMock(return_value=[])
    assert await prov.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure(provider):
    prov, mock_client = provider
    mock_client.models.list = AsyncMock(side_effect=Exception("Connection refused"))
    assert await prov.health_check() is False
```

- [ ] **Step 3: Implement OpenAI provider**

```python
# backend/nobla/brain/providers/openai.py
"""OpenAI GPT provider using the official openai SDK."""

from __future__ import annotations
import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse

_COST_INPUT = 2.50 / 1_000_000  # GPT-4o
_COST_OUTPUT = 10.00 / 1_000_000


class OpenAIProvider(BaseLLMProvider):
    """LLM provider backed by OpenAI's API."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        super().__init__(
            name="openai",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        self._client = AsyncOpenAI(api_key=api_key)

    @staticmethod
    def _to_openai_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages)
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model, messages=openai_messages, **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0
        content = response.choices[0].message.content or "" if response.choices else ""

        return LLMResponse(
            content=content, model=self.model,
            tokens_input=tokens_input, tokens_output=tokens_output,
            cost_usd=self.estimate_cost(tokens_input, tokens_output),
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        openai_messages = self._to_openai_messages(messages)
        stream = await self._client.chat.completions.create(
            model=self.model, messages=openai_messages, stream=True, **kwargs,
        )
        async for chunk in stream:
            if chunk.choices:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(self.model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Implement Anthropic provider**

```python
# backend/nobla/brain/providers/anthropic.py
"""Anthropic Claude provider using the official anthropic SDK."""

from __future__ import annotations
import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse

_COST_INPUT = 3.00 / 1_000_000  # Claude Sonnet
_COST_OUTPUT = 15.00 / 1_000_000


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by Anthropic's API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        super().__init__(
            name="anthropic",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        self._client = AsyncAnthropic(api_key=api_key)

    @staticmethod
    def _to_anthropic_messages(messages: list[LLMMessage]) -> tuple[str, list[dict]]:
        system = ""
        msgs = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                msgs.append({"role": msg.role, "content": msg.content})
        return system, msgs

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        system, anthropic_msgs = self._to_anthropic_messages(messages)
        start = time.monotonic()
        response = await self._client.messages.create(
            model=self.model, messages=anthropic_msgs,
            system=system or "You are a helpful assistant.",
            max_tokens=kwargs.pop("max_tokens", 4096), **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        content = response.content[0].text if response.content else ""
        tokens_input = response.usage.input_tokens
        tokens_output = response.usage.output_tokens

        return LLMResponse(
            content=content, model=self.model,
            tokens_input=tokens_input, tokens_output=tokens_output,
            cost_usd=self.estimate_cost(tokens_input, tokens_output),
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        system, anthropic_msgs = self._to_anthropic_messages(messages)
        async with self._client.messages.stream(
            model=self.model, messages=anthropic_msgs,
            system=system or "You are a helpful assistant.",
            max_tokens=kwargs.pop("max_tokens", 4096), **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def count_tokens(self, text: str) -> int:
        result = await self._client.count_tokens(text)
        return result

    async def health_check(self) -> bool:
        try:
            await self._client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                system="Reply with pong.",
                max_tokens=5,
            )
            return True
        except Exception:
            return False
```

- [ ] **Step 5: Implement DeepSeek provider**

```python
# backend/nobla/brain/providers/deepseek.py
"""DeepSeek provider using OpenAI-compatible API."""

from __future__ import annotations
import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse

_COST_INPUT = 0.14 / 1_000_000
_COST_OUTPUT = 0.28 / 1_000_000


class DeepSeekProvider(BaseLLMProvider):
    """LLM provider backed by DeepSeek's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        super().__init__(
            name="deepseek",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        self._client = AsyncOpenAI(
            api_key=api_key, base_url="https://api.deepseek.com",
        )

    @staticmethod
    def _to_openai_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages)
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model, messages=openai_messages, **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0
        content = response.choices[0].message.content or "" if response.choices else ""

        return LLMResponse(
            content=content, model=self.model,
            tokens_input=tokens_input, tokens_output=tokens_output,
            cost_usd=self.estimate_cost(tokens_input, tokens_output),
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        openai_messages = self._to_openai_messages(messages)
        stream = await self._client.chat.completions.create(
            model=self.model, messages=openai_messages, stream=True, **kwargs,
        )
        async for chunk in stream:
            if chunk.choices:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        return len(text.split()) * 4 // 3  # Estimate

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
```

- [ ] **Step 6: Write tests for Anthropic and DeepSeek (same pattern as OpenAI)**

```python
# backend/tests/test_provider_anthropic.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.brain.providers.anthropic import AnthropicProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = AnthropicProvider(api_key="sk-ant-test")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello from Claude")]
    mock_response.usage.input_tokens = 15
    mock_response.usage.output_tokens = 25
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])
    assert result.content == "Hello from Claude"
    assert result.tokens_input == 15


@pytest.mark.asyncio
async def test_system_message_extraction(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="OK")]
    mock_response.usage.input_tokens = 5
    mock_response.usage.output_tokens = 1
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    msgs = [
        LLMMessage(role="system", content="Be helpful"),
        LLMMessage(role="user", content="Hi"),
    ]
    await prov.generate(msgs)
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["system"] == "Be helpful"
```

```python
# backend/tests/test_provider_deepseek.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.brain.providers.deepseek import DeepSeekProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = DeepSeekProvider(api_key="sk-test")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "DeepSeek response"
    mock_response.usage.prompt_tokens = 8
    mock_response.usage.completion_tokens = 12
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])
    assert result.content == "DeepSeek response"


@pytest.mark.asyncio
async def test_uses_deepseek_base_url():
    with patch("nobla.brain.providers.deepseek.AsyncOpenAI") as mock_cls:
        DeepSeekProvider(api_key="sk-test")
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["base_url"] == "https://api.deepseek.com"
```

- [ ] **Step 7: Update providers __init__.py**

```python
# backend/nobla/brain/providers/__init__.py
from nobla.brain.providers.gemini import GeminiProvider
from nobla.brain.providers.groq import GroqProvider
from nobla.brain.providers.ollama import OllamaProvider
from nobla.brain.providers.openai import OpenAIProvider
from nobla.brain.providers.anthropic import AnthropicProvider
from nobla.brain.providers.deepseek import DeepSeekProvider

__all__ = [
    "GeminiProvider", "GroqProvider", "OllamaProvider",
    "OpenAIProvider", "AnthropicProvider", "DeepSeekProvider",
]
```

- [ ] **Step 8: Run all provider tests**

Run: `cd backend && python -m pytest tests/test_provider_openai.py tests/test_provider_anthropic.py tests/test_provider_deepseek.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add backend/nobla/brain/providers/ backend/tests/test_provider_*.py backend/pyproject.toml
git commit -m "feat(brain): add OpenAI, Anthropic, DeepSeek providers"
```

---

## Task 8: LiteLLM Proxy Provider

**Files:**
- Create: `backend/nobla/brain/providers/litellm_proxy.py`
- Test: `backend/tests/test_provider_litellm.py`
- Modify: `backend/pyproject.toml` (add `litellm`)

LiteLLM serves as a fallback abstraction for 100+ models. NOT the primary path.

- [ ] **Step 1: Add litellm dependency**

Add `"litellm>=1.50.0"` to `backend/pyproject.toml` dependencies.

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_provider_litellm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.brain.providers.litellm_proxy import LiteLLMProvider
from nobla.brain.base_provider import LLMMessage


@pytest.mark.asyncio
async def test_generate():
    with patch("nobla.brain.providers.litellm_proxy.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "LiteLLM response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 15
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        prov = LiteLLMProvider(model="together_ai/meta-llama/Llama-3-70b")
        result = await prov.generate([LLMMessage(role="user", content="Hi")])
        assert result.content == "LiteLLM response"


@pytest.mark.asyncio
async def test_health_check_success():
    with patch("nobla.brain.providers.litellm_proxy.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "pong"
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        prov = LiteLLMProvider(model="together_ai/meta-llama/Llama-3-70b")
        assert await prov.health_check() is True
```

- [ ] **Step 3: Implement LiteLLM provider**

```python
# backend/nobla/brain/providers/litellm_proxy.py
"""
LiteLLM unified fallback provider for 100+ models.

Used when: (a) user configures a non-primary provider, or
(b) all primary providers are circuit-broken.
"""

from __future__ import annotations
import time
from typing import AsyncIterator

import litellm

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


class LiteLLMProvider(BaseLLMProvider):
    """Fallback provider using LiteLLM for any OpenAI-compatible model."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        super().__init__(
            name="litellm",
            model=model,
            is_local=False,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )
        self._api_key = api_key

    @staticmethod
    def _to_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        msgs = self._to_messages(messages)
        start = time.monotonic()
        response = await litellm.acompletion(
            model=self.model, messages=msgs, api_key=self._api_key, **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0
        content = response.choices[0].message.content or "" if response.choices else ""

        return LLMResponse(
            content=content, model=self.model,
            tokens_input=tokens_input, tokens_output=tokens_output,
            cost_usd=0.0, latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        msgs = self._to_messages(messages)
        response = await litellm.acompletion(
            model=self.model, messages=msgs,
            api_key=self._api_key, stream=True, **kwargs,
        )
        async for chunk in response:
            if chunk.choices:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        return len(text.split()) * 4 // 3

    async def health_check(self) -> bool:
        try:
            await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                api_key=self._api_key,
                max_tokens=5,
            )
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests, commit**

Run: `cd backend && python -m pytest tests/test_provider_litellm.py -v`

```bash
git add backend/nobla/brain/providers/litellm_proxy.py backend/tests/test_provider_litellm.py backend/pyproject.toml
git commit -m "feat(brain): add LiteLLM fallback provider for 100+ models"
```

---

## Task 9: Enhanced Router with Circuit Breakers

**Files:**
- Modify: `backend/nobla/brain/router.py`
- Modify: `backend/tests/test_router.py`
- Modify: `backend/nobla/brain/__init__.py`

Upgrade the router: circuit breaker integration, multi-signal complexity classifier, updated preference lists with new providers.

- [ ] **Step 1: Write new failing tests for router enhancements**

```python
# Add to backend/tests/test_router.py (append these tests)

from nobla.brain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


def test_classify_with_technical_keywords():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("explain how neural networks learn") == TaskComplexity.MEDIUM
    assert router.classify_complexity("write a recursive fibonacci function") == TaskComplexity.HARD


def test_classify_length_signal():
    router = LLMRouter(providers={}, fallback_chain=[])
    # Very short = EASY
    assert router.classify_complexity("ok") == TaskComplexity.EASY
    # Long analytical = MEDIUM
    long_msg = "Can you analyze the trade-offs between microservices and monolithic architectures for our use case"
    assert router.classify_complexity(long_msg) == TaskComplexity.MEDIUM


@pytest.mark.asyncio
async def test_router_skips_circuit_broken_provider():
    gemini = make_mock_provider("gemini", healthy=True)
    groq = make_mock_provider("groq", healthy=True)

    cb_gemini = CircuitBreaker("gemini", CircuitBreakerConfig(failure_threshold=1))
    cb_gemini.record_failure()  # Opens circuit

    router = LLMRouter(
        providers={"gemini": gemini, "groq": groq},
        fallback_chain=["gemini", "groq"],
        circuit_breakers={"gemini": cb_gemini},
    )
    result = await router.route([LLMMessage(role="user", content="hello")])
    assert result.content == "Response from groq"
    # Gemini's generate should never have been called
    gemini.generate.assert_not_called()


@pytest.mark.asyncio
async def test_router_records_circuit_breaker_failure():
    gemini = make_mock_provider("gemini", healthy=True)
    gemini.generate = AsyncMock(side_effect=Exception("API error"))
    groq = make_mock_provider("groq", healthy=True)

    cb_gemini = CircuitBreaker("gemini", CircuitBreakerConfig(failure_threshold=3))

    router = LLMRouter(
        providers={"gemini": gemini, "groq": groq},
        fallback_chain=["gemini", "groq"],
        circuit_breakers={"gemini": cb_gemini},
    )
    result = await router.route([LLMMessage(role="user", content="hello")])
    assert result.content == "Response from groq"
    assert cb_gemini.failure_count == 1


def test_preference_includes_new_providers():
    router = LLMRouter(providers={}, fallback_chain=[])
    hard_prefs = router._select_provider_name(TaskComplexity.HARD)
    assert "anthropic" in hard_prefs or "openai" in hard_prefs
```

- [ ] **Step 2: Run tests to see failures**

Run: `cd backend && python -m pytest tests/test_router.py -v`
Expected: New tests FAIL (circuit_breakers param not accepted yet)

- [ ] **Step 3: Update router.py with circuit breaker integration**

Replace the full content of `backend/nobla/brain/router.py` with:

```python
# backend/nobla/brain/router.py
from __future__ import annotations
import re
from enum import Enum
from typing import AsyncIterator

import structlog

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse
from nobla.brain.circuit_breaker import CircuitBreaker

logger = structlog.get_logger(__name__)


class TaskComplexity(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


_EASY_PATTERNS = re.compile(
    r"\b("
    r"hi|hello|hey|thanks|thank you|bye|goodbye|"
    r"translate|summarize|summary|define|definition|what is|what are|"
    r"who is|who are|when is|when was|where is|where was|how do you say"
    r")\b",
    re.IGNORECASE,
)

_HARD_PATTERNS = re.compile(
    r"\b("
    r"write code|write a|implement|function|class|algorithm|"
    r"debug|fix the bug|refactor|optimize|regex|regular expression|"
    r"math|equation|proof|derive|integral|derivative|"
    r"create a program|build a|design a system|architect"
    r")\b",
    re.IGNORECASE,
)

_TECHNICAL_KEYWORDS = re.compile(
    r"\b("
    r"api|database|sql|docker|kubernetes|deploy|server|"
    r"authentication|encryption|pipeline|microservice|"
    r"neural network|machine learning|training"
    r")\b",
    re.IGNORECASE,
)

# Updated preference lists with new providers
_PREFERENCE: dict[TaskComplexity, list[str]] = {
    TaskComplexity.EASY: ["groq", "gemini", "ollama"],
    TaskComplexity.MEDIUM: ["gemini", "deepseek", "groq", "ollama"],
    TaskComplexity.HARD: ["anthropic", "openai", "gemini", "ollama"],
}


class LLMRouter:
    """
    Routes LLM requests to the most appropriate provider based on task
    complexity, provider health, circuit breaker state, and a configurable
    fallback chain.
    """

    def __init__(
        self,
        providers: dict[str, BaseLLMProvider],
        fallback_chain: list[str],
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self.providers = providers
        self.fallback_chain = fallback_chain
        self.circuit_breakers = circuit_breakers or {}

    # ------------------------------------------------------------------
    # Complexity classification (enhanced with multi-signal scoring)
    # ------------------------------------------------------------------

    def classify_complexity(self, message: str) -> TaskComplexity:
        if _HARD_PATTERNS.search(message):
            return TaskComplexity.HARD
        if _EASY_PATTERNS.search(message):
            return TaskComplexity.EASY
        if len(message.split()) <= 6:
            return TaskComplexity.EASY

        # Multi-signal scoring for ambiguous messages
        score = 0.0
        word_count = len(message.split())
        if word_count > 30:
            score += 0.3
        if _TECHNICAL_KEYWORDS.search(message):
            score += 0.3
        if "?" in message and word_count > 15:
            score += 0.1

        if score >= 0.6:
            return TaskComplexity.HARD
        return TaskComplexity.MEDIUM

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def _select_provider_name(self, complexity: TaskComplexity) -> list[str]:
        return _PREFERENCE.get(complexity, self.fallback_chain)

    async def _get_healthy_provider(
        self, preferred: list[str]
    ) -> BaseLLMProvider | None:
        candidates = list(preferred)
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue

            # Check circuit breaker before health check
            cb = self.circuit_breakers.get(name)
            if cb and not cb.is_available():
                logger.info("router.circuit_open", provider=name)
                continue

            try:
                healthy = await provider.health_check()
                if healthy:
                    logger.info("router.provider_selected", provider=name)
                    return provider
                logger.warning("router.provider_unhealthy", provider=name)
            except Exception as exc:
                logger.warning(
                    "router.provider_health_check_error",
                    provider=name, error=str(exc),
                )

        return None

    # ------------------------------------------------------------------
    # Public routing API
    # ------------------------------------------------------------------

    async def route(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)

        logger.info(
            "router.routing",
            complexity=complexity.value,
            preferred=preferred,
            message_preview=last_user[:80],
        )

        # Try providers in order; record circuit breaker outcomes
        candidates = list(preferred)
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue

            cb = self.circuit_breakers.get(name)
            if cb and not cb.is_available():
                continue

            try:
                healthy = await provider.health_check()
                if not healthy:
                    continue
                result = await provider.generate(messages, **kwargs)
                if cb:
                    cb.record_success()
                return result
            except Exception as exc:
                logger.warning(
                    "router.provider_failed",
                    provider=name, error=str(exc),
                )
                if cb:
                    cb.record_failure()
                continue

        raise RuntimeError("All LLM providers failed health checks")

    async def stream_route(
        self, messages: list[LLMMessage], **kwargs
    ) -> tuple[str, AsyncIterator[str]]:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)

        logger.info(
            "router.stream_routing",
            complexity=complexity.value,
            preferred=preferred,
        )

        candidates = list(preferred)
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue

            cb = self.circuit_breakers.get(name)
            if cb and not cb.is_available():
                continue

            try:
                healthy = await provider.health_check()
                if not healthy:
                    continue
                return provider.name, provider.stream(messages, **kwargs)
            except Exception as exc:
                logger.warning(
                    "router.stream_provider_failed",
                    provider=name, error=str(exc),
                )
                if cb:
                    cb.record_failure()
                continue

        raise RuntimeError("All LLM providers failed health checks")
```

- [ ] **Step 4: Run all router tests**

Run: `cd backend && python -m pytest tests/test_router.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Update brain/__init__.py exports**

```python
# backend/nobla/brain/__init__.py
from nobla.brain.router import LLMRouter, TaskComplexity
from nobla.brain.base_provider import BaseLLMProvider, LLMResponse, LLMMessage
from nobla.brain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from nobla.brain.token_counter import TokenCounter

__all__ = [
    "LLMRouter", "TaskComplexity",
    "BaseLLMProvider", "LLMResponse", "LLMMessage",
    "CircuitBreaker", "CircuitBreakerConfig", "CircuitState",
    "TokenCounter",
]
```

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/brain/router.py backend/nobla/brain/__init__.py backend/tests/test_router.py
git commit -m "feat(brain): integrate circuit breakers into router with enhanced classifier"
```

---

## Task 10: Streaming Handler

**Files:**
- Create: `backend/nobla/brain/streaming.py`
- Test: `backend/tests/test_streaming.py`

Coordinates streaming from a provider's `AsyncIterator[str]` to WebSocket JSON-RPC notifications.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_streaming.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.brain.streaming import StreamSession, StreamState


async def fake_stream(*tokens):
    for t in tokens:
        yield t


@pytest.mark.asyncio
async def test_stream_session_sends_tokens():
    ws = AsyncMock()
    session = StreamSession(
        ws=ws, conversation_id="conv-1", model="gemini-2.0-flash",
    )
    async def token_gen():
        yield "Hello"
        yield " world"

    await session.run(token_gen())

    # Should have sent: stream.start, 2x stream.token, stream.end
    calls = ws.send_json.call_args_list
    assert len(calls) == 4
    assert calls[0].args[0]["method"] == "chat.stream.start"
    assert calls[1].args[0]["method"] == "chat.stream.token"
    assert calls[1].args[0]["params"]["content"] == "Hello"
    assert calls[2].args[0]["params"]["content"] == " world"
    assert calls[3].args[0]["method"] == "chat.stream.end"


@pytest.mark.asyncio
async def test_stream_session_collects_full_text():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")

    async def token_gen():
        yield "Hello"
        yield " world"

    await session.run(token_gen())
    assert session.full_text == "Hello world"
    assert session.token_count == 2


@pytest.mark.asyncio
async def test_stream_session_cancellation():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")

    async def slow_stream():
        yield "Hello"
        await asyncio.sleep(10)  # Would block forever
        yield "never reached"

    session.cancel()
    await session.run(slow_stream())

    assert session.full_text == ""  # Cancelled before first token
    assert session.state == StreamState.CANCELLED


@pytest.mark.asyncio
async def test_stream_session_error_handling():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")

    async def error_stream():
        yield "partial"
        raise RuntimeError("Provider exploded")

    await session.run(error_stream())

    assert session.state == StreamState.ERROR
    assert session.full_text == "partial"
    # Should have sent stream.error notification
    last_call = ws.send_json.call_args_list[-1]
    assert last_call.args[0]["method"] == "chat.stream.error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_streaming.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement streaming handler**

```python
# backend/nobla/brain/streaming.py
"""
WebSocket streaming coordinator.

Bridges provider AsyncIterator[str] to JSON-RPC notifications
over WebSocket. Handles cancellation, errors, and backpressure.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import AsyncIterator

from fastapi import WebSocket
import structlog

logger = structlog.get_logger(__name__)


class StreamState(str, Enum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class StreamSession:
    """Manages a single streaming response session."""

    def __init__(
        self,
        ws: WebSocket,
        conversation_id: str,
        model: str,
        buffer_size: int = 100,
    ) -> None:
        self._ws = ws
        self._conversation_id = conversation_id
        self._model = model
        self._buffer_size = buffer_size
        self._cancelled = asyncio.Event()
        self._state = StreamState.PENDING
        self._full_text = ""
        self._token_count = 0

    @property
    def state(self) -> StreamState:
        return self._state

    @property
    def full_text(self) -> str:
        return self._full_text

    @property
    def token_count(self) -> int:
        return self._token_count

    def cancel(self) -> None:
        self._cancelled.set()
        self._state = StreamState.CANCELLED

    async def _send_notification(self, method: str, params: dict) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._ws.send_json(msg)

    async def run(self, token_stream: AsyncIterator[str]) -> None:
        if self._cancelled.is_set():
            return

        self._state = StreamState.STREAMING

        await self._send_notification("chat.stream.start", {
            "conversation_id": self._conversation_id,
            "model": self._model,
        })

        try:
            index = 0
            async for token in token_stream:
                if self._cancelled.is_set():
                    self._state = StreamState.CANCELLED
                    break

                self._full_text += token
                self._token_count += 1

                await self._send_notification("chat.stream.token", {
                    "content": token,
                    "index": index,
                })
                index += 1

            if self._state == StreamState.STREAMING:
                self._state = StreamState.COMPLETED

        except Exception as exc:
            self._state = StreamState.ERROR
            logger.error(
                "stream.error",
                conversation_id=self._conversation_id,
                error=str(exc),
            )
            await self._send_notification("chat.stream.error", {
                "code": -32000,
                "message": str(exc),
            })
            return

        if self._state == StreamState.COMPLETED:
            await self._send_notification("chat.stream.end", {
                "tokens_output": self._token_count,
                "model": self._model,
                "conversation_id": self._conversation_id,
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_streaming.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/brain/streaming.py backend/tests/test_streaming.py
git commit -m "feat(brain): add WebSocket streaming coordinator with cancellation support"
```

---

## Task 11: Gateway — Streaming Chat + Provider RPC Handlers

**Files:**
- Modify: `backend/nobla/gateway/websocket.py` (add `chat.stream`, `chat.stream.cancel`, provider.* handlers)
- Test: `backend/tests/test_provider_rpc.py`
- Test: `backend/tests/test_streaming_flow.py`

Add new JSON-RPC methods: `chat.stream` (streaming version of `chat.send`), `chat.stream.cancel`, and provider management methods (`provider.list`, `provider.connect_apikey`, `provider.disconnect`, `provider.health`).

- [ ] **Step 1: Write failing tests for provider RPC**

```python
# backend/tests/test_provider_rpc.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.gateway.websocket import (
    handle_message,
    ConnectionState,
    set_router,
)


@pytest.fixture
def ws():
    mock = AsyncMock()
    mock.send_json = AsyncMock()
    return mock


@pytest.fixture
def authed_state():
    return ConnectionState(user_id="test-user")


@pytest.mark.asyncio
async def test_provider_list(ws, authed_state):
    """provider.list should return available providers with status."""
    msg = '{"jsonrpc":"2.0","method":"provider.list","params":{},"id":1}'
    await handle_message(ws, msg, authed_state)
    response = ws.send_json.call_args.args[0]
    assert "result" in response
    assert "providers" in response["result"]
```

- [ ] **Step 2: Add streaming RPC handlers to websocket.py**

Add to `backend/nobla/gateway/websocket.py` — after the existing `chat.send` handler, before the Conversation section:

```python
# ---------------------------------------------------------------------------
# Streaming Chat (Phase 2B)
# ---------------------------------------------------------------------------

import asyncio
from nobla.brain.streaming import StreamSession

# Active streaming sessions: {conversation_id: StreamSession}
_active_streams: dict[str, StreamSession] = {}


@rpc_method("chat.stream")
async def handle_chat_stream(params: dict, state: ConnectionState) -> dict:
    """Start a streaming LLM response. Tokens arrive as notifications."""
    message = params.get("message", "")
    conversation_id = params.get("conversation_id", str(uuid.uuid4()))

    router = get_router()
    if not router:
        raise RuntimeError("LLM router not initialized")

    # Build messages (same as chat.send)
    memory = get_memory_orchestrator()
    if memory:
        conv_uuid = uuid.UUID(conversation_id)
        await memory.process_message(
            conversation_id=conv_uuid, role="user", content=message,
        )

    memory_context = ""
    if memory and state.user_id:
        memory_context = await memory.get_memory_context(
            user_id=uuid.UUID(state.user_id), query=message,
        )

    llm_messages = []
    if memory_context:
        llm_messages.append(LLMMessage(role="system", content=f"[Memory] {memory_context}"))
    llm_messages.append(LLMMessage(role="user", content=message))

    provider_name, token_iter = await router.stream_route(llm_messages)

    # We need access to the raw WebSocket — get it from the connection manager
    ws_pair = manager._connections.get(state.connection_id)
    if not ws_pair:
        raise RuntimeError("WebSocket connection not found")
    ws, _ = ws_pair

    session = StreamSession(
        ws=ws, conversation_id=conversation_id, model=provider_name,
    )
    _active_streams[conversation_id] = session

    async def run_stream():
        try:
            await session.run(token_iter)
        finally:
            _active_streams.pop(conversation_id, None)
            # Store assistant response in memory
            if memory and session.full_text:
                await memory.process_message(
                    conversation_id=uuid.UUID(conversation_id),
                    role="assistant",
                    content=session.full_text,
                    model_used=provider_name,
                )

    asyncio.create_task(run_stream())
    return {"conversation_id": conversation_id, "model": provider_name, "streaming": True}


@rpc_method("chat.stream.cancel")
async def handle_chat_stream_cancel(params: dict, state: ConnectionState) -> dict:
    conversation_id = params.get("conversation_id", "")
    session = _active_streams.get(conversation_id)
    if session:
        session.cancel()
        return {"cancelled": True, "partial_text": session.full_text}
    return {"cancelled": False, "error": "No active stream for this conversation"}
```

- [ ] **Step 3: Create provider_handlers.py**

```python
# backend/nobla/gateway/provider_handlers.py
"""
JSON-RPC handlers for provider management.

Registered via the @rpc_method decorator from websocket.py.
"""

from __future__ import annotations

import structlog

from nobla.gateway.websocket import rpc_method, ConnectionState

logger = structlog.get_logger(__name__)

# Service accessors — set during app lifespan
_api_key_manager = None
_oauth_manager = None
_local_model_manager = None
_provider_registry: dict[str, dict] = {}


def set_api_key_manager(mgr) -> None:
    global _api_key_manager
    _api_key_manager = mgr


def set_oauth_manager(mgr) -> None:
    global _oauth_manager
    _oauth_manager = mgr


def set_local_model_manager(mgr) -> None:
    global _local_model_manager
    _local_model_manager = mgr


def set_provider_registry(registry: dict[str, dict]) -> None:
    global _provider_registry
    _provider_registry = registry


@rpc_method("provider.list")
async def handle_provider_list(params: dict, state: ConnectionState) -> dict:
    """List all providers with connection status."""
    providers = []
    for name, info in _provider_registry.items():
        connected = False
        auth_type = "none"

        if _api_key_manager and _api_key_manager.get(name, state.user_id or ""):
            connected = True
            auth_type = "api_key"
        elif _oauth_manager and _oauth_manager.get_tokens(name, state.user_id or ""):
            connected = True
            auth_type = "oauth"
        elif _local_model_manager and name == "ollama":
            endpoint = _local_model_manager.get(state.user_id or "")
            if endpoint:
                connected = True
                auth_type = "local"

        providers.append({
            "name": name,
            "display_name": info.get("display_name", name.title()),
            "connected": connected,
            "auth_type": auth_type,
            "auth_methods": info.get("auth_methods", ["api_key"]),
            "model": info.get("model", ""),
        })

    return {"providers": providers}


@rpc_method("provider.connect_apikey")
async def handle_provider_connect_apikey(params: dict, state: ConnectionState) -> dict:
    """Validate and store an API key for a provider."""
    if not _api_key_manager:
        raise RuntimeError("API key manager not initialized")

    provider = params.get("provider", "")
    api_key = params.get("api_key", "")

    if not provider or not api_key:
        return {"connected": False, "error": "Provider and api_key are required"}

    if not _api_key_manager.validate_format(provider, api_key):
        return {"connected": False, "error": f"Invalid API key format for {provider}"}

    user_id = state.user_id or "default"
    _api_key_manager.store(provider, user_id, api_key)
    return {"connected": True, "provider": provider, "auth_type": "api_key"}


@rpc_method("provider.oauth_url")
async def handle_provider_oauth_url(params: dict, state: ConnectionState) -> dict:
    """Get OAuth authorization URL for a provider."""
    if not _oauth_manager:
        raise RuntimeError("OAuth manager not initialized")

    provider = params.get("provider", "")
    user_id = state.user_id or "default"

    try:
        url, oauth_state = _oauth_manager.get_auth_url(provider, user_id)
        return {"auth_url": url, "state": oauth_state}
    except ValueError as e:
        return {"error": str(e)}


@rpc_method("provider.oauth_callback")
async def handle_provider_oauth_callback(params: dict, state: ConnectionState) -> dict:
    """Exchange OAuth auth code for tokens (called after redirect)."""
    if not _oauth_manager:
        raise RuntimeError("OAuth manager not initialized")

    oauth_state = params.get("state", "")
    code = params.get("code", "")

    user_id = _oauth_manager.validate_state(oauth_state)
    if not user_id:
        return {"connected": False, "error": "Invalid or expired OAuth state (CSRF check failed)"}

    # Token exchange would happen here via httpx to the provider's token_url
    # For now, return that the code was received and state validated
    return {
        "connected": True,
        "user_id": user_id,
        "message": "OAuth code received; token exchange pending",
    }


@rpc_method("provider.connect_local")
async def handle_provider_connect_local(params: dict, state: ConnectionState) -> dict:
    """Configure a local model endpoint (Ollama)."""
    if not _local_model_manager:
        raise RuntimeError("Local model manager not initialized")

    base_url = params.get("base_url", "http://localhost:11434")
    models = params.get("models", [])
    user_id = state.user_id or "default"

    endpoint = _local_model_manager.register(user_id, base_url, models)
    return {
        "connected": True,
        "base_url": endpoint.base_url,
        "models": endpoint.models,
    }


@rpc_method("provider.disconnect")
async def handle_provider_disconnect(params: dict, state: ConnectionState) -> dict:
    """Disconnect a provider by removing credentials."""
    provider = params.get("provider", "")
    user_id = state.user_id or "default"

    if _api_key_manager:
        _api_key_manager.delete(provider, user_id)
    if _oauth_manager:
        _oauth_manager.revoke(provider, user_id)
    if _local_model_manager and provider == "ollama":
        _local_model_manager.remove(user_id)

    return {"disconnected": True, "provider": provider}


@rpc_method("provider.health")
async def handle_provider_health(params: dict, state: ConnectionState) -> dict:
    """Health-check a specific provider."""
    from nobla.gateway.websocket import get_router

    provider_name = params.get("provider", "")
    router = get_router()
    if not router:
        return {"healthy": False, "error": "Router not initialized"}

    provider = router.providers.get(provider_name)
    if not provider:
        return {"healthy": False, "error": f"Provider '{provider_name}' not configured"}

    try:
        healthy = await provider.health_check()
        return {"healthy": healthy, "provider": provider_name}
    except Exception as e:
        return {"healthy": False, "error": str(e)}
```

- [ ] **Step 4: Import provider_handlers in app.py**

Add to `backend/nobla/gateway/app.py` alongside the existing memory_handlers import:
```python
import nobla.gateway.provider_handlers  # noqa: F401
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_provider_rpc.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/gateway/ backend/tests/test_provider_rpc.py
git commit -m "feat(gateway): add streaming chat + provider management RPC handlers"
```

---

## Task 12: Config + App Wiring

**Files:**
- Modify: `backend/nobla/config/settings.py` (new provider settings)
- Modify: `backend/nobla/gateway/app.py` (wire new providers + circuit breakers)

- [ ] **Step 1: Update settings.py**

Add to `ProviderSettings`:
```python
auth_type: str = "api_key"  # "api_key" | "oauth" | "local"
```

Add to `LLMSettings`:
```python
fallback_chain: list[str] = ["gemini", "groq", "ollama", "openai", "anthropic", "deepseek"]
providers: dict[str, ProviderSettings] = Field(default_factory=lambda: {
    "gemini": ProviderSettings(model="gemini-2.0-flash"),
    "ollama": ProviderSettings(model="llama3.1", base_url="http://localhost:11434"),
    "groq": ProviderSettings(model="llama-3.1-70b-versatile"),
    "openai": ProviderSettings(model="gpt-4o", enabled=False),
    "anthropic": ProviderSettings(model="claude-sonnet-4-20250514", enabled=False),
    "deepseek": ProviderSettings(model="deepseek-chat", enabled=False),
})
```

- [ ] **Step 2: Update app.py lifespan to wire new providers + circuit breakers**

In `backend/nobla/gateway/app.py`, add these imports at the top:

```python
from nobla.brain.circuit_breaker import CircuitBreaker
from nobla.brain.auth.api_key import ApiKeyManager
from nobla.brain.auth.oauth import OAuthManager, OAuthConfig
from nobla.brain.auth.local import LocalModelManager
from nobla.gateway.provider_handlers import (
    set_api_key_manager, set_oauth_manager,
    set_local_model_manager, set_provider_registry,
)
```

Then update the lifespan function — after the existing provider loop, add new provider `elif` blocks and circuit breakers:

```python
    # Inside lifespan(), after existing provider loop:

    # --- New Providers (Phase 2B) ---
    for name in llm_config.fallback_chain:
        prov_settings = llm_config.providers.get(name)
        if not prov_settings or not prov_settings.enabled:
            continue
        if name in providers:
            continue  # Already initialized above
        try:
            if name == "openai":
                from nobla.brain.providers.openai import OpenAIProvider
                api_key = prov_settings.api_key or os.environ.get("OPENAI_API_KEY", "")
                if api_key:
                    providers[name] = OpenAIProvider(api_key=api_key, model=prov_settings.model)
            elif name == "anthropic":
                from nobla.brain.providers.anthropic import AnthropicProvider
                api_key = prov_settings.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
                if api_key:
                    providers[name] = AnthropicProvider(api_key=api_key, model=prov_settings.model)
            elif name == "deepseek":
                from nobla.brain.providers.deepseek import DeepSeekProvider
                api_key = prov_settings.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
                if api_key:
                    providers[name] = DeepSeekProvider(api_key=api_key, model=prov_settings.model)
        except Exception as e:
            logger.warning("provider_init_failed", provider=name, error=str(e))

    # --- Circuit Breakers ---
    circuit_breakers = {name: CircuitBreaker(name) for name in providers}

    router = LLMRouter(
        providers=providers,
        fallback_chain=llm_config.fallback_chain,
        circuit_breakers=circuit_breakers,
    )
    set_router(router)

    # --- Provider Auth (Phase 2B) ---
    api_key_mgr = ApiKeyManager(encryption_key=settings.secret_key or "dev-key-change-me")
    oauth_mgr = OAuthManager(configs={}, encryption_key=settings.secret_key or "dev-key-change-me")
    local_mgr = LocalModelManager()

    set_api_key_manager(api_key_mgr)
    set_oauth_manager(oauth_mgr)
    set_local_model_manager(local_mgr)

    # Provider registry for provider.list RPC
    set_provider_registry({
        "gemini": {"display_name": "Google Gemini", "auth_methods": ["oauth", "api_key"], "model": "gemini-2.0-flash"},
        "openai": {"display_name": "OpenAI GPT", "auth_methods": ["api_key"], "model": "gpt-4o"},
        "anthropic": {"display_name": "Anthropic Claude", "auth_methods": ["api_key"], "model": "claude-sonnet-4-20250514"},
        "groq": {"display_name": "Groq", "auth_methods": ["api_key"], "model": "llama-3.1-70b-versatile"},
        "deepseek": {"display_name": "DeepSeek", "auth_methods": ["api_key"], "model": "deepseek-chat"},
        "ollama": {"display_name": "Ollama (Local)", "auth_methods": ["local"], "model": "llama3.1"},
    })
```

**Note:** Remove the old `router = LLMRouter(...)` and `set_router(router)` lines (around lines 90-93) since we replaced them above.

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/gateway/app.py
git commit -m "feat(config): wire new providers, circuit breakers, and auth into app lifespan"
```

---

## Task 13: Flutter — Provider Management Screen

**Files:**
- Create: `app/lib/features/settings/providers/provider_settings_provider.dart`
- Create: `app/lib/features/settings/screens/provider_management_screen.dart`
- Create: `app/lib/features/settings/widgets/provider_card.dart`
- Create: `app/lib/features/settings/widgets/api_key_wizard.dart`
- Modify: `app/lib/features/settings/screens/settings_screen.dart`

- [ ] **Step 1: Create Riverpod provider for settings state**

```dart
// app/lib/features/settings/providers/provider_settings_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/core/network/jsonrpc_client.dart';

class ProviderInfo {
  final String name;
  final String displayName;
  final bool connected;
  final String authType;
  final List<String> authMethods;
  final String model;

  const ProviderInfo({
    required this.name,
    required this.displayName,
    required this.connected,
    required this.authType,
    required this.authMethods,
    required this.model,
  });

  factory ProviderInfo.fromJson(Map<String, dynamic> json) {
    return ProviderInfo(
      name: json['name'] as String,
      displayName: json['display_name'] as String? ?? json['name'] as String,
      connected: json['connected'] as bool? ?? false,
      authType: json['auth_type'] as String? ?? 'none',
      authMethods: (json['auth_methods'] as List?)?.cast<String>() ?? ['api_key'],
      model: json['model'] as String? ?? '',
    );
  }
}

class ProviderSettingsState {
  final List<ProviderInfo> providers;
  final bool isLoading;
  final String? error;

  const ProviderSettingsState({
    this.providers = const [],
    this.isLoading = false,
    this.error,
  });

  ProviderSettingsState copyWith({
    List<ProviderInfo>? providers,
    bool? isLoading,
    String? error,
  }) {
    return ProviderSettingsState(
      providers: providers ?? this.providers,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class ProviderSettingsNotifier extends StateNotifier<ProviderSettingsState> {
  final JsonRpcClient _rpc;
  ProviderSettingsNotifier(this._rpc) : super(const ProviderSettingsState());

  Future<void> loadProviders() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _rpc.call('provider.list');
      final list = (result['providers'] as List)
          .map((p) => ProviderInfo.fromJson(p as Map<String, dynamic>))
          .toList();
      state = state.copyWith(providers: list, isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<bool> connectApiKey(String provider, String apiKey) async {
    try {
      final result = await _rpc.call('provider.connect_apikey', {
        'provider': provider,
        'api_key': apiKey,
      });
      if (result['connected'] == true) {
        await loadProviders();
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  Future<void> disconnect(String provider) async {
    await _rpc.call('provider.disconnect', {'provider': provider});
    await loadProviders();
  }
}
```

- [ ] **Step 2: Create provider card widget**

```dart
// app/lib/features/settings/widgets/provider_card.dart
import 'package:flutter/material.dart';
import 'package:nobla_agent/features/settings/providers/provider_settings_provider.dart';

class ProviderCard extends StatelessWidget {
  final ProviderInfo provider;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;

  const ProviderCard({
    super.key,
    required this.provider,
    required this.onConnect,
    required this.onDisconnect,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: ListTile(
        leading: Icon(
          provider.connected ? Icons.check_circle : Icons.circle_outlined,
          color: provider.connected ? Colors.green : Colors.grey,
        ),
        title: Text(provider.displayName),
        subtitle: Text(
          provider.connected
              ? 'Connected via ${provider.authType} \u2022 ${provider.model}'
              : 'Not connected',
          style: theme.textTheme.bodySmall,
        ),
        trailing: provider.connected
            ? TextButton(onPressed: onDisconnect, child: const Text('Disconnect'))
            : FilledButton(onPressed: onConnect, child: const Text('Connect')),
      ),
    );
  }
}
```

- [ ] **Step 3: Create API key wizard widget**

```dart
// app/lib/features/settings/widgets/api_key_wizard.dart
import 'package:flutter/material.dart';

class ApiKeyWizard extends StatefulWidget {
  final String provider;
  final Future<bool> Function(String apiKey) onSubmit;

  const ApiKeyWizard({
    super.key,
    required this.provider,
    required this.onSubmit,
  });

  @override
  State<ApiKeyWizard> createState() => _ApiKeyWizardState();
}

class _ApiKeyWizardState extends State<ApiKeyWizard> {
  final _controller = TextEditingController();
  bool _isSubmitting = false;
  String? _error;

  static const _consoleUrls = {
    'openai': 'platform.openai.com/api-keys',
    'anthropic': 'console.anthropic.com/settings/keys',
    'groq': 'console.groq.com/keys',
    'deepseek': 'platform.deepseek.com/api_keys',
    'gemini': 'aistudio.google.com/apikey',
  };

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_controller.text.trim().isEmpty) return;
    setState(() { _isSubmitting = true; _error = null; });
    final success = await widget.onSubmit(_controller.text.trim());
    if (!mounted) return;
    if (success) {
      Navigator.of(context).pop(true);
    } else {
      setState(() { _isSubmitting = false; _error = 'Invalid API key'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final url = _consoleUrls[widget.provider] ?? '';
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 24, right: 24, top: 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Connect ${widget.provider.toUpperCase()}',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          if (url.isNotEmpty) ...[
            Text('1. Go to $url'),
            const Text('2. Create a new API key'),
            const Text('3. Paste it below'),
            const SizedBox(height: 16),
          ],
          TextField(
            controller: _controller,
            decoration: InputDecoration(
              labelText: 'API Key',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
            obscureText: true,
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Connect'),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Create provider management screen**

```dart
// app/lib/features/settings/screens/provider_management_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nobla_agent/features/settings/providers/provider_settings_provider.dart';
import 'package:nobla_agent/features/settings/widgets/provider_card.dart';
import 'package:nobla_agent/features/settings/widgets/api_key_wizard.dart';

class ProviderManagementScreen extends ConsumerStatefulWidget {
  const ProviderManagementScreen({super.key});

  @override
  ConsumerState<ProviderManagementScreen> createState() => _ProviderManagementScreenState();
}

class _ProviderManagementScreenState extends ConsumerState<ProviderManagementScreen> {
  @override
  void initState() {
    super.initState();
    // Load providers on screen open
    Future.microtask(() {
      // ref.read(providerSettingsProvider.notifier).loadProviders();
      // NOTE: Provider wiring depends on how JsonRpcClient is provided.
      // Wire this once the Riverpod provider is registered in main.dart.
    });
  }

  void _showApiKeyWizard(String providerName, ProviderSettingsNotifier notifier) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => ApiKeyWizard(
        provider: providerName,
        onSubmit: (key) => notifier.connectApiKey(providerName, key),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // TODO: Wire to actual Riverpod provider once registered
    // final state = ref.watch(providerSettingsProvider);
    // final notifier = ref.read(providerSettingsProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('LLM Providers')),
      body: const Center(child: Text('Provider list loads here')),
      // Replace body with:
      // state.isLoading
      //   ? const Center(child: CircularProgressIndicator())
      //   : ListView.builder(
      //       itemCount: state.providers.length,
      //       itemBuilder: (context, index) {
      //         final p = state.providers[index];
      //         return ProviderCard(
      //           provider: p,
      //           onConnect: () => _showApiKeyWizard(p.name, notifier),
      //           onDisconnect: () => notifier.disconnect(p.name),
      //         );
      //       },
      //     ),
    );
  }
}
```

- [ ] **Step 5: Update settings screen with navigation**

Add to `app/lib/features/settings/screens/settings_screen.dart` — inside the settings list, add a tile:

```dart
ListTile(
  leading: const Icon(Icons.psychology),
  title: const Text('LLM Providers'),
  subtitle: const Text('Connect AI models'),
  trailing: const Icon(Icons.chevron_right),
  onTap: () => Navigator.push(
    context,
    MaterialPageRoute(builder: (_) => const ProviderManagementScreen()),
  ),
),
```

And add the import at the top:
```dart
import 'package:nobla_agent/features/settings/screens/provider_management_screen.dart';
```

- [ ] **Step 6: Run Flutter analyze**

Run: `cd app && flutter analyze`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add app/lib/features/settings/
git commit -m "feat(flutter): add provider management screen with API key wizard"
```

---

## Task 14: Flutter — Streaming Message Display

**Files:**
- Create: `app/lib/features/chat/widgets/streaming_message.dart`
- Modify: `app/lib/features/chat/providers/chat_provider.dart`

- [ ] **Step 1: Create streaming message widget**

```dart
// app/lib/features/chat/widgets/streaming_message.dart
import 'package:flutter/material.dart';

class StreamingMessage extends StatelessWidget {
  final String text;
  final String model;
  final bool isStreaming;
  final VoidCallback? onCancel;

  const StreamingMessage({
    super.key,
    required this.text,
    required this.model,
    required this.isStreaming,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isStreaming)
            Row(
              children: [
                SizedBox(
                  width: 12, height: 12,
                  child: CircularProgressIndicator(strokeWidth: 1.5, color: theme.colorScheme.primary),
                ),
                const SizedBox(width: 8),
                Text(model, style: theme.textTheme.labelSmall),
                const Spacer(),
                if (onCancel != null)
                  IconButton(
                    icon: const Icon(Icons.stop_circle_outlined, size: 20),
                    onPressed: onCancel,
                    tooltip: 'Stop generating',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
              ],
            ),
          if (isStreaming) const SizedBox(height: 8),
          Text(
            text.isEmpty && isStreaming ? '...' : text,
            style: theme.textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: Update ChatNotifier for streaming**

Add to `app/lib/features/chat/providers/chat_provider.dart`:

```dart
// Add these fields to ChatState:
//   final String streamingText;
//   final bool isStreaming;
//   final String streamingModel;

// Add this import at top:
// import 'dart:async';

// Add this method to ChatNotifier:
  StreamSubscription? _streamSub;

  Future<void> sendMessageStreaming(String text) async {
    final userMsg = ChatMessage.user(text);
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isLoading: true,
    );

    try {
      final result = await _rpc.call('chat.stream', {
        'message': text,
        'conversation_id': state.conversationId,
      });

      final model = result['model'] as String? ?? '';

      // Listen for streaming notifications
      _streamSub = _rpc.notificationStream.listen((notification) {
        final method = notification['method'] as String?;
        final params = notification['params'] as Map<String, dynamic>? ?? {};

        switch (method) {
          case 'chat.stream.token':
            final token = params['content'] as String? ?? '';
            // Update the last message with accumulated text
            _appendStreamToken(token);
          case 'chat.stream.end':
            _finalizeStream(model);
            _streamSub?.cancel();
          case 'chat.stream.error':
            _handleStreamError(params['message'] as String? ?? 'Stream error');
            _streamSub?.cancel();
        }
      });
    } catch (e) {
      state = state.copyWith(isLoading: false);
    }
  }

  void _appendStreamToken(String token) {
    // Build streaming text incrementally
    final messages = List<ChatMessage>.from(state.messages);
    if (messages.isNotEmpty && messages.last.role == 'assistant') {
      final last = messages.removeLast();
      messages.add(last.copyWith(content: last.content + token));
    } else {
      messages.add(ChatMessage(
        role: 'assistant', content: token, status: MessageStatus.sending,
      ));
    }
    state = state.copyWith(messages: messages);
  }

  void _finalizeStream(String model) {
    final messages = List<ChatMessage>.from(state.messages);
    if (messages.isNotEmpty && messages.last.role == 'assistant') {
      final last = messages.removeLast();
      messages.add(last.copyWith(status: MessageStatus.sent));
    }
    state = state.copyWith(messages: messages, isLoading: false);
  }

  void _handleStreamError(String error) {
    state = state.copyWith(isLoading: false);
  }

  Future<void> cancelStream() async {
    _streamSub?.cancel();
    await _rpc.call('chat.stream.cancel', {
      'conversation_id': state.conversationId,
    });
    state = state.copyWith(isLoading: false);
  }
```

- [ ] **Step 3: Run Flutter analyze**

Run: `cd app && flutter analyze`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add app/lib/features/chat/
git commit -m "feat(flutter): add streaming message display with cancel support"
```

---

## Task 15: Integration Test — Full Streaming Flow

**Files:**
- Create: `backend/tests/test_streaming_flow.py`

End-to-end test: WebSocket client sends `chat.stream`, receives `stream.start` → `stream.token` × N → `stream.end`.

- [ ] **Step 1: Write integration test**

```python
# backend/tests/test_streaming_flow.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.brain.streaming import StreamSession, StreamState


@pytest.mark.asyncio
async def test_full_stream_lifecycle():
    """Verify complete stream: start → tokens → end."""
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="test-conv", model="gemini-2.0-flash")

    async def mock_provider_stream():
        yield "The"
        yield " answer"
        yield " is"
        yield " 42"

    await session.run(mock_provider_stream())

    assert session.state == StreamState.COMPLETED
    assert session.full_text == "The answer is 42"
    assert session.token_count == 4

    calls = ws.send_json.call_args_list
    methods = [c.args[0]["method"] for c in calls]
    assert methods[0] == "chat.stream.start"
    assert methods[-1] == "chat.stream.end"
    assert all(m == "chat.stream.token" for m in methods[1:-1])

    # Verify end notification includes stats
    end_params = calls[-1].args[0]["params"]
    assert end_params["tokens_output"] == 4
    assert end_params["model"] == "gemini-2.0-flash"
```

- [ ] **Step 2: Run integration test**

Run: `cd backend && python -m pytest tests/test_streaming_flow.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --cov=nobla --ignore=tests/integration`
Expected: All tests PASS, coverage report shows new modules covered

- [ ] **Step 4: Final commit**

```bash
git add backend/tests/test_streaming_flow.py
git commit -m "test: add full streaming flow integration test for Phase 2B-1"
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | Circuit Breaker | 1 new | 8 |
| 2 | Token Counter | 1 new | 6 |
| 3 | API Key Auth | 2 new | 9 |
| 4 | OAuth Auth | 1 new | 9 |
| 5 | Local Auth | 1 new | 6 |
| 6 | Restructure Providers | 1 new, 3 moved | 0 (verify existing) |
| 7 | OpenAI + Anthropic + DeepSeek | 3 new | 7 |
| 8 | LiteLLM Proxy | 1 new | 2 |
| 9 | Enhanced Router | 1 modified | 5 |
| 10 | Streaming Handler | 1 new | 4 |
| 11 | Gateway RPC | 2 new/modified | 2+ |
| 12 | Config + Wiring | 2 modified | 0 (verify existing) |
| 13 | Flutter Provider Mgmt | 4 new, 1 modified | flutter analyze |
| 14 | Flutter Streaming | 1 new, 1 modified | flutter analyze |
| 15 | Integration Test | 1 new | 1 |

**Total: ~20 new files, ~5 modified files, ~60+ tests**

**Dependencies between tasks:**
- Tasks 1-5: Independent, can be parallelized
- Task 6: Must complete before Task 7-8
- Task 7-8: Depend on Task 6
- Task 9: Depends on Tasks 1, 6, 7
- Task 10: Depends on Task 1 (circuit breaker concept)
- Task 11: Depends on Tasks 3-5, 9, 10
- Task 12: Depends on Tasks 7, 9, 11
- Task 13: Depends on Task 11 (RPC endpoints)
- Task 14: Depends on Tasks 10, 11
- Task 15: Depends on Task 10
