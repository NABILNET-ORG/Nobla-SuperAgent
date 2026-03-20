# Nobla Agent — Super Agent Master Plan

## Context

**Problem:** Current AI agents (OpenClaw, CoPaw, Auto-GPT, etc.) suffer from critical security vulnerabilities, complex setup, runaway costs, unreliable execution, and fragmented capabilities. No single agent does everything well. Users want ONE reliable, secure, super-capable agent.

**Solution:** Nobla Agent — an open-source, privacy-first, ultra-capable AI super agent that:
- Fixes every problem users complained about in existing agents
- Combines the best of OpenClaw + CoPaw + Vane + 30 other projects
- Controlled primarily via a Flutter mobile app with voice (PersonaPlex)
- Supports every messaging channel as alternative interfaces
- Runs locally, on VPS, or hybrid — user chooses
- Free/low-cost with multi-LLM support (local + API)

**Inspired by research on:** OpenClaw (319K stars), CoPaw (12.4K), Vane (33.1K), UI-TARS (27K), Open WebUI (65K), Khoj (32.8K), Agent Zero (13.5K), Letta/MemGPT (15K), CrewAI (44.5K), Dify (100K), n8n (179K), and 25+ other projects.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   FLUTTER MOBILE APP                     │
│  (Primary Interface — Chat, Voice, Avatar, Dashboard)    │
└──────────────────────────┬──────────────────────────────┘
                           │ WebSocket / HTTPS
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    NOBLA GATEWAY                         │
│              (Python — Control Plane)                     │
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Auth &   │ │ Session  │ │ Channel  │ │  Audit     │ │
│  │ Security │ │ Manager  │ │ Router   │ │  Logger    │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Cron &   │ │ Webhook  │ │ Cost     │ │  Kill      │ │
│  │ Scheduler│ │ Manager  │ │ Control  │ │  Switch    │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  BRAIN       │ │  MEMORY      │ │  TOOLS               │
│  (LLM Router)│ │  (Advanced)  │ │  (Capabilities)      │
│              │ │              │ │                       │
│ • Ollama     │ │ • Episodic   │ │ • Browser Control    │
│ • Gemini API │ │ • Semantic   │ │ • Screen Vision      │
│ • DeepSeek   │ │ • Procedural │ │ • File Manager       │
│ • Groq       │ │ • Knowledge  │ │ • Code Executor      │
│ • OpenAI     │ │   Graph      │ │ • Search (Brave+     │
│ • Claude     │ │ • RAG        │ │   SearXNG)           │
│ • Any LLM    │ │ • ChromaDB/  │ │ • MCP Client/Server  │
│              │ │   SQLite     │ │ • SSH Remote Control  │
│ Smart Router:│ │              │ │ • API Hub             │
│ Hard→Strong  │ │              │ │ • Email/Calendar      │
│ Easy→Cheap   │ │              │ │ • Smart Home          │
└──────────────┘ └──────────────┘ │ • Media Generation   │
                                  │ • OCR/Documents      │
              ┌───────────────────│ • Database Manager    │
              ▼                   │ • System Monitor      │
┌──────────────────┐              │ • Web Scraper         │
│  VOICE ENGINE    │              │ • Social Media        │
│                  │              │ • Finance Tracker     │
│ Premium:         │              │ • + 50 more skills    │
│ • PersonaPlex    │              └──────────────────────┘
│ Default:         │
│ • Faster-Whisper │        ┌──────────────────────┐
│   (+ Levantine)  │        │  CHANNELS            │
│ • Fish Speech/   │        │                       │
│   CosyVoice TTS  │        │ • Telegram            │
│ • Emotion detect │        │ • Discord             │
│   (Hume AI)      │        │ • WhatsApp            │
└──────────────────┘        │ • Slack               │
                            │ • Signal              │
