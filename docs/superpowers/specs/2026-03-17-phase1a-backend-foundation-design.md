# Phase 1A: Backend Foundation — Design Spec

**Date:** 2026-03-17
**Status:** Draft
**Scope:** Python backend skeleton — FastAPI gateway, LLM router, config system, database layer, memory-ready schema, Docker setup

## 1. Overview

Phase 1A builds the core backend that all subsequent phases plug into. It delivers a working chat system: Flutter (or any WebSocket client) connects, sends a message, gets an LLM response streamed back. No auth, no permissions, no sandbox yet (those are Phase 1B).

### Design Decisions Made

- **Database:** PostgreSQL + Redis (production-grade from day one). **Note:** CLAUDE.md and Plan.md originally specified SQLite, but this was an explicit user decision to go production-grade. Rationale: the 5-layer memory architecture (graph queries, range queries, GIN indexes on arrays, JSONB operators) benefits heavily from PostgreSQL. SQLite lacks native array types, range types, and concurrent write support needed for multi-agent scenarios (Phase 6). CLAUDE.md should be updated to reflect this decision.
- **Auth:** Deferred to 1B (PIN/passphrase with JWT)
- **LLM Providers:** Gemini (free) + Ollama (local) + Groq (free), with smart router
- **Sandbox:** Deferred to 1B (Docker-only now, gVisor-ready abstraction)
- **Protocol:** JSON-RPC 2.0 over WebSocket
- **Memory:** Infinite — everything stored permanently, smart retrieval keeps context bounded

## 2. Architecture

```
Client (Flutter / any WebSocket client)
    |
    | WSS (JSON-RPC 2.0)
    v
FastAPI App (uvicorn)
    |
    +-- WebSocket Handler
    |     JSON-RPC 2.0 dispatch
    |     Method routing
    |     Streaming support
    |
    +-- REST API
    |     GET /health
    |     GET /status
    |     POST /api/chat (HTTP fallback)
    |
    +-- LLM Router (brain/)
    |     Provider abstraction (base class)
    |     GeminiProvider
    |     OllamaProvider
    |     GroqProvider
    |     Smart selection (easy->cheap, hard->strong)
    |     Fallback chain + token counting
    |
    +-- Config Manager (config/)
    |     Pydantic Settings
    |     YAML + .env loading
    |     Runtime reload
    |
    +-- Database Layer (db/)
          SQLAlchemy 2.0 async (PostgreSQL)
          Redis async (sessions, cache)
          Alembic migrations
          Memory-ready schema
```

## 3. JSON-RPC 2.0 WebSocket Protocol

All WebSocket communication uses JSON-RPC 2.0. This aligns with MCP (Phase 6) and gives us a standardized request/response/notification pattern.

### Message Types

**Request** (client -> server, expects response):
```json
{
  "jsonrpc": "2.0",
  "method": "chat.send",
  "params": {
    "message": "What is the weather in Beirut?",
    "conversation_id": "uuid-here"
  },
  "id": 1
}
```

**Response** (server -> client):
```json
{
  "jsonrpc": "2.0",
  "result": {
    "message": "The weather in Beirut is...",
    "model": "gemini-2.0-flash",
    "tokens_used": 142,
    "cost_usd": 0.0
  },
  "id": 1
}
```

**Streaming Notification** (server -> client, no id = no response expected):
```json
{
  "jsonrpc": "2.0",
  "method": "chat.stream",
  "params": {
    "chunk": "The weather",
    "done": false,
    "conversation_id": "uuid-here"
  }
}
```

**Error**:
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid request",
    "data": {"detail": "Missing required field: message"}
  },
  "id": 1
}
```

### Phase 1A Methods

| Method | Direction | Description |
|--------|-----------|-------------|
| `chat.send` | client->server | Send message, get response |
| `chat.stream` | server->client | Streaming response chunks (notification) |
| `chat.history` | client->server | Get conversation history (paginated) |
| `conversation.list` | client->server | List all conversations |
| `conversation.create` | client->server | Create new conversation |
| `system.health` | client->server | Health check |
| `system.status` | client->server | Server status + connected providers |
| `system.authenticate` | client->server | Auth stub (returns `{"authenticated": false}` in 1A, JWT validation in 1B) |

### WebSocket Connection Lifecycle

Phase 1A accepts all connections (no auth). But the handler tracks per-connection state to make Phase 1B auth a non-breaking addition:

1. **Connect:** Client connects to `wss://host/ws`. Server accepts, creates a `ConnectionState` object with `connection_id` (UUID) and `user_id` (null in 1A).
2. **Authenticate (stub):** Client may call `system.authenticate`. In 1A, returns `{"authenticated": false, "message": "Auth not required in this version"}`. In 1B, this method validates JWT and sets `user_id` on the connection state.
3. **Operate:** All JSON-RPC methods work. Methods that need user context (like `chat.history`) use the connection's `user_id` if set, otherwise return all data (1A behavior).
4. **Disconnect:** Server cleans up connection state, flushes any pending writes.

