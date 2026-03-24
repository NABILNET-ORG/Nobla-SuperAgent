# Nobla Agent — Backend

Python 3.12+ / FastAPI backend for [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent). Provides the gateway, LLM routing, memory engine, voice pipeline, tool platform, and security infrastructure.

## Modules

| Module | Purpose |
|--------|---------|
| `nobla/gateway/` | WebSocket + REST API, JSON-RPC protocol, connection management |
| `nobla/brain/` | LLM router with 6 providers (Gemini, Groq, Ollama, OpenAI, Anthropic, DeepSeek), circuit breakers, complexity-based routing |
| `nobla/memory/` | 5-layer memory engine — episodic (PostgreSQL), semantic (ChromaDB), procedural, knowledge graph (NetworkX), working memory |
| `nobla/voice/` | STT (Whisper + Levantine Arabic), TTS (Fish Speech, CosyVoice, PersonaPlex), VAD, language detection |
| `nobla/tools/` | Tool platform — BaseTool ABC, registry, executor, approval manager. Includes vision and search tools |
| `nobla/security/` | Auth (JWT + OAuth + API Key), sandbox (Docker/gVisor), audit (OpenTelemetry), permissions (4-tier), kill switch |
| `nobla/persona/` | Emotion detection, persona engine, prompt builder, PersonaPlex integration |
| `nobla/config/` | Centralized Pydantic settings (server, LLM, database, memory, auth, sandbox, voice, persona, tools, vision) |
| `nobla/db/` | SQLAlchemy models, repository pattern |

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn nobla.main:app --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
pytest tests/ -v --cov=nobla
```

89 test files across unit and integration tests. Key test areas:
- Security: auth, permissions, sandbox, kill switch, audit
- Brain: router, providers, circuit breakers, streaming
- Memory: all 5 layers, consolidation, retrieval
- Voice: STT, TTS, VAD, pipeline, language detection
- Tools: platform (registry, executor, approval), vision tools
- Gateway: WebSocket, chat flow, RPC handlers

## Configuration

All settings via environment variables or `Settings()` Pydantic class:

```bash
# Required
SECRET_KEY=your-secret-key

# Database
DATABASE__POSTGRES_URL=postgresql+asyncpg://nobla:nobla@localhost:5432/nobla
DATABASE__REDIS_URL=redis://localhost:6379/0

# LLM Providers (configure what you have)
LLM__PROVIDERS__GEMINI__API_KEY=your-key
LLM__PROVIDERS__GROQ__API_KEY=your-key
LLM__PROVIDERS__OLLAMA__BASE_URL=http://localhost:11434

# Optional features
VISION__ENABLED=true
CODE__ENABLED=true
VOICE__STT_MODEL=large-v3
```

## Docker

```bash
docker-compose up backend    # Backend only
docker-compose up            # Full stack (backend + PostgreSQL + Redis)
```

## Key Dependencies

FastAPI, uvicorn, websockets, chromadb, sentence-transformers, networkx, faster-whisper, playwright, ollama, google-generativeai, groq, openai, anthropic, apscheduler, pydantic, structlog, docker

---

Part of [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent) by [NABILNET.AI](https://nabilnet.ai)
