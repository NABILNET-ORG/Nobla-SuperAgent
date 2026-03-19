# Phase 2B Design Spec: LLM Router Enhancements + AI Search

**Date:** 2026-03-19
**Author:** NABILNET.AI
**Status:** Draft
**Scope:** Streaming, OAuth provider auth, circuit breakers, prompt compression, AI search
**Depends on:** Phase 2A (memory system provides retrieval for search integration)
**Research basis:** See `research/phase2-research-synthesis.md`

---

## 1. Overview

Phase 2B upgrades the LLM router from Phase 1 (basic routing + 3 providers) to a production-grade multi-provider system with streaming, OAuth sign-in, circuit breakers, and AI-powered search.

### Goals
- Stream LLM responses token-by-token to Flutter app
- Three connection methods per provider: OAuth sign-in, API key, local model
- Robust fallback with circuit breakers and health monitoring
- AI search with LLM synthesis and source citations
- Prompt compression for cost optimization

### Non-Goals (Phase 2B)
- Voice streaming (Phase 3)
- Tool execution during streaming (Phase 4)
- Multi-agent routing (Phase 6)

---

## 2. Provider Authentication — Three Methods

### 2.1 Architecture

Every LLM provider supports up to three connection methods. Users choose per provider.

```
backend/nobla/brain/
├── router.py              # Enhanced smart router (extends Phase 1)
├── base_provider.py       # Abstract base (extends Phase 1)
├── providers/
│   ├── gemini.py          # Google Gemini (OAuth + API key)
│   ├── openai.py          # OpenAI GPT (OAuth + API key)
│   ├── anthropic.py       # Anthropic Claude (OAuth + API key)
│   ├── groq.py            # Groq (OAuth + API key, extends Phase 1)
│   ├── deepseek.py        # DeepSeek (API key)
│   ├── ollama.py          # Ollama local (endpoint config, extends Phase 1)
│   └── litellm_proxy.py   # LiteLLM unified fallback for 100+ models
├── auth/
│   ├── oauth.py           # OAuth2 flow manager (Google, OpenAI, Anthropic)
│   ├── api_key.py         # API key storage + validation
│   └── local.py           # Local model endpoint management
├── streaming.py           # Token-by-token streaming handler
├── circuit_breaker.py     # Circuit breaker per provider
├── compression.py         # LLMLingua-2 prompt compression
└── token_counter.py       # Cross-provider token counting
```

### 2.2 OAuth Sign-In Flow

```
User taps "Connect Gemini" in Flutter settings
  → Flutter opens OAuth URL in system browser
  → User signs in with Google account
  → Google redirects to callback URL with auth code
  → Backend exchanges code for access + refresh tokens
  → Tokens stored encrypted in PostgreSQL (per user)
  → Provider marked as "connected" via OAuth
  → LLM Router can now use Gemini through user's account
```

**Supported OAuth providers:**
| Provider | OAuth Type | Scopes | Notes |
|----------|-----------|--------|-------|
| Google (Gemini) | Google OAuth 2.0 | `generativelanguage.googleapis.com` | Most users have Google accounts |
| OpenAI | OpenAI OAuth 2.0 | API access | Uses platform.openai.com OAuth |
| Anthropic | Anthropic OAuth 2.0 | API access | Console OAuth flow |
| Groq | Groq OAuth | API access | If available, else API key |

**Token management:**
- Access tokens refreshed automatically before expiry
- Refresh tokens stored AES-256 encrypted in PostgreSQL
- If OAuth token expires and refresh fails → graceful degradation to other providers
- User can disconnect (revoke) any provider from settings

### 2.3 API Key Method

For providers without OAuth or users who prefer API keys:

```
User taps "Use API Key" for Claude
  → Guided wizard shows:
    1. "Go to console.anthropic.com"
    2. "Click API Keys → Create Key"
    3. "Copy the key and paste below"
    (with screenshots/links)
  → User pastes key
  → Backend validates key with a test call
  → Key stored AES-256 encrypted in PostgreSQL
  → Provider marked as "connected" via API key
```

### 2.4 Local Model Method

```
User taps "Add Local Model"
  → Configure: Ollama endpoint URL (default: http://localhost:11434)
  → Backend health-checks the endpoint
  → Lists available models from Ollama
  → User selects default model(s)
  → Provider marked as "connected" via local
```

### 2.5 Unified Provider Interface