### Standard JSON-RPC 2.0 Error Codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error |
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32000 to -32099 | Application errors (custom) |

Custom application errors:
| Code | Meaning |
|------|---------|
| -32001 | LLM provider unavailable |
| -32002 | All providers failed |
| -32003 | Rate limited |
| -32004 | Conversation not found |

## 4. LLM Router

### Provider Abstraction

```python
class BaseLLMProvider(ABC):
    name: str
    is_local: bool
    cost_per_input_token: float
    cost_per_output_token: float

    @abstractmethod
    async def generate(self, messages, **kwargs) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, messages, **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    async def count_tokens(self, text) -> int: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

### Providers (Phase 1A)

| Provider | Class | Default For | Cost |
|----------|-------|-------------|------|
| Gemini | `GeminiProvider` | Cloud default | Free (15 RPM, 1M tok/day) |
| Ollama | `OllamaProvider` | Local default | $0 (local) |
| Groq | `GroqProvider` | Fast fallback | Free (6K tok/min) |

### Smart Routing Logic

```
1. Classify task complexity (simple heuristic for Phase 1A):
   - Short query (<50 tokens), translation, summary -> EASY
   - Analysis, search, multi-step -> MEDIUM
   - Code generation, reasoning, math -> HARD

2. Select provider:
   EASY   -> Groq (fastest) or Gemini (free)
   MEDIUM -> Gemini
   HARD   -> Gemini (best free) or Ollama (if strong local model loaded)

3. Fallback chain:
   primary_choice -> next_available -> next_available -> Ollama (always last resort)

4. Track per-request:
   - Provider used
   - Input/output tokens
   - Latency (ms)
   - Estimated cost (USD)
```

The router is intentionally simple for Phase 1A. Phase 2 adds ML-based classification, user preference learning, and cost optimization.

## 5. Database Schema (Memory-Ready)

### Design Principles (from research)

The schema is designed to support the full memory architecture from day one, even though Phase 1A only uses basic conversation storage. This avoids migration pain later.

**Research-informed architecture** (5-layer hybrid, see Section 7):
- All messages stored permanently (infinite storage)
- Embedding column ready for ChromaDB sync (Phase 2)
- Metadata JSONB fields for future memory attributes (A-MEM Zettelkasten tags, keywords, links)
- Timestamps on everything for temporal queries (Mem0 temporal reasoning)
- Conversation summaries table for compressed state (ACC bounded state, Focus Knowledge blocks)

### Tables

#### `users`
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
passphrase_hash TEXT NOT NULL
display_name    TEXT
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
last_active_at  TIMESTAMPTZ
settings        JSONB DEFAULT '{}'
```

#### `conversations`
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id         UUID REFERENCES users(id)
title           TEXT
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
metadata        JSONB DEFAULT '{}'
is_archived     BOOLEAN DEFAULT FALSE
```

#### `messages`
Core table — must scale to millions of rows. No TTL, no pruning, no size limits.

```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE
role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system'))
content         TEXT NOT NULL
model_used      TEXT
tokens_input    INTEGER
tokens_output   INTEGER
cost_usd        NUMERIC(12, 8) DEFAULT 0
latency_ms      INTEGER
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
metadata        JSONB DEFAULT '{}'