┌──────────────────┐        │ • iMessage            │
│  MULTI-AGENT     │        │ • MS Teams            │
│                  │        │ • Matrix              │
│ • Agent Cloning  │        │ • WebChat             │
│ • Sub-agents     │        │ • + 15 more           │
│ • A2A Protocol   │        └──────────────────────┘
│ • CrewAI-style   │
│   role-based     │        ┌──────────────────────┐
│ • Parallel exec  │        │  SANDBOX             │
└──────────────────┘        │                       │
                            │ • Docker isolation    │
                            │ • gVisor/Firecracker  │
                            │ • Per-tool sandboxing │
                            │ • Network isolation   │
                            └──────────────────────┘
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Backend/Gateway** | Python 3.12+ (FastAPI + WebSocket) | Best AI/ML ecosystem, PersonaPlex compat |
| **Mobile App** | Flutter/Dart | Cross-platform (iOS + Android), single codebase |
| **LLM Local** | Ollama | Supports all open models, easy API |
| **LLM API** | Gemini (free), Groq (free), DeepSeek (cheap) | Cost optimization |
| **STT** | Faster-Whisper + Levantine model (Arabic) | 4x faster than Whisper, your custom model |
| **TTS** | Fish Speech V1.5 / CosyVoice2 (open source) | Free, voice cloning, multilingual |
| **Voice Premium** | PersonaPlex 7B (on server) | Full-duplex real-time conversation |
| **Search** | Brave Search API + SearXNG | Quality + privacy + free fallback |
| **Memory DB** | ChromaDB (vectors) + SQLite (structured) | Local, free, fast |
| **Knowledge Graph** | NetworkX + SQLite | Local graph storage |
| **Sandbox** | Docker + gVisor | Industry standard, OWASP recommended |
| **Screen Vision** | UI-TARS / screenshot analysis | State-of-the-art GUI understanding |
| **MCP** | MCP protocol (client + server) | Industry standard for tool integration |
| **Channels** | python-telegram-bot, discord.py, etc. | Mature libraries |
| **Cron** | APScheduler | Python-native scheduling |
| **OCR** | Tesseract + EasyOCR | Free, multilingual |
| **Image Gen** | Stable Diffusion (local) / DALL-E API | Free local + API option |

---

## Security Architecture (Fixing OpenClaw's Failures)

Based on OWASP Top 10 for Agentic Applications + OpenClaw CVEs:

### 4-Tier Security Model
```
TIER 1: SAFE (Default)
├── Read-only operations
├── Search, summarize, answer questions
├── No file modifications
├── No code execution
├── No network requests (except search)
└── No system commands

TIER 2: STANDARD
├── File read/write in designated folders
├── Code execution in sandbox only
├── Web browsing (controlled)
├── API calls (whitelisted)
└── Requires initial user approval

TIER 3: ELEVATED
├── Full file system access
├── Code execution with network
├── Install packages
├── Git operations
├── SSH to remote machines
└── Each action needs mobile app approval (2FA-style)

TIER 4: ADMIN
├── Full system control
├── Keyboard/mouse control
├── Screen recording
├── Process management
├── System configuration changes
└── Every action logged + needs approval + can be undone
```

### Security Features
- **Sandbox execution** — All code runs in Docker/gVisor containers, never on bare metal
- **Audit logging** — OpenTelemetry-compatible, every action logged with timestamp, user, result
- **Kill switch** — Instant stop from mobile app, emergency shutdown
- **Cost controls** — Per-session token budget, daily spending limit, automatic shutoff
- **Rate limiting** — Prevent runaway loops (max iterations per task)
- **Input sanitization** — Defend against prompt injection (structured output validation)
- **Marketplace vetting** — Skills require code review + malware scan (VirusTotal integration)
- **Encrypted storage** — All secrets/memory encrypted at rest (AES-256)
- **Network isolation** — Sandbox has no access to host network by default
- **Undo system** — Every file/system change can be rolled back

---

## Development Phases

### Phase 1: Secure Foundation (Weeks 1-4)
**Goal:** Build the secure backbone that everything else sits on.

**Backend:**
- [ ] Project setup: Python 3.12+, FastAPI, pyproject.toml, Docker
- [ ] Gateway server: WebSocket + REST API
- [ ] Authentication: JWT tokens, API keys, session management
- [ ] 4-tier security model implementation
- [ ] Sandbox system: Docker container management for code execution
- [ ] Audit logging: OpenTelemetry-compatible event logging
- [ ] Kill switch: Emergency stop endpoint
- [ ] Cost control: Token counting, budget limits, auto-shutoff
- [ ] Configuration system: YAML/TOML config with .env support
- [ ] Basic LLM integration: Ollama + one API provider (Gemini)