```python
class ProviderConnection:
    provider: str           # "gemini", "openai", "anthropic", etc.
    auth_type: AuthType     # OAUTH | API_KEY | LOCAL
    credentials: Encrypted  # OAuth tokens, API key, or endpoint URL
    status: Status          # CONNECTED | DISCONNECTED | ERROR
    health: HealthStatus    # HEALTHY | DEGRADED | DOWN
    last_check: datetime
    latency_ms: float       # Rolling average

class UnifiedProvider(BaseProvider):
    """Wraps any provider with any auth method into a single interface."""
    async def generate(self, messages, **kwargs) -> str: ...
    async def stream(self, messages, **kwargs) -> AsyncIterator[str]: ...
    async def health_check(self) -> bool: ...
    def token_count(self, text: str) -> int: ...
    def cost_estimate(self, input_tokens: int, output_tokens: int) -> float: ...
```

---

## 3. Streaming Architecture

### 3.1 Flow

```
Flutter App ←── WebSocket (JSON-RPC) ──→ Gateway
                                            │
Gateway ←──── SSE / SDK streaming ────→ LLM Provider
```

- **Client ↔ Gateway**: WebSocket (bidirectional, needed for voice in Phase 3)
- **Gateway ↔ LLM Providers**: SSE or provider SDK streaming (OpenAI/Anthropic SDKs stream natively)

### 3.2 Streaming Protocol (JSON-RPC Notifications)

```json
// Stream start
{"jsonrpc": "2.0", "method": "chat.stream.start", "params": {"conversation_id": "uuid", "model": "gemini-2.0-flash"}}

// Token chunks (sent per token or small batch)
{"jsonrpc": "2.0", "method": "chat.stream.token", "params": {"content": "Hello", "index": 0}}
{"jsonrpc": "2.0", "method": "chat.stream.token", "params": {"content": " world", "index": 1}}

// Stream end
{"jsonrpc": "2.0", "method": "chat.stream.end", "params": {"tokens_input": 150, "tokens_output": 42, "cost_usd": 0.0003, "model": "gemini-2.0-flash"}}

// Stream error
{"jsonrpc": "2.0", "method": "chat.stream.error", "params": {"code": -32000, "message": "Provider timeout"}}
```

### 3.3 Cancellation

- Flutter sends `chat.stream.cancel` with conversation_id
- Gateway immediately stops consuming from the LLM provider
- Tokens already generated are kept (partial response saved to episodic memory)
- Cost only incurred for tokens actually generated

### 3.4 Backpressure

- Gateway buffers up to 100 tokens if WebSocket write is slow
- If buffer fills, gateway pauses consuming from LLM (SDK-level pause)
- On WebSocket drain, resume consumption

---

## 4. Circuit Breaker Pattern

### 4.1 States

```
CLOSED (normal) ──→ failures > threshold ──→ OPEN (failing)
    ↑                                            │
    └── success in half-open ←── timeout ────────┘
                                    │
                                HALF_OPEN (testing)
```

### 4.2 Configuration (per provider)

```python
class CircuitBreakerConfig:
    failure_threshold: int = 3        # Failures before opening
    recovery_timeout: float = 30.0    # Seconds before trying half-open
    half_open_max_calls: int = 1      # Test calls in half-open state
    rolling_window: float = 60.0      # Window for counting failures
```

### 4.3 Integration with Router

```python
# Router checks circuit breaker before each provider
for provider in route_order:
    if circuit_breakers[provider].is_available():
        try:
            result = await provider.generate(messages)
            circuit_breakers[provider].record_success()
            return result
        except Exception:
            circuit_breakers[provider].record_failure()
            continue  # Try next provider

# All providers failed
raise AllProvidersDown("No available providers")
```

---

## 5. Smart Routing (Enhanced)

### 5.1 RouteLLM-Inspired Classification

Extend Phase 1's regex-based classification with a lightweight scoring model:

```python
class ComplexityClassifier:
    """Classifies query complexity using multiple signals."""

    def classify(self, message: str, conversation_context: list) -> Complexity:
        scores = {
            "pattern": self._regex_score(message),          # Phase 1 patterns
            "length": self._length_score(message),           # Longer = harder
            "technical": self._technical_score(message),     # Code/math keywords
            "context_depth": self._context_score(conversation_context),  # Multi-turn reasoning
        }
        weighted = sum(w * scores[k] for k, w in self.weights.items())

        if weighted < 0.3: return Complexity.EASY
        if weighted < 0.7: return Complexity.MEDIUM
        return Complexity.HARD
```

### 5.2 Updated Provider Selection

```
EASY   → [Ollama local, Groq free, Gemini free]   (priority: free/local)
MEDIUM → [Gemini (OAuth/free), DeepSeek, Ollama]   (priority: balanced)
HARD   → [Claude (OAuth/API), Gemini Pro, GPT-4o, Ollama (fallback)]
```

Only connected/available providers are considered. If user has only Ollama, everything routes there.

### 5.3 User Overrides

- **Force local**: Only use Ollama (privacy mode)
- **Pin model**: Use specific model for entire conversation
- **Budget cap**: Stop using paid providers after $X
- **Prefer provider**: Always try X first regardless of complexity