-- Phase 2 columns (nullable, filled later)
embedding_id    TEXT          -- Reference to ChromaDB embedding
memory_tags     TEXT[]        -- A-MEM Zettelkasten tags
memory_keywords TEXT[]        -- A-MEM keywords for linking
```

Indexes:
```sql
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);
-- Phase 2: GIN index on memory_tags, memory_keywords
```

#### `conversation_summaries` (for ACC/Focus compressed state)
Stores compressed representations of conversation history. Phase 1A creates the table; Phase 2 populates it with auto-generated summaries.

```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE
summary_type    TEXT NOT NULL CHECK (summary_type IN ('rolling', 'knowledge_block', 'episode'))
content         TEXT NOT NULL
first_message_id UUID REFERENCES messages(id)  -- First message covered
last_message_id  UUID REFERENCES messages(id)  -- Last message covered
message_count    INTEGER                        -- Number of messages summarized
token_count     INTEGER
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
metadata        JSONB DEFAULT '{}'
```

#### `memory_nodes` (for A-MEM Zettelkasten network — Phase 2)
Created in Phase 1A migration, populated in Phase 2.

```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id         UUID REFERENCES users(id)
content         TEXT NOT NULL
note_type       TEXT NOT NULL CHECK (note_type IN ('fact', 'preference', 'skill', 'entity', 'episode'))
keywords        TEXT[] NOT NULL DEFAULT '{}'
tags            TEXT[] NOT NULL DEFAULT '{}'
context_description TEXT
embedding_id    TEXT
confidence      REAL DEFAULT 1.0
access_count    INTEGER DEFAULT 0
last_accessed   TIMESTAMPTZ
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
metadata        JSONB DEFAULT '{}'
```

#### `memory_links` (for A-MEM Zettelkasten connections — Phase 2)
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
source_id       UUID REFERENCES memory_nodes(id) ON DELETE CASCADE
target_id       UUID REFERENCES memory_nodes(id) ON DELETE CASCADE
link_type       TEXT NOT NULL CHECK (link_type IN ('related', 'supports', 'contradicts', 'derived_from', 'updates'))
strength        REAL DEFAULT 1.0
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
UNIQUE(source_id, target_id, link_type)
```

#### `procedures` (for MACLA procedural memory — Phase 2)
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id         UUID REFERENCES users(id)
name            TEXT NOT NULL
description     TEXT NOT NULL
steps           JSONB NOT NULL  -- Ordered list of action steps
success_count   INTEGER DEFAULT 0
failure_count   INTEGER DEFAULT 0
bayesian_score  REAL DEFAULT 0.5  -- MACLA reliability score
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
metadata        JSONB DEFAULT '{}'
```

#### `procedure_sources` (join table for procedure-conversation relationship)
```sql
procedure_id    UUID REFERENCES procedures(id) ON DELETE CASCADE
conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE
PRIMARY KEY (procedure_id, conversation_id)
```

#### `llm_usage`
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
provider        TEXT NOT NULL
model           TEXT NOT NULL
tokens_input    INTEGER NOT NULL
tokens_output   INTEGER NOT NULL
cost_usd        NUMERIC(12, 8) NOT NULL DEFAULT 0
latency_ms      INTEGER
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
conversation_id UUID REFERENCES conversations(id)
user_id         UUID REFERENCES users(id)     -- Direct FK for fast per-user cost queries
```

## 6. Config System

### config.yaml
```yaml
server:
  host: "0.0.0.0"
  port: 8000
  debug: false
  cors_origins: ["*"]

llm:
  default_provider: "gemini"
  fallback_chain: ["gemini", "groq", "ollama"]
  providers:
    gemini:
      enabled: true
      model: "gemini-2.0-flash"
    ollama:
      enabled: true
      model: "llama3.1"
      base_url: "http://localhost:11434"
    groq:
      enabled: true
      model: "llama-3.1-70b-versatile"

database:
  postgres_url: "postgresql+asyncpg://nobla:nobla@localhost:5432/nobla"
  redis_url: "redis://localhost:6379/0"

memory:
  context_window_messages: 20  # Recent messages always in context
  max_context_tokens: 8000     # Max tokens for LLM context
  store_embeddings: false       # Phase 2: enable for semantic search
```

### .env (secrets)
```
GEMINI_API_KEY=
GROQ_API_KEY=
DATABASE_URL=postgresql+asyncpg://nobla:nobla@localhost:5432/nobla
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=  # For Phase 1B JWT
```

### Pydantic Settings Model
Single `Settings` class with nested models for each section. Validates on startup, fails fast on misconfiguration. Supports runtime reload for non-critical settings via `POST /api/config/reload`.

## 7. Memory Architecture Design (Research-Informed)

Based on 8 research papers (2023-2026), Nobla uses a **5-layer hybrid memory system**. Phase 1A implements layers 1 and 5. Remaining layers are added in Phase 2.

### The 5 Layers

