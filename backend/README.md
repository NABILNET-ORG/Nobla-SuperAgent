# Nobla Agent — Backend

Python 3.12+ / FastAPI backend for [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent). Provides the gateway, LLM routing, memory engine, voice pipeline, tool platform, and security infrastructure.

## Modules

| Module | Purpose |
|--------|---------|
| `nobla/gateway/` | WebSocket + REST API, JSON-RPC protocol, connection management |
| `nobla/brain/` | LLM router with 6 providers (Gemini, Groq, Ollama, OpenAI, Anthropic, DeepSeek), circuit breakers, complexity-based routing |
| `nobla/memory/` | 5-layer memory engine — episodic (PostgreSQL), semantic (ChromaDB), procedural, knowledge graph (NetworkX), working memory |
| `nobla/voice/` | STT (Whisper + Levantine Arabic), TTS (Fish Speech, CosyVoice, PersonaPlex), VAD, language detection |
| `nobla/tools/` | Tool platform — BaseTool ABC, registry, executor, approval manager. Includes vision, control, code, remote, and search tools |
| `nobla/events/` | Async event bus — pub/sub with fnmatch wildcards, priority dispatch, backpressure (10K queue, urgent bypass) |
| `nobla/channels/` | Channel abstraction — BaseChannelAdapter ABC, ChannelManager, UserLinkingService. Includes Telegram adapter (polling + webhook, MarkdownV2) and Discord adapter (WebSocket gateway, ui.Button views) |
| `nobla/automation/` | NL Scheduled Tasks — NLP time parser (dateparser + recurrent), LLM task interpreter, APScheduler wrapper, user confirmation flow, scheduler service orchestrator |
| `nobla/skills/` | Skill runtime — UniversalSkillAdapter (format detection), SkillSecurityScanner (blocklist, tier escalation, source patterns), SkillToolBridge (registry integration) |
| `nobla/security/` | Auth (JWT + OAuth + API Key), sandbox (Docker/gVisor), audit (OpenTelemetry), permissions (4-tier), kill switch |
| `nobla/persona/` | Emotion detection, persona engine, prompt builder, PersonaPlex integration |
| `nobla/config/` | Centralized Pydantic settings (server, LLM, database, memory, auth, sandbox, voice, persona, tools, vision, computer control, remote control, event bus, channels, telegram, discord, scheduler, skills) |
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

100+ test files across unit and integration tests. Key test areas:
- Security: auth, permissions, sandbox, kill switch, audit
- Brain: router, providers, circuit breakers, streaming
- Memory: all 5 layers, consolidation, retrieval
- Voice: STT, TTS, VAD, pipeline, language detection
- Tools: platform (registry, executor, approval), vision, control, code execution, remote control (SSH/SFTP)
- Events: event bus pub/sub, wildcards, priority, backpressure, overflow (25 tests)
- Channels: adapter lifecycle, manager routing, user linking, pairing codes (31 tests)
- Telegram: settings, MarkdownV2 formatter, media handler, commands, group activation, callbacks (95 tests)
- Discord: settings, formatter, media handler, commands, guild activation, interactions (78 tests)
- Scheduler: NL parser, interpreter, APScheduler wrapper, confirmation flow, service orchestration (76 tests)
- Skills: manifest models, adapter detection, runtime install/uninstall/upgrade, security scanner (39 tests)
- Integration: cross-component event pipeline, tool→bus→subscriber, handler isolation (11 tests)
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

# Remote control (Phase 4D)
REMOTE_CONTROL__ENABLED=true
REMOTE_CONTROL__ALLOWED_HOSTS=["prod.example.com"]
REMOTE_CONTROL__ALLOWED_USERS=["deploy"]

# Event bus (Phase 5-Foundation)
EVENT_BUS__MAX_QUEUE_DEPTH=10000

# Skills (Phase 5-Foundation)
SKILL_RUNTIME__SKILLS_DIR=skills/
SKILL_RUNTIME__MAX_INSTALLED=100

# Telegram (Phase 5A)
TELEGRAM__ENABLED=true
TELEGRAM__BOT_TOKEN=your-bot-token
TELEGRAM__MODE=polling  # or "webhook"

# Discord (Phase 5A)
DISCORD__ENABLED=true
DISCORD__BOT_TOKEN=your-bot-token
DISCORD__COMMAND_PREFIX=!

# Scheduler (Phase 6)
SCHEDULER__ENABLED=true
SCHEDULER__DEFAULT_TIMEZONE=UTC
SCHEDULER__MAX_TASKS_PER_USER=50
```

## Docker

```bash
docker-compose up backend    # Backend only
docker-compose up            # Full stack (backend + PostgreSQL + Redis)
```

## Key Dependencies

FastAPI, uvicorn, websockets, chromadb, sentence-transformers, networkx, faster-whisper, playwright, ollama, google-generativeai, groq, openai, anthropic, apscheduler, dateparser, recurrent, python-telegram-bot, discord.py, pydantic, structlog, docker, asyncssh

---

Part of [Nobla Agent](https://github.com/NABILNET-ORG/Nobla-SuperAgent) by [NABILNET.AI](https://nabilnet.ai)