---

## 6. Prompt Compression

### 6.1 LLMLingua-2 Integration

Applied to the memory context retrieved by the Phase 2A retrieval pipeline:

```python
async def compress_context(memory_context: str, target_ratio: float = 0.5) -> str:
    """Compress retrieved memory context before injecting into LLM prompt.
    Achieves 3-6x compression with minimal quality loss (ACL 2024)."""
    if len(memory_context) < 200:  # Don't compress short contexts
        return memory_context
    return llmlingua.compress(memory_context, rate=target_ratio)
```

### 6.2 Token Budget Hints

For HARD queries, add a budget hint to the system prompt:
```
"Provide a thorough but focused response in approximately {budget} tokens."
```
This reduces output 3x with minimal quality impact (ACL 2025 Findings).

---

## 7. Token Counting & Cost Tracking

### 7.1 Cross-Provider Token Counting

```python
class TokenCounter:
    def count(self, text: str, provider: str, model: str) -> int:
        if provider == "openai":
            return tiktoken.encoding_for_model(model).encode(text).__len__()
        elif provider == "anthropic":
            return self._anthropic_count(text, model)  # Official API
        elif provider == "gemini":
            return self._gemini_count(text, model)      # countTokens endpoint
        else:
            return tiktoken.get_encoding("cl100k_base").encode(text).__len__()  # Estimate
```

### 7.2 Cost Tracking (extends Phase 1)

- Track cost per message, per conversation, per session, per day, per month
- Separate tracking for OAuth (user's own account) vs API key (Nobla's key)
- Budget warnings at 80% threshold
- Auto-shutoff at budget limit (existing Phase 1 feature)

---

## 8. AI Search

### 8.1 Architecture

```
backend/nobla/tools/search/
├── engine.py          # Search orchestrator
├── searxng.py         # SearxNG integration (free, self-hosted)
├── brave.py           # Brave Search LLM Context API
├── academic.py        # ArXiv + Google Scholar
├── synthesizer.py     # LLM synthesis with citations
└── cache.py           # Search result caching (Redis + ChromaDB)
```

### 8.2 Search Flow

```
User asks a question requiring web knowledge
  │
  ├─ Step 1: CHECK MEMORY FIRST
  │   └─ If memory has a confident answer (score > 0.8), use it
  │
  ├─ Step 2: SEARCH (if memory insufficient)
  │   ├─ SearxNG: parallel query across multiple engines (default)
  │   └─ Brave LLM Context API: if premium enabled ($5/1K queries)
  │
  ├─ Step 3: EXTRACT
  │   └─ Parse results: title, URL, snippet, relevance score
  │
  ├─ Step 4: SYNTHESIZE
  │   └─ LLM generates answer from search results + memory context
  │   └─ Every claim linked to source URL + snippet
  │
  ├─ Step 5: CACHE
  │   ├─ Redis: cache search results for 24h (avoid duplicate searches)
  │   └─ ChromaDB: store synthesized facts in semantic memory
  │
  └─ Step 6: RESPOND
      └─ Answer with inline citations: "According to [1] and [2]..."
```

### 8.3 Search Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| Quick | 1 query, top 5 results, fast synthesis | Simple factual questions |
| Deep | Follow links, extract page content, detailed analysis | Research questions |
| Wide | Multiple queries, diverse sources, comparison | "Compare X vs Y" |
| DeepWide | Combines depth + breadth (most thorough) | Complex research |

### 8.4 SearxNG Integration

```yaml
# docker-compose.yml addition
searxng:
  image: searxng/searxng:latest
  ports:
    - "8888:8080"
  environment:
    - SEARXNG_SECRET=<generated>
  volumes:
    - ./searxng:/etc/searxng
```

SearxNG API endpoint: `http://localhost:8888/search?q={query}&format=json`

### 8.5 Brave LLM Context API

```python
# Brave's API returns actual page content (not just snippets)
# <600ms P90 latency, powers 22M answers/day internally
async def brave_search(query: str, count: int = 5) -> list[SearchResult]:
    response = await httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": api_key},
        params={"q": query, "count": count, "extra_snippets": True}
    )
    return parse_brave_results(response.json())
```

---

## 9. Flutter App Updates

### 9.1 Provider Management Screen

```
Settings → LLM Providers
  ├─ Gemini          [Connected via Google Sign-In] ✅
  ├─ Claude          [Connected via API Key]        ✅
  ├─ GPT-4           [Not Connected]                ⚪ [Connect]
  ├─ Groq            [Connected via API Key]        ✅
  ├─ DeepSeek        [Not Connected]                ⚪ [Connect]
  ├─ Ollama (Local)  [Connected: llama3.1]          ✅
  └─ [+ Add Provider]
```