**Flutter App:**
- [ ] Project setup: Flutter 3.x, clean architecture (MVVM)
- [ ] Auth flow: Login, registration, JWT token management
- [ ] WebSocket connection to Gateway
- [ ] Basic chat UI: Text messages, send/receive
- [ ] Dashboard: Agent status, security level selector
- [ ] Settings: Server URL, LLM selection, security preferences
- [ ] Push notifications: Firebase Cloud Messaging
- [ ] Kill switch button: Emergency stop

**Testing:**
- [ ] Unit tests for Gateway, Auth, Sandbox
- [ ] Integration test: Flutter app ↔ Gateway communication
- [ ] Security test: Sandbox escape attempts, injection tests

---

### Phase 2A: Memory System + Conversation Persistence (Weeks 5-7)
**Goal:** Make the agent remember, learn, and persist conversations.
**Design spec:** `docs/superpowers/specs/2026-03-19-phase2a-memory-conversation-design.md`
**Research basis:** 80+ papers (2024-2026). See `research/phase2-research-synthesis.md`

**5-Layer Memory Engine (Layered Pipeline Architecture):**
- [ ] Memory orchestrator: thin coordinator routing to independent layers
- [ ] Working memory: context window management with token budgeting
- [ ] Episodic memory: conversation storage + full-text search (PostgreSQL GIN)
- [ ] Semantic memory: fact extraction + vector embeddings (ChromaDB + PostgreSQL)
- [ ] Procedural memory: learned workflows + Bayesian Beta scoring (MACLA-inspired)
- [ ] Knowledge graph: entity relationships via NetworkX (LazyGraphRAG, incremental)
- [ ] Hybrid retrieval: 0.7 semantic + 0.3 BM25 keyword + lightweight re-ranking
- [ ] Memory scoring: recency decay + importance + relevance + access frequency

**Three Processing Paths:**
- [ ] Hot path: per-message, <50ms, spaCy NER + keywords + embedding (no LLM call)
- [ ] Warm path: post-conversation, async LLM extraction of facts/entities/procedures
- [ ] Cold path: nightly maintenance — decay, dedup, prune, graph rebuild (APScheduler)

**Conversation Persistence:**
- [ ] Tree-structured messages (parent_message_id for future branching)
- [ ] Conversation lifecycle: create, resume, switch, archive
- [ ] Conversation search: full-text + semantic across all history
- [ ] Observation masking: tool outputs hidden from context, action kept (NeurIPS 2025)
- [ ] Rolling summary: compress older messages when context window overflows

**Skill & Plugin Schema (Foundation for Phase 6 Marketplace):**
- [ ] Skill manifest (skill.json) + SKILL.md prompt format
- [ ] Plugin manifest (plugin.json) with skills/agents/hooks/commands
- [ ] Directory structure: bundled/ + community/ + custom/
- [ ] Marketplace entry schema (data model only, no UI yet)

**Flutter App Updates:**
- [ ] Conversation drawer: sidebar with list, search, grouping by date
- [ ] Memory viewer screen: facts, entities, procedures tabs
- [ ] Dashboard memory stats card
- [ ] Community tab placeholder ("Coming Soon")
- [ ] Memory settings: context budget, warm path timeout, retention period

**New JSON-RPC Methods:**
- [ ] conversation.list, conversation.get, conversation.search
- [ ] conversation.delete (soft), conversation.rename
- [ ] memory.search, memory.facts, memory.graph, memory.stats

---

### Phase 2B: LLM Router Enhancements + Search (Weeks 8-9)
**Goal:** Upgrade the LLM router with streaming, OAuth provider auth, and add AI search.
**Design spec:** `docs/superpowers/specs/2026-03-19-phase2b-router-search-design.md`

**Multi-LLM Router Enhancements:**
- [ ] Streaming responses: token-by-token via WebSocket (SSE internally to providers)
- [ ] Provider auth — three connection methods per provider:
  - [ ] OAuth sign-in: "Sign in with Google" for Gemini, OAuth for OpenAI/Anthropic
  - [ ] API key: guided setup wizard with step-by-step instructions
  - [ ] Local model: Ollama endpoint configuration