```
Layer 1: HOT CONTEXT (in LLM prompt)         [Phase 1A]
  |  Inspired by: MemGPT paging, ACC bounded state
  |  What: Last N messages + system prompt
  |  Size: Bounded (~8K tokens max)
  |  Speed: Instant (already in prompt)
  |
Layer 2: WARM GRAPH (fast structured retrieval) [Phase 2]
  |  Inspired by: A-MEM Zettelkasten, Mem0 graph memory
  |  What: Structured notes with dynamic links, tags, keywords
  |  Size: Grows unbounded, retrieval is O(1) by index
  |  Speed: <50ms (PostgreSQL + index)
  |
Layer 3: SEMANTIC STORE (embedding search)      [Phase 2]
  |  Inspired by: Mem0, Agentic RAG
  |  What: ChromaDB vector embeddings of all messages + notes
  |  Size: Grows unbounded
  |  Speed: <100ms (ANN search)
  |
Layer 4: PROCEDURAL MEMORY (learned workflows)  [Phase 2]
  |  Inspired by: MACLA Bayesian selection
  |  What: Extracted procedures with reliability scores
  |  Size: Compact (compressed from trajectories)
  |  Speed: <50ms (filtered query)
  |
Layer 5: COLD ARCHIVE (infinite storage)        [Phase 1A]
     Inspired by: Core principle — store everything
     What: PostgreSQL stores every message, forever
     Size: Unlimited (disk is cheap)
     Speed: Variable (full-text search, pagination)
```

### Phase 1A Memory Flow

```
User sends message
    |
    v
Load hot context:
  - System prompt
  - Last N messages from conversation (configurable, default 20)
  - Total kept under max_context_tokens
    |
    v
Send to LLM Router -> get response
    |
    v
Stream response to client via WebSocket (chunk by chunk)
  While streaming: accumulate chunks in memory buffer
    |
    v
After stream completes (done: true):
  Store user message + full assistant response to PostgreSQL
  (with tokens, cost, latency, model — all metadata)
  Note: If client disconnects mid-stream, still write whatever
  was accumulated to DB (partial responses are still valuable data)
```

### Phase 2 Memory Flow (future, for reference)

```
User sends message
    |
    v
Memory Retrieval Pipeline (parallel):
  1. Hot context: last N messages (always)
  2. Graph search: A-MEM Zettelkasten nodes related to query
  3. Semantic search: ChromaDB top-K similar past messages
  4. Procedural: relevant learned workflows (MACLA)
  5. Knowledge blocks: compressed summaries (Focus/ACC)
    |
    v
Compose prompt = system + retrieved memories + recent messages
  (bounded to max_context_tokens via ACC compression)
    |
    v
LLM Router -> response
    |
    v
Post-response:
  - Store message + response (cold archive)
  - Update/create A-MEM notes (warm graph)
  - Generate embeddings (semantic store)
  - Extract procedures if workflow detected (procedural)
  - Trigger compression if context grew too large (Focus)
```

## 8. Project Structure

```
backend/
+-- nobla/
|   +-- __init__.py
|   +-- main.py                 # Entry point, lifespan management
|   +-- gateway/
|   |   +-- __init__.py
|   |   +-- app.py              # FastAPI app factory, middleware, CORS
|   |   +-- websocket.py        # WebSocket handler, JSON-RPC dispatch
|   |   +-- routes.py           # REST endpoints (health, status, chat)
|   |   +-- protocol.py         # JSON-RPC 2.0 Pydantic models
|   +-- brain/
|   |   +-- __init__.py
|   |   +-- router.py           # LLM Router, provider selection, fallback
|   |   +-- base_provider.py    # Abstract base class for providers
|   |   +-- gemini.py           # Google Gemini provider
|   |   +-- ollama.py           # Ollama local provider
|   |   +-- groq.py             # Groq provider
|   +-- config/
|   |   +-- __init__.py
|   |   +-- settings.py         # Pydantic Settings model
|   |   +-- loader.py           # YAML + .env loading, validation
|   +-- db/
|   |   +-- __init__.py
|   |   +-- engine.py           # SQLAlchemy async engine + Redis setup
|   |   +-- models/
|   |   |   +-- __init__.py     # Re-exports all models
|   |   |   +-- users.py        # User model
|   |   |   +-- conversations.py # Conversation + Message models
|   |   |   +-- memory.py       # memory_nodes, memory_links, procedures (Phase 2)
|   |   |   +-- usage.py        # llm_usage, conversation_summaries
|   |   +-- repositories/
|   |   |   +-- __init__.py
|   |   |   +-- conversation_repo.py  # Conversation + Message CRUD
|   |   |   +-- usage_repo.py         # LLM usage tracking
|   |   +-- migrations/         # Alembic migrations
|   |       +-- env.py
|   |       +-- versions/
+-- tests/
|   +-- conftest.py             # Fixtures (test DB, test client)
|   +-- test_websocket.py       # WebSocket + JSON-RPC tests
|   +-- test_router.py          # LLM router logic tests
|   +-- test_providers.py       # Individual provider tests
|   +-- test_config.py          # Config loading/validation tests
|   +-- test_conversation_repo.py  # Conversation CRUD tests
|   +-- test_usage_repo.py         # Usage tracking tests
+-- config.yaml                 # Default configuration
+-- .env.example                # Example environment variables
+-- Dockerfile
+-- pyproject.toml
+-- alembic.ini
```

