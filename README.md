# Nobla Agent

**An open-source, privacy-first AI super agent that unifies 35+ AI agent capabilities with enterprise-grade security.**

Built by [NABILNET.AI](https://nabilnet.ai) | [GitHub](https://github.com/NABILNET-ORG/Nobla-SuperAgent)

---

## What is Nobla Agent?

Nobla Agent is an AI super agent that combines the best capabilities of 35+ existing AI agent projects — while fixing their security vulnerabilities and keeping your data private. It can:

- **Converse** in multiple languages with smart LLM routing (cheap models for easy tasks, powerful models for hard ones)
- **Remember** everything across conversations using a 5-layer memory architecture
- **See** your screen via OCR, UI element detection, and natural language targeting
- **Speak** with customizable voice personas, including native Levantine Arabic support
- **Control** your computer — mouse, keyboard, files, apps, clipboard with 6-layer security
- **Control remote machines** via SSH with connection pooling, SFTP file transfer, and ADMIN-tier security
- **Execute code** in sandboxed Docker containers with package management
- **Search** the web with AI-powered result synthesis
- **Integrate** with 20+ messaging platforms via a unified channel abstraction layer
- **Extend** with a skill marketplace — install, sandbox-scan, and manage community skills at runtime

All processing stays on your machine by default. No cloud required unless you explicitly enable it.

## Architecture

```
Flutter App (Mobile-first UI)
    |
    | WebSocket / HTTPS (TLS)
    v
FastAPI Gateway (Python 3.12+)
    |
    +-- Brain: LLM Router (6 providers, smart routing)
    +-- Memory: 5-layer engine (episodic, semantic, procedural, knowledge graph, working)
    +-- Voice: STT/TTS pipeline (Whisper + Levantine Arabic, Fish Speech, PersonaPlex)
    +-- Tools: Plugin platform (vision, computer control, code execution, remote control, search, and more)
    +-- Events: Async pub/sub event bus (wildcards, priority dispatch, backpressure)
    +-- Channels: Unified channel abstraction (adapter → manager → user linking)
    |     +-- Telegram adapter (polling + webhook, MarkdownV2)
    |     +-- Discord adapter (WebSocket gateway, ui.Button views)
    +-- Automation: NL Scheduled Tasks (dateparser + recurrent + APScheduler + LLM interpreter)
    +-- Agents: Multi-agent orchestrator (design complete — A2A protocol, MCP client/server, workspace isolation)
    +-- Skills: Runtime skill marketplace (install, security scan, universal adapter)
    +-- Security: 4-tier permissions, sandbox, audit trail, kill switch
    +-- Persona: Emotion-aware response styling with customizable personalities
```

**Backend:** Python 3.12+ / FastAPI — 135+ source files, 100+ test files

**Frontend:** Flutter 3.x / Dart — 57 source files with Riverpod state management

**Database:** PostgreSQL + Redis + ChromaDB (vector embeddings)

## Current Status

Nobla Agent is in **active development**. Phases 1-5A + Phase 6 NL Scheduler complete. Multi-Agent System designed (implementation next). 344 tests passing.

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase 1**: Secure Foundation | Complete | Gateway, Auth (JWT + OAuth + API Key), Sandbox (Docker/gVisor), Kill Switch, Flutter chat UI |
| **Phase 2**: Intelligence Core | Complete | LLM Router (6 providers), 5-layer Memory Engine, AI Search with synthesis |
| **Phase 3**: Voice & Persona | Complete | Whisper STT + Levantine Arabic, Fish Speech/CosyVoice TTS, PersonaPlex, Emotion detection, Persona management UI |
| **Phase 4-Pre**: Tool Platform | Complete | BaseTool ABC, Registry, Executor pipeline, Approval Manager, Gateway handlers |
| **Phase 4A**: Screen Vision | Complete | Screenshot capture, OCR (Tesseract + EasyOCR), UI detection, NL element targeting (158 tests) |
| **Phase 4C**: Code Execution | Complete | Sandboxed code.run, package install, LLM codegen, debug assistant, git operations (110 tests) |
| **Phase 4B**: Computer Control | Complete | mouse.control, keyboard.control, file.manage, app.control, clipboard.manage, Flutter approval UI (191 tests) |
| **Phase 4D**: Remote Control | Complete | ssh.connect, ssh.exec, sftp.manage — SSH connection pooling, remote exec, SFTP transfers (116 tests) |
| **Phase 4E**: Flutter Tool UI | Design Complete | Screen mirror, activity feed, tool browser — 12-task plan ready |
| **Phase 5-Foundation** | Complete | Event bus (pub/sub, wildcards, priority, backpressure), channel abstraction, skill runtime, tool event wiring (106 tests) |
| **Phase 5A**: Telegram + Discord | Complete | Telegram adapter (polling + webhook), Discord adapter (WebSocket gateway), MarkdownV2/Markdown formatting, media handlers, pairing/linking, group mention-only, inline buttons (173 tests) |
| **Phase 5**: Channels | In Progress | 15 remaining platform adapters (WhatsApp, Slack, Signal, Teams, etc.) |
| **Phase 6**: NL Scheduler | Complete | NLP time parser (dateparser + recurrent), LLM task interpreter, APScheduler wrapper, user confirmation flow (76 tests) |
| **Phase 6**: Multi-Agent System | Design Complete | BaseAgent, registry, executor, orchestrator, A2A protocol, workspace isolation, MCP client/server, researcher + coder agents — 14-task plan ready |
| **Phase 6**: Automation | In Progress | Webhooks, workflows, community marketplace |
| **Phase 7**: Full Feature Set | Planned | Media, finance, health, social, smart home tools |

## Quick Start

### Prerequisites

- Python 3.12+
- Flutter 3.x
- Docker (for sandbox/code execution)
- PostgreSQL, Redis (or use Docker Compose)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Run
uvicorn nobla.main:app --reload --host 0.0.0.0 --port 8000

# Test
pytest tests/ -v --cov=nobla
```

### Flutter App

```bash
cd app
flutter pub get
flutter run -d <device-id>

# Test
flutter test --coverage
flutter analyze
```

### Full Stack (Docker)

```bash
docker-compose up          # All services
docker-compose up backend  # Backend only
```

## Project Structure

```
nobla-agent/
├── backend/nobla/
│   ├── gateway/        # WebSocket + REST API (FastAPI)
│   ├── brain/          # LLM router (6 providers, smart routing)
│   ├── memory/         # 5-layer memory engine
│   ├── voice/          # STT/TTS pipeline + Levantine Arabic
│   ├── tools/          # Tool platform + vision, control, code, search
│   │   ├── base.py, registry.py, executor.py, approval.py
│   │   ├── vision/     # Screen vision (Phase 4A)
│   │   ├── control/    # Computer control (Phase 4B)
│   │   ├── code/       # Code execution (Phase 4C)
│   │   ├── remote/     # Remote control — SSH/SFTP (Phase 4D)
│   │   └── search/     # AI search engine
│   ├── events/         # Event bus — async pub/sub, wildcards, priority dispatch (Phase 5)
│   ├── channels/       # Channel abstraction + Telegram + Discord adapters (Phase 5A)
│   ├── automation/     # NL Scheduled Tasks — parser, interpreter, scheduler, confirmation (Phase 6)
│   ├── agents/         # Multi-agent orchestrator, A2A protocol, MCP client/server (Phase 6 — design complete)
│   ├── skills/         # Skill runtime — universal adapter, security scanner, tool bridge (Phase 5)
│   ├── security/       # Auth, sandbox, audit, encryption
│   ├── persona/        # Emotion detection + persona engine
│   ├── config/         # Centralized settings
│   └── db/             # Database models + repos
├── app/lib/
│   ├── core/           # Theme, routing, DI (Riverpod)
│   ├── features/       # auth, chat, dashboard, voice, persona, memory, security, tools, settings
│   └── shared/         # Shared widgets, utils
├── backend/tests/      # 95 test files
├── docs/superpowers/   # Design specs + implementation plans
│   ├── specs/          # Approved design specifications
│   ├── plans/          # Step-by-step implementation plans
│   └── prompts/        # Session continuation prompts
└── docker-compose.yml
```

## Key Design Principles

- **Privacy by default** — All data stays on your machine unless explicitly enabled otherwise
- **Security is non-negotiable** — 4-tier permission model (SAFE/STANDARD/ELEVATED/ADMIN), Docker/gVisor sandbox, full audit trail, kill switch
- **Cost conscious** — Defaults to free/cheap LLM options (Gemini free, Groq free, Ollama local), budget controls with auto-shutoff
- **Mobile-first** — APIs designed for mobile UX, Flutter is the primary interface
- **Graceful degradation** — GPU unavailable? CPU mode. Cloud unavailable? Local Ollama. PersonaPlex unavailable? Default TTS
- **750-line hard limit** — No source file exceeds 750 lines. Period.

## LLM Router

The brain routes tasks to the right model based on complexity:

```
Easy (summarize, translate)        -> Gemini free, Groq free
Medium (analysis, search)          -> DeepSeek ($0.14/M tokens)
Hard (code gen, reasoning)         -> GPT-4, Claude
Fallback: primary -> secondary -> tertiary -> local Ollama
```

## Voice Pipeline

```
Audio -> Language Detection -> Arabic? Levantine model : Standard Whisper
      -> LLM Router -> Response -> TTS (Fish Speech / PersonaPlex)
      -> WebSocket stream -> Flutter avatar lip-sync + playback
```

Includes a custom Levantine Arabic Whisper model (`ggml-levantine-large-v3.bin`, 2.9GB) for native dialect support.

## Security Model

| Tier | Access |
|------|--------|
| SAFE | Read-only operations, search |
| STANDARD | Code execution (sandboxed), vision, chat |
| ELEVATED | Package install, git, file operations |
| ADMIN | Mouse/keyboard control, SSH, kill switch |

All actions are audit-logged. Destructive and externally-visible actions require user approval via Flutter dialog.

## Tool Platform

Tools plug into a unified platform with automatic:
- Permission checking (tier-gated)
- User approval (for dangerous actions)
- Audit logging
- Kill switch integration
- Activity feed broadcasting

```python
@register_tool
class MyTool(BaseTool):
    name = "my.tool"
    category = ToolCategory.CODE
    tier = Tier.STANDARD

    async def execute(self, params: ToolParams) -> ToolResult:
        ...
```

## Documentation

| Document | Description |
|----------|-------------|
| `PRD.md` | Full product requirements, competitive analysis |
| `Plan.md` | 7-phase development roadmap |
| `CLAUDE.md` | AI assistant development guide |
| `docs/superpowers/specs/` | Approved design specifications |
| `docs/superpowers/plans/` | Step-by-step implementation plans |

## Contributing

Nobla Agent is open source. Contributions are welcome.

1. Fork the repository
2. Create a feature branch
3. Write tests first (TDD)
4. Ensure all tests pass: `pytest tests/ -v`
5. Keep files under 750 lines
6. Submit a pull request

## License

Open source. See LICENSE for details.

---

Built with care by [NABILNET.AI](https://nabilnet.ai)