- [ ] All three methods coexist — user picks per provider, router uses all available
- [ ] RouteLLM-inspired complexity classification (matrix factorization approach)
- [ ] Circuit breaker pattern: Closed→Open→Half-Open with rolling latency metrics
- [ ] New providers: Claude (Anthropic), DeepSeek, OpenAI (extends Phase 1 Gemini/Groq/Ollama)
- [ ] Token counting: `tiktoken` + provider-specific tokenizers
- [ ] Prompt compression: LLMLingua-2 for retrieved memory context
- [ ] LiteLLM as provider abstraction layer (100+ models, unified interface)
- [ ] User-configurable model preferences + per-session model pinning

**Smart Search (Brave + SearXNG):**
- [ ] SearXNG Docker integration (self-hosted, free, privacy-first default)
- [ ] Brave Search LLM Context API ($5/1K queries, extracts page content)
- [ ] Agentic RAG: expose 3 retrieval tools (keyword, semantic, chunk) to LLM
- [ ] Search modes: Quick, Deep Search, Wide Search, DeepWide
- [ ] Source citation: every answer links to sources with snippets
- [ ] Academic search: ArXiv, Google Scholar integration
- [ ] Search + Memory integration: check memory before searching, cache results
- [ ] Domain-scoped search

**Flutter App Updates:**
- [ ] Provider management screen: connect/disconnect per provider, status indicators
- [ ] OAuth sign-in flows per provider (Google, OpenAI, Anthropic, etc.)
- [ ] API key guided setup wizard with screenshots and links
- [ ] Search UI: search modes, source display, citations
- [ ] LLM settings: model selector, provider config, cost display per provider
- [ ] Streaming message display: token-by-token text rendering

---

### Phase 3: Voice & Persona (Weeks 9-12)
**Goal:** Add voice interaction and PersonaPlex integration.

**Voice Engine (Default — Free):**
- [ ] Faster-Whisper integration for STT
- [ ] Levantine Arabic model integration (your custom model)
- [ ] Language auto-detection: Arabic → Levantine model, others → standard
- [ ] Fish Speech V1.5 or CosyVoice2 for TTS (open source, voice cloning)
- [ ] Voice activity detection (VAD) for push-to-talk and auto-detect
- [ ] Audio streaming: WebSocket audio pipeline (app → server → app)

**Voice Engine (Premium — PersonaPlex):**
- [ ] PersonaPlex 7B server deployment (Docker)
- [ ] Full-duplex conversation: listen + speak simultaneously
- [ ] Voice prompt conditioning: custom voice character
- [ ] Text prompt conditioning: persona attributes
- [ ] CPU offload mode for smaller GPUs
- [ ] Fallback: if PersonaPlex unavailable → use default pipeline

**Emotion Detection:**
- [ ] Hume AI integration (or open-source alternative)
- [ ] Detect user mood from voice
- [ ] Adapt responses based on emotional context

**Persona System:**
- [ ] Pre-built personas: Professional, Friendly, Military, Custom
- [ ] Custom persona creation: name, voice, personality, language style
- [ ] Persona marketplace: share/download community personas
- [ ] Per-conversation persona switching

**Flutter App Updates:**
- [ ] Voice chat UI: waveform visualization, push-to-talk, auto-detect
- [ ] Avatar display: animated avatar synced with speech (Rive/Lottie)
- [ ] Persona selector: choose/create/customize personas
- [ ] Voice settings: TTS voice, speed, language preferences
- [ ] Background voice mode: talk while app is minimized

---

### Phase 4: Computer Control & Vision (Weeks 13-16)
**Goal:** The agent can see and control the screen like a human.

**Screen Vision:**
- [ ] Screenshot capture and analysis pipeline
- [ ] UI-TARS integration for GUI element detection
- [ ] OCR: Tesseract + EasyOCR for text extraction from screenshots
- [ ] Screen understanding: "What's on screen?" → structured description
- [ ] Element targeting: click coordinates from natural language

**Computer Control:**
- [ ] Mouse control: move, click, drag, scroll
- [ ] Keyboard control: type, shortcuts, key combinations
- [ ] Application launching and management
- [ ] Window management: resize, move, minimize, maximize
- [ ] File manager: browse, create, delete, move, copy files
- [ ] Clipboard management: read/write clipboard