Each provider card shows:
- Connection method (OAuth / API Key / Local)
- Status (Connected / Error / Down)
- Latency (rolling avg)
- Cost this session / today / month
- [Disconnect] / [Reconfigure] actions

### 9.2 OAuth Flow in Flutter

```dart
// Uses url_launcher to open OAuth URL in system browser
// Deep link callback returns to app with auth code
// App sends code to backend for token exchange
Future<void> connectProvider(String provider) async {
  final authUrl = await rpcClient.call('provider.oauth_url', {'provider': provider});
  await launchUrl(Uri.parse(authUrl));
  // Deep link handler receives callback
}
```

### 9.3 Search UI

- Search bar in chat (detected automatically or via explicit /search command)
- Results displayed as cards with: title, source, snippet, relevance
- Citations shown inline in response: "[1]", "[2]" with expandable source list
- Search mode selector: Quick / Deep / Wide / DeepWide

### 9.4 Streaming Display

- Messages render token-by-token as they arrive
- Typing indicator shows which model is generating
- Cost badge updates in real-time during generation
- Cancel button appears during streaming

### 9.5 New JSON-RPC Methods

| Method | Auth | Description |
|--------|------|-------------|
| `provider.list` | Required | List all providers with connection status |
| `provider.oauth_url` | Required | Get OAuth URL for a provider |
| `provider.oauth_callback` | Required | Exchange auth code for tokens |
| `provider.connect_apikey` | Required | Validate and store API key |
| `provider.connect_local` | Required | Configure local model endpoint |
| `provider.disconnect` | Required | Revoke/remove provider credentials |
| `provider.health` | Required | Health check a specific provider |
| `search.query` | Required | Execute search with mode selection |
| `search.modes` | Required | List available search modes |
| `chat.stream.cancel` | Required | Cancel an in-progress stream |

---

## 10. Dependencies (New)

### Backend
| Package | Purpose | Cost |
|---------|---------|------|
| `litellm` | Unified provider abstraction (100+ models) | Free |
| `tiktoken` | OpenAI token counting | Free |
| `llmlingua` | Prompt compression (LLMLingua-2) | Free |
| `httpx` | Async HTTP for search APIs | Free |
| `authlib` | OAuth2 client flows | Free |

### Flutter
| Package | Purpose | Cost |
|---------|---------|------|
| `url_launcher` | Open OAuth URLs in system browser | Free |

---

## 11. Testing Strategy

### Unit Tests
- `test_streaming.py` — Token streaming, cancellation, backpressure
- `test_circuit_breaker.py` — State transitions, recovery, rolling window
- `test_oauth.py` — Token exchange, refresh, revocation
- `test_complexity.py` — Classification accuracy across query types
- `test_compression.py` — LLMLingua-2 compression ratio + quality
- `test_token_counter.py` — Cross-provider counting accuracy
- `test_search_engine.py` — SearxNG + Brave integration
- `test_synthesizer.py` — Citation generation, source linking

### Integration Tests
- `test_streaming_flow.py` — Full stream from provider through WebSocket to assertions
- `test_oauth_flow.py` — End-to-end OAuth with mock provider
- `test_search_memory.py` — Search results cached in memory, retrieved later
- `test_fallback_chain.py` — Provider failure → circuit break → fallback

### Coverage Target
- Backend router/search: 85%+
- Flutter new screens: 80%+

---

## 12. Performance Targets

| Operation | Target |
|-----------|--------|
| TTFT (time to first token) | <500ms for API, <1s for local |
| Streaming throughput | Match provider speed (no gateway bottleneck) |
| Circuit breaker detection | <3 failures within 60s |
| OAuth token refresh | <2s, transparent to user |
| Search (Quick mode) | <2s total (search + synthesis) |
| Search (Deep mode) | <10s total |
| Prompt compression | <200ms for typical memory context |

---

## 13. Security Considerations

- OAuth tokens encrypted AES-256 at rest in PostgreSQL
- API keys encrypted AES-256 at rest
- OAuth refresh tokens never exposed to Flutter app (backend-only)
- Search queries logged in audit trail
- SearxNG runs locally (no data sent to external search engines beyond the query itself)
- Brave API key stored server-side only
- Provider credentials scoped per user (no cross-user access)

---

## 14. Phase 2B Sub-phases

### 2B-1: Streaming + Provider Auth (~1 week)
- Streaming protocol implementation
- OAuth flows for Google/OpenAI/Anthropic
- API key guided wizard
- Circuit breaker pattern
- Flutter provider management screen

### 2B-2: Search + Polish (~1 week)
- SearxNG Docker integration
- Brave Search API integration
- LLM synthesis with citations
- Search + memory integration (check memory first, cache results)
- Prompt compression (LLMLingua-2)
- Flutter search UI
- Comprehensive tests