**750-line rule enforced:** Every file stays under 750 lines. The split between `app.py`/`websocket.py`/`routes.py`/`protocol.py` (instead of one big gateway file) and `router.py`/`base_provider.py`/individual providers reflects this constraint.

## 9. Docker Setup

### docker-compose.yml
```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://nobla:nobla@postgres:5432/nobla
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: nobla
      POSTGRES_PASSWORD: nobla
      POSTGRES_DB: nobla
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U nobla"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    profiles:
      - local-llm

volumes:
  postgres_data:
  redis_data:
  ollama_data:
```

### Dockerfile (backend)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy full source first (needed for pip install)
COPY . .

# Install dependencies (non-editable for production)
RUN pip install --no-cache-dir "."

EXPOSE 8000
CMD ["uvicorn", "nobla.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Note:** In development, `docker-compose.yml` mounts `./backend:/app` as a volume, so source changes are reflected immediately without rebuilding. For production, build without the volume mount.

## 10. Dependencies (pyproject.toml)

Phase 1A only — minimal set needed:

```toml
[project]
name = "nobla-agent"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    # Web framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",

    # LLM providers
    "google-generativeai>=0.8.0",
    "ollama>=0.3.0",
    "groq>=0.11.0",

    # Database
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "redis>=5.0.0",

    # Config & validation
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "pyyaml>=6.0.2",
    "python-dotenv>=1.0.0",

    # Utilities
    "uuid7>=0.1.0",
    "structlog>=24.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]
```

## 11. What's NOT in Phase 1A

| Deferred To | Feature |
|------------|---------|
| Phase 1B | Authentication (PIN/passphrase + JWT) |
| Phase 1B | 4-tier permission model |
| Phase 1B | Docker sandbox for code execution |
| Phase 1B | Audit logging (OpenTelemetry) |
| Phase 1B | Kill switch |
| Phase 1B | Cost controls (budget limits, auto-shutoff) |
| Phase 1C | Flutter app |
| Phase 1D | End-to-end integration tests |
| Phase 1D | Full docker-compose deployment docs |
| Phase 2 | Memory layers 2-4 (graph, semantic, procedural) |
| Phase 2 | Smart memory retrieval pipeline |
| Phase 2 | Embedding generation |

## 12. Acceptance Criteria

1. `docker-compose up` starts backend + PostgreSQL + Redis successfully
2. WebSocket client connects to `ws://localhost:8000/ws`
3. JSON-RPC `chat.send` sends message and receives streamed LLM response
4. Messages stored in PostgreSQL with all metadata (tokens, cost, model, latency)
5. Conversation history retrievable via `chat.history` (paginated)
6. LLM router tries fallback chain when primary provider is unavailable
7. Config loads from `config.yaml` + `.env`, validates on startup
8. All files under 750 lines
9. Test coverage >80% on gateway and router modules

## 13. References

- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) — Virtual context management
- [Mem0: Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) — Graph memory, 90% token savings
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — Zettelkasten dynamic memory
- [ACC: Agent Cognitive Compressor](https://arxiv.org/abs/2601.11653) — Bounded state, anti-drift
- [Focus: Active Context Compression](https://arxiv.org/abs/2601.07190) — Autonomous pruning
- [MACLA: Hierarchical Procedural Memory](https://arxiv.org/abs/2512.18950) — Bayesian workflow learning
- [Agentic RAG Survey](https://arxiv.org/abs/2501.09136) — RAG pipeline patterns
- [Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564) — Memory taxonomy survey