**Code Execution:**
- [ ] Sandboxed code runner: Python, JavaScript, Bash, more
- [ ] Package installation in sandbox
- [ ] Code generation from natural language
- [ ] Debug assistant: analyze errors, suggest fixes
- [ ] Git integration: clone, commit, push, PR creation
- [ ] Project scaffolding: create full projects from description

**Remote Control:**
- [ ] SSH integration: connect to remote machines
- [ ] Remote command execution with audit logging
- [ ] File transfer: upload/download via SCP/SFTP
- [ ] Multi-machine orchestration

**Flutter App Updates:**
- [ ] Screen mirror: see agent's screen in real-time
- [ ] Approval dialogs: approve/deny each computer action
- [ ] Activity feed: live log of what agent is doing
- [ ] Remote machine manager: add/remove SSH connections

---

### Phase 5: Channels & Integrations (Weeks 17-20)
**Goal:** Connect to every messaging platform + productivity tools.

**Messaging Channels:**
- [ ] Telegram bot
- [ ] Discord bot
- [ ] WhatsApp (via WhatsApp Business API or Baileys)
- [ ] Slack bot
- [ ] Signal (via signal-cli)
- [ ] iMessage (via BlueBubbles on macOS)
- [ ] Microsoft Teams
- [ ] Google Chat
- [ ] Matrix
- [ ] IRC
- [ ] Feishu/Lark
- [ ] LINE
- [ ] Mattermost
- [ ] WebChat (browser-based)
- [ ] DingTalk
- [ ] QQ
- [ ] Nostr

**Channel Features:**
- [ ] Unified message format across all channels
- [ ] Media handling: images, audio, video, files across channels
- [ ] Group chat support with activation modes
- [ ] Channel-specific formatting (Markdown, Block Kit, etc.)
- [ ] DM pairing/security (like OpenClaw but better)

**Productivity Integrations:**
- [ ] Email: Gmail, Outlook (read, send, organize, summarize)
- [ ] Calendar: Google Calendar, Apple Calendar (read, create, modify)
- [ ] Notes: Obsidian, Notion, Apple Notes (sync, search, create)
- [ ] Task managers: Todoist, Linear, Jira, Trello
- [ ] Cloud storage: Google Drive, Dropbox, OneDrive

**Flutter App Updates:**
- [ ] Channel manager: enable/disable channels, configure tokens
- [ ] Integration setup wizard: step-by-step connection guides
- [ ] Notification routing: choose which channel gets which alerts

---

### Phase 6: Automation, Multi-Agent & Community Marketplace (Weeks 21-24)
**Goal:** Workflows, cron jobs, multi-agent collaboration, and community skill/plugin marketplace.

**Automation Engine:**
- [ ] Cron jobs: schedule recurring tasks with APScheduler
- [ ] Webhooks: receive and process external events
- [ ] Workflow builder: create multi-step workflows in natural language
- [ ] IFTTT-style triggers: "When X happens, do Y"
- [ ] Batch processing: process multiple files/tasks in parallel
- [ ] Morning/Evening briefings: automated daily reports
- [ ] Report generation: scheduled reports with data aggregation
- [ ] Web scraping: automated data collection from websites
- [ ] Form filling: auto-complete web forms

**Multi-Agent System:**
- [ ] Agent cloning: spawn multiple instances for parallel work
- [ ] Sub-agents: specialized agents for specific tasks
- [ ] Agent-to-Agent communication (A2A protocol)
- [ ] Role-based agents (CrewAI-style): researcher, coder, reviewer
- [ ] Shared memory between agents (configurable isolation)
- [ ] Agent orchestrator: coordinate multi-agent workflows
- [ ] Independent agent workspaces

**MCP Integration:**
- [ ] MCP Client: connect to external MCP servers
- [ ] MCP Server: expose Nobla capabilities to other tools
- [ ] Dynamic tool discovery via MCP
- [ ] MCP marketplace: discover and install MCP servers

**Community Marketplace (Skills + Plugins):**
- [ ] Skill runtime: load and execute user-created skills (SKILL.md + skill.json)
- [ ] Plugin runtime: load plugins with skills/agents/hooks/commands
- [ ] Community backend: user accounts, publishing, versioning, moderation
- [ ] Marketplace API: browse, search, install, rate, review
- [ ] Security audit pipeline: scan published plugins for dangerous patterns
- [ ] Custom skill creator: guided UI for non-developers to create skills
- [ ] Custom plugin creator: developer-focused plugin scaffolding tool
- [ ] Plugin revenue sharing: optional paid plugins with author payments
- [ ] One-tap install: install from marketplace directly in Flutter app
- [ ] Auto-update: version pinning with update notifications
- [ ] Categories: productivity, development, media, automation, finance, health, etc.
- [ ] Author profiles: linked to community accounts with reputation scoring

**Flutter App Updates:**
- [ ] Workflow builder UI: visual workflow creation
- [ ] Cron manager: schedule, edit, delete cron jobs
- [ ] Multi-agent dashboard: see all running agents/sub-agents
- [ ] Automation templates: pre-built common workflows
- [ ] Community tab: browse marketplace, install skills/plugins, rate/review
- [ ] Skill creator screen: guided skill creation for non-developers
- [ ] Plugin manager: installed plugins, updates, settings per plugin
- [ ] My Publications: manage user's published skills/plugins

---

### Phase 7: Full Feature Set (Weeks 25-32)
**Goal:** All remaining features — media, finance, health, social, education.

**Media & Creative:**
- [ ] Image generation: Stable Diffusion (local) / API providers
- [ ] Image editing: crop, resize, filter, background removal
- [ ] Video generation: AI video models integration
- [ ] Music generation: AI music models
- [ ] Presentation builder: auto-create slides from content
- [ ] Document converter: PDF, DOCX, XLSX, PPTX handling

**Finance:**
- [ ] Expense tracking: parse bank notifications, categorize
- [ ] Budget management: monthly budgets with alerts
- [ ] Crypto tracking: portfolio, price alerts
- [ ] Stock tracking: real-time prices, basic analysis
- [ ] Bill reminders: payment due date alerts
- [ ] Price comparison: search for best deals

**Health & Life:**
- [ ] Health data integration: Apple Health, Google Fit
- [ ] Medication reminders: scheduled alerts
- [ ] Meal planning: recipes, grocery lists
- [ ] Exercise suggestions: personalized routines
- [ ] Habit tracking: daily habit monitoring
- [ ] Sleep analysis: patterns and recommendations

**Social Media:**
- [ ] Multi-platform posting: schedule and publish
- [ ] Content calendar: plan content across platforms
- [ ] Engagement monitoring: track comments, likes, mentions
- [ ] Auto-reply: smart responses in your style
- [ ] Reputation monitoring: brand/name mention tracking

**Smart Home:**
- [ ] Home Assistant integration (80+ tools via MCP)
- [ ] Google Home / Alexa integration
- [ ] Automation rules: time, event, condition-based triggers
- [ ] Energy monitoring: track consumption patterns
- [ ] Security cameras: motion alerts, snapshot review

**Education:**
- [ ] AI tutor: explain any topic at your level
- [ ] Flashcard generation: auto-create from content
- [ ] Language practice: conversation in any language
- [ ] Exam prep: generate practice questions
- [ ] Lecture summarization: audio/video → summary + notes

**Travel:**
- [ ] Flight/hotel search: compare prices
- [ ] Trip planning: full itinerary generation
- [ ] Navigation: route suggestions
- [ ] Airport reminders: check-in, gates, delays

**System Administration:**
- [ ] System monitoring: CPU, RAM, disk, network
- [ ] Process management: list, kill, monitor processes
- [ ] Network monitoring: connectivity, speed, security
- [ ] Backup management: scheduled backups
- [ ] Database management: queries, backups, optimization
- [ ] Log analysis: parse and alert on log patterns

**Security Tools:**
- [ ] Dark web monitoring: credential leak alerts
- [ ] Password manager integration: Bitwarden/1Password
- [ ] System security scan: vulnerability detection
- [ ] VPN management: auto-connect based on rules

**Flutter App Updates:**
- [ ] Finance dashboard: expenses, budget, investments
- [ ] Health dashboard: metrics, reminders, trends
- [ ] Social media manager: post, schedule, monitor
- [ ] Smart home control panel
- [ ] System monitoring dashboard

---

## Self-Improvement System

Nobla Agent improves itself over time:

1. **Feedback loops** — User ratings on responses improve future quality
2. **Procedural memory** — Successful workflows are saved and reused
3. **Skill auto-creation** — If a task is repeated 3x, agent creates a reusable skill
4. **Model fine-tuning data** — (Optional) collect interaction data for future model improvements
5. **A/B routing** — Test different models/approaches, keep the better one
6. **Community marketplace** — Open marketplace where users create, share, and install custom skills + plugins (security-audited, rated, versioned). Schema defined in Phase 2A, runtime + UI in Phase 6

---

## Proactive Intelligence

The agent doesn't just respond — it anticipates:

1. **Pattern learning** — Notices your routines and automates them
2. **Smart notifications** — "Your flight is delayed 30 min" before you check
3. **Anomaly detection** — "Unusual $500 charge on your card" alert
4. **Recommendation engine** — Suggests actions based on context
5. **Deadline awareness** — "Your report is due tomorrow, want me to draft it?"
6. **Morning briefing** — Auto-generated daily report at your preferred time

---

## Cost Structure (For End Users)

| Deployment | Monthly Cost | Best For |
|-----------|-------------|----------|
| Full local (Ollama) | $0 | Users with good GPU (8GB+ VRAM) |
| Hybrid (local + free APIs) | $0-5 | Best balance (recommended) |
| Cloud APIs only | $5-30 | Users without GPU |
| Full VPS deployment | $10-50 | Always-on, accessible everywhere |
| PersonaPlex voice | +$30-100 | Premium voice experience |

---

## Deployment Options

### Option A: Local Only
```
User's Computer → Nobla Backend → Ollama (local LLM)
                → Flutter App (same network or Tailscale)
```

### Option B: VPS
```
VPS (cloud) → Nobla Backend → API LLMs
Flutter App → VPS (anywhere in the world)
```

### Option C: Hybrid (Recommended)
```
User's Computer → Nobla Backend → Ollama + API LLMs
                → Relay Server (lightweight, free tier)
Flutter App → Relay Server → Computer
```

---

## Project Structure
```
nobla-agent/
├── backend/                    # Python backend
│   ├── nobla/
│   │   ├── gateway/           # WebSocket + REST API server
│   │   ├── brain/             # LLM router + prompt management
│   │   ├── memory/            # Episodic, semantic, procedural, KG
│   │   ├── tools/             # All tool implementations
│   │   │   ├── browser/       # Browser control
│   │   │   ├── vision/        # Screen capture + UI-TARS
│   │   │   ├── computer/      # Mouse, keyboard, files
│   │   │   ├── search/        # Brave + SearXNG
│   │   │   ├── code/          # Code execution in sandbox
│   │   │   ├── email/         # Email integration
│   │   │   ├── calendar/      # Calendar integration
│   │   │   ├── finance/       # Finance tools
│   │   │   ├── media/         # Image/video/audio generation
│   │   │   ├── social/        # Social media management
│   │   │   ├── smarthome/     # Home Assistant integration
│   │   │   ├── health/        # Health tracking
│   │   │   └── ...
│   │   ├── voice/             # STT + TTS + PersonaPlex
│   │   ├── security/          # Auth, sandbox, audit, encryption
│   │   ├── channels/          # Telegram, Discord, WhatsApp, etc.
│   │   ├── automation/        # Cron, webhooks, workflows
│   │   ├── agents/            # Multi-agent system
│   │   ├── skills/            # Skill platform + marketplace
│   │   └── config/            # Configuration management
│   ├── tests/
│   ├── docker/                # Dockerfiles, compose
│   ├── pyproject.toml
│   └── README.md
│
├── app/                       # Flutter mobile app
│   ├── lib/
│   │   ├── core/             # Theme, routing, DI, config
│   │   ├── features/
│   │   │   ├── auth/         # Login, registration
│   │   │   ├── chat/         # Text + voice chat
│   │   │   ├── dashboard/    # Agent status, controls
│   │   │   ├── voice/        # Voice UI, avatar
│   │   │   ├── persona/      # Persona management
│   │   │   ├── memory/       # Memory viewer
│   │   │   ├── search/       # Search interface
│   │   │   ├── automation/   # Workflows, cron
│   │   │   ├── agents/       # Multi-agent view
│   │   │   ├── channels/     # Channel management
│   │   │   ├── security/     # Security settings
│   │   │   ├── finance/      # Finance dashboard
│   │   │   ├── health/       # Health dashboard
│   │   │   ├── smarthome/    # Smart home controls
│   │   │   ├── social/       # Social media manager
│   │   │   └── settings/     # App settings
│   │   ├── shared/           # Shared widgets, utils
│   │   └── main.dart
│   ├── test/
│   └── pubspec.yaml
│
├── skills/                    # Community skills repository
│   ├── bundled/              # Pre-installed skills
│   └── marketplace/          # Community contributed
│
├── docker-compose.yml         # Full stack deployment
├── docs/                      # Documentation
├── LICENSE                    # MIT or Apache 2.0
└── README.md
```

---

## Verification Plan

### Phase 1 Verification:
1. Start backend: `docker-compose up`
2. Connect Flutter app to backend via WebSocket
3. Send text message → receive LLM response
4. Test all 4 security tiers (Safe → Admin)
5. Test sandbox: run code in Docker container
6. Test kill switch from mobile app
7. Test cost control: set budget, exceed it, verify shutoff
8. Run security tests: injection attempts, sandbox escape

### Phase 2A Verification:
1. Test memory hot path: send messages, verify NER extraction + embedding storage (<50ms)
2. Test episodic memory: have conversation, close app, reopen, verify history retained
3. Test semantic memory: chat about preferences, verify facts extracted after conversation ends
4. Test knowledge graph: mention people/projects, verify entities + relationships in graph
5. Test procedural memory: repeat a workflow 2x, verify procedure created with Bayesian score
6. Test retrieval pipeline: ask about past conversation, verify relevant memories augment prompt
7. Test conversation persistence: list, switch, search, archive conversations
8. Test working memory: long conversation, verify observation masking + rolling summary
9. Test cold path: trigger maintenance, verify decay + dedup + prune
10. Flutter: test conversation drawer, memory viewer, dashboard stats

### Phase 2B Verification:
1. Test streaming: send message, verify token-by-token response via WebSocket
2. Test OAuth: sign in with Google, verify Gemini access via OAuth token
3. Test API key: configure Claude API key, verify routing to Claude for hard tasks
4. Test local model: connect Ollama, verify free routing for easy tasks
5. Test all three coexisting: OAuth Gemini + API Claude + local Ollama, verify router uses all
6. Test circuit breaker: disable a provider, verify fallback to next
7. Test search: query via SearxNG, verify citations + LLM synthesis
8. Test search + memory: search for something, ask again later, verify memory serves it
9. Test prompt compression: verify LLMLingua-2 reduces token count on retrieved context
10. Flutter: test provider management screen, OAuth flows, search UI

### Phase 3 Verification:
1. Test voice: speak → STT → LLM → TTS → hear response
2. Test Arabic: speak Lebanese → verify Levantine model activates
3. Test PersonaPlex: full-duplex conversation (if GPU available)
4. Test persona: switch personas, verify voice + personality change

### Phase 4-7: Each phase has specific integration tests per feature.

---

## Key Differentiators vs Competition

| Problem in Others | Nobla's Solution |
|------------------|------------------|
| OpenClaw's security vulnerabilities (CVE-2026-25253) | 4-tier security + sandbox + audit + encrypted storage |
| OpenClaw's malware marketplace (1000+ malicious skills) | VirusTotal scanning + code review + vetting pipeline |
| Runaway costs ($200+/day) | Token budgets + spending alerts + auto-shutoff + kill switch |
| Complex setup (430K lines) | One-command Docker install + Flutter setup wizard |
| CoPaw's poor built-in skills | Thoroughly tested skill library + community contributions |
| Open Interpreter's no sandbox | All code runs in Docker/gVisor containers |
| Auto-GPT's looping | Max iteration limits + smart loop detection + kill switch |
| No single agent does everything | 100+ tools across 12 categories |
| Voice support is rare/poor | PersonaPlex + Faster-Whisper + open-source TTS + emotion detection |
| No mobile-first experience | Flutter app as primary interface |
| Memory is basic | 4-type memory system + Knowledge Graph + RAG |
| No cost control | Built-in budgets, alerts, and automatic shutoffs |
