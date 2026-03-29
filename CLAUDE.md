# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nobla Agent** is an open-source, privacy-first AI super agent that unifies 35+ AI agent projects while fixing their security vulnerabilities. Currently in **active development** — Phases 1-4E + Phase 5A + Phase 5B.1 + Phase 6 (NL Scheduler + Multi-Agent System v2 + Webhooks & Workflows + Templates & Import/Export) complete. 1192 tests passing (241 Flutter + 951 backend).

- **PRD.md** — Full product requirements, competitive analysis, feature specs
- **Plan.md** — 7-phase development roadmap with detailed task breakdowns
- **ggml-levantine-large-v3.bin** — Custom Levantine Arabic Whisper model (2.9GB, production-ready)

### Completed Phases
- **Phase 1** (1A/1B/1C): Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat
- **Phase 2** (2A/2B): 5-layer memory engine, LLM router with 6 providers, AI search
- **Phase 3** (3A/3B): Voice pipeline (STT/TTS), Persona engine, PersonaPlex, Management UI
- **Phase 4-Pre**: Tool platform foundation — BaseTool ABC, registry, executor, approval manager
- **Phase 4A**: Screen Vision — screenshot capture, OCR, UI element detection, NL targeting (158 tests)
- **Phase 4B**: Computer Control — mouse.control, keyboard.control, file.manage, app.control, clipboard.manage (191 tests)
- **Phase 4C**: Code Execution — code.run, code.install_package, code.generate, code.debug, git.ops (110 tests)
- **Phase 4D**: Remote Control — ssh.connect, ssh.exec, sftp.manage (116 tests)
- **Phase 4E**: Flutter Tool UI — ToolsScreen with 3-tab TabBar (Mirror/Activity/Browse), shared activity provider, filtered activity feed, mirror provider with subscribe/capture/decode, tool catalog browser with category sections, backend mirror RPC handlers, executor mirror integration (85 Flutter + 9 backend tests)
- **Phase 5-Foundation**: Event bus, channel abstraction, skill runtime, tool event wiring (106 tests)
- **Phase 5A**: Telegram adapter (polling + webhook, 95 tests), Discord adapter (WebSocket gateway, 78 tests)
- **Phase 6-Scheduler**: NL Scheduled Tasks — dateparser + recurrent + LLM interpreter + APScheduler + confirmation flow (76 tests)
- **Phase 6-MultiAgent**: Multi-Agent System v2 — BaseAgent ABC, registry, executor, parallel orchestrator (dependency tiers + asyncio.gather), A2A protocol with capability discovery, depth-limited delegation, workspace isolation, task decomposer with dependency graphs, bridge/cloning, MCP client (stdio + SSE transports) + MCP server (FastAPI SSE endpoints), researcher + coder agents, gateway wiring with kill switch (148 tests)
- **Phase 6-Webhooks**: Webhook system — pluggable signature verification (HMAC-SHA256/SHA1 + custom), inbound/outbound webhooks, exponential retry, dead letter queue with user notifications, health monitoring, REST API (110 tests)
- **Phase 6-Workflows**: Workflow engine — DAG execution (topological sort + asyncio.gather tiers), 6 step types (tool/agent/condition/webhook/delay/approval), named condition branches, trigger matching (fnmatch + payload conditions + dedup), NL interpreter with heuristic fallback, workflow versioning, WorkflowService + REST API, Flutter UI (automation tab, workflow list with filters, webhook management, interactive DAG visualization with tappable nodes + live execution, NL creator with source attribution chips, detail screen) (258 backend + 82 Flutter tests)
- **Phase 6-Templates**: Workflow Templates + Import/Export — WorkflowTemplate model with TemplateCategory enum (8 categories), TemplateStep/TemplateTrigger portable format, WorkflowExportData envelope with `$nobla_version` schema versioning, TemplateRegistry with 5 bundled templates (GitHub CI Notifier, Scheduled Backup, Webhook Relay, Approval Chain, Data Pipeline), search/filter by category/tags/query, export (UUID→ref_id mapping, dedup), import (ref_id→UUID hydration, trigger condition parsing), template instantiation, REST API (6 routes), gateway wiring, Flutter UI (template gallery with search/categories/instantiate, import screen with JSON preview, export bottom sheet with copy) (86 backend + 50 Flutter tests)
- **Phase 5B.1-Learning**: Self-Improving Agent — FeedbackCollector (thumbs + stars + tool chain tracking), PatternDetector (SHA-256 sequence fingerprinting + configurable threshold + max cap), SkillGenerator (macro → skill → publishable lifecycle with security scanning), ABTestManager (epsilon-greedy per-category experiments), ProactiveEngine (configurable aggressiveness + snooze/dismiss/auto-expire with confidence penalties), LearningService orchestrator, LLM Router A/B hook (update_preference/get_preference), REST API (22 routes), gateway wiring with kill switch, Flutter UI (Agent Intelligence screen with 4 tabs, feedback/pattern/suggestion widgets) (106 backend + 24 Flutter tests)

## Architecture (Two Codebases)

**Backend** (Python 3.12+ / FastAPI): Gateway server with WebSocket, LLM router, memory engine, voice pipeline, tool platform, multi-agent orchestrator, 20+ channel integrations, sandbox execution.

**Frontend** (Flutter 3.x / Dart): Mobile-first app with Riverpod state management, real-time WebSocket chat, voice UI with avatar animations, security dashboard with kill switch.

Communication: Flutter app <-> WebSocket/HTTPS (TLS) <-> Python FastAPI gateway.

**Database:** PostgreSQL (structured storage) + Redis (sessions/cache) + ChromaDB (vector embeddings). Originally planned as SQLite but upgraded to PostgreSQL for array types, GIN indexes, JSONB operators, and concurrent write support needed by the 5-layer memory architecture.

## Key Design Constraints

- **750-line hard limit per file**: No code file (`.py`, `.dart`, or any source file) may exceed 750 lines. If a file approaches this limit, split it into smaller, well-named modules. No exceptions.
- **Security is non-negotiable**: 4-tier permission model (SAFE/STANDARD/ELEVATED/ADMIN), all code execution in Docker/gVisor sandbox, full audit trail, kill switch
- **Privacy by default**: All data stays on user's machine unless explicitly enabled otherwise
- **Cost conscious**: Default to free/cheap LLM options (Gemini free, Groq free, Ollama local), budget controls with auto-shutoff
- **Mobile-first**: Design APIs with mobile UX in mind, Flutter is the primary interface
- **Graceful degradation**: GPU unavailable -> CPU mode, PersonaPlex unavailable -> default TTS, cloud unavailable -> local Ollama

## Backend Development

```bash
# Setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Run
uvicorn nobla.main:app --reload --host 0.0.0.0 --port 8000

# Test
pytest tests/ -v --cov=nobla

# Full stack
docker-compose up          # All services
docker-compose up backend  # Backend only
```

Core dependencies: FastAPI, uvicorn, websockets, chromadb, sentence-transformers, networkx, faster-whisper, playwright, ollama, google-generativeai, groq, openai, anthropic, apscheduler, pydantic.

## Flutter Development

```bash
flutter pub get
flutter run -d <device-id>
flutter test --coverage
flutter analyze
dart format lib/
```

Core dependencies: flutter_riverpod, web_socket_channel, dio, flutter_secure_storage, just_audio, record, rive, lottie, go_router.

## Project Structure (Target)

```
nobla-agent/
├── backend/nobla/
│   ├── gateway/        # WebSocket + REST API (FastAPI)
│   ├── brain/          # LLM router (smart routing: hard->strong, easy->cheap)
│   ├── memory/         # Episodic (SQLite), Semantic (ChromaDB), Procedural, Knowledge Graph (NetworkX)
│   ├── voice/          # Faster-Whisper STT (+ Levantine Arabic), Fish Speech/CosyVoice TTS, PersonaPlex
│   ├── tools/          # Tool platform + vision, code, search, etc.
│   │   ├── base.py, registry.py, executor.py, approval.py, models.py  # Tool platform (Phase 4-Pre)
│   │   ├── vision/     # Screen vision: capture, ocr, detection, targeting (Phase 4A)
│   │   ├── code/       # Code execution: runner, packages, codegen, debug, git (Phase 4C)
│   │   ├── control/    # Computer control: mouse, keyboard, files, apps, clipboard (Phase 4B)
│   │   ├── remote/     # Remote control: SSH connect, exec, SFTP manage (Phase 4D)
│   │   └── search/     # AI search engine (Phase 2B)
│   ├── security/       # Auth (JWT), sandbox (Docker/gVisor), audit (OpenTelemetry), encryption (AES-256)
│   ├── events/         # Event bus: async pub/sub, wildcard subscriptions, priority dispatch (Phase 5)
│   ├── channels/       # Channel abstraction + Telegram + Discord adapters (Phase 5A)
│   │   ├── base.py, manager.py, linking.py, bridge.py  # Channel foundation (Phase 5)
│   │   ├── telegram/   # Telegram adapter: polling + webhook, MarkdownV2, media, commands (Phase 5A)
│   │   └── discord/    # Discord adapter: WebSocket gateway, ui.Button views, media, commands (Phase 5A)
│   ├── automation/     # NL Scheduled Tasks + Webhooks + Workflows + Templates (Phase 6)
│   │   ├── parser.py, interpreter.py, scheduler.py, confirmation.py, service.py  # NL Scheduler
│   │   ├── webhooks/   # Webhook system: models, verification, manager, outbound (Phase 6)
│   │   └── workflows/  # Workflow engine: models, executor, trigger_matcher, interpreter, service, templates, template_registry (Phase 6)
│   ├── skills/         # Skill runtime: universal adapter, security scanner, tool bridge (Phase 5)
│   ├── learning/       # Self-improving agent: feedback, patterns, generator, A/B testing, proactive engine (Phase 5B.1)
│   ├── agents/         # Multi-agent orchestrator, A2A protocol, MCP client/server (Phase 6)
├── app/lib/
│   ├── core/           # Theme, routing, DI (Riverpod), network
│   ├── features/       # auth, chat, dashboard, voice, persona, memory, automation, security, settings, tools
│   └── shared/         # Shared widgets, utils
├── skills/             # Bundled + marketplace community skills
└── docker-compose.yml
```

## LLM Router Logic

```
easy_task (summarize, translate)     -> cheap (Gemini free, Groq free)
medium_task (analysis, search)       -> balanced (DeepSeek $0.14/M tokens)
hard_task (code generation, reasoning) -> strong (GPT-4, Claude)
Fallback chain: primary -> secondary -> tertiary -> local Ollama
```

## Voice Pipeline

```
Audio in -> Language Detection -> Arabic? Levantine model : Standard Whisper
         -> LLM Router -> Response -> TTS (Fish Speech / PersonaPlex)
         -> WebSocket stream -> Flutter avatar lip-sync + playback
```

The Levantine model (`ggml-levantine-large-v3.bin`) should be moved to `backend/nobla/voice/models/` during setup.

## Development Phases

1. **Phase 1** (Weeks 1-4): Secure Foundation — Gateway, Auth, Sandbox, Flutter basic chat ✅
2. **Phase 2** (Weeks 5-8): Intelligence Core — Multi-LLM router, memory system, search ✅
3. **Phase 3** (Weeks 9-12): Voice & Persona — STT/TTS, PersonaPlex, avatar ✅
4. **Phase 4** (Weeks 13-16): Computer Control — Screen vision, mouse/keyboard, code sandbox (**4-Pre ✅, 4A ✅, 4B ✅, 4C ✅, 4D ✅, 4E design ✅**)
5. **Phase 5** (Weeks 17-20): Channels & Integrations — 20+ messaging platforms (**5-Foundation ✅, 5A ✅**)
6. **Phase 6** (Weeks 21-24): Automation & Multi-Agent — NL Scheduler ✅, **Multi-Agent design ✅**, workflows, MCP
7. **Phase 7** (Weeks 25-32): Full Feature Set — Media, finance, health, social, smart home

### Phase 4 Sub-phases
| Sub-phase | Status | Scope |
|-----------|--------|-------|
| 4-Pre: Tool Platform | ✅ Complete | BaseTool ABC, registry, executor, approval, gateway handlers |
| 4A: Screen Vision | ✅ Complete | screenshot.capture, ocr.extract, ui.detect_elements, ui.target_element |
| 4C: Code Execution | ✅ Complete | code.run, code.install_package, code.generate, code.debug, git.ops (110 tests) |
| 4B: Computer Control | ✅ Complete | mouse.control, keyboard.control, file.manage, app.control, clipboard.manage (191 tests) |
| 4D: Remote Control | ✅ Complete | ssh.connect, ssh.exec, sftp.manage (116 tests) |
| 4E: Flutter Tool UI | ✅ Complete | Screen mirror, activity feed, tool browser, 6th nav tab, backend mirror handlers (85 Flutter + 9 backend tests) |

### Phase 5 Sub-phases
| Sub-phase | Status | Scope |
|-----------|--------|-------|
| 5-Foundation | ✅ Complete | Event bus (pub/sub, wildcards, priority, backpressure), channel abstraction (base adapter, manager, user linking, bridge), skill runtime (universal adapter, security scanner, tool bridge), tool event wiring, settings models (106 tests) |
| 5A: Telegram + Discord | ✅ Complete | Telegram adapter (polling + webhook, MarkdownV2, media, commands, group mention-only, inline buttons — 95 tests), Discord adapter (WebSocket gateway, ui.Button views, media, commands, guild mention-only, interactions — 78 tests) |
| 5-Channels | In Progress | 15 remaining platform adapters (WhatsApp, Slack, Signal, Teams, etc.) |
| 5B.1-Learning | ✅ Complete | FeedbackCollector (thumbs+stars+tool chain), PatternDetector (fingerprint+threshold), SkillGenerator (macro→skill→publishable), ABTestManager (epsilon-greedy), ProactiveEngine (snooze/dismiss/auto-expire), LearningService, REST API (22 routes), LLM Router A/B hook, Flutter Agent Intelligence screen (106 backend + 24 Flutter tests) |

### Phase 6 Sub-phases
| Sub-phase | Status | Scope |
|-----------|--------|-------|
| 6-Scheduler: NL Scheduled Tasks | ✅ Complete | NLP time parser (dateparser + recurrent), LLM task interpreter with fallback, APScheduler wrapper (add/remove/pause/resume), user confirmation flow with timeout, scheduler service orchestrator, event bus integration (76 tests) |
| 6-MultiAgent: Multi-Agent System v2 | ✅ Complete | BaseAgent ABC, AgentRegistry, AgentExecutor, parallel orchestrator (dependency tiers, asyncio.gather, cascade failure), A2A protocol + capability discovery (Future pattern), depth-limited delegation, AgentWorkspace, MCPClientManager (stdio + SSE transports, JSON-RPC 2.0), MCPServer (FastAPI SSE endpoints), TaskDecomposer (dependency-aware graphs), AgentToolBridge, cloning, researcher + coder agents, gateway wiring with kill switch + MCP router (148 tests) |
| 6-Webhooks | ✅ Complete | Pluggable signature verification (HMAC-SHA256/SHA1 + custom registry), inbound/outbound webhooks, WebhookManager CRUD, exponential retry with dead letter queue + user notifications, health monitoring endpoint, REST API (9 routes), gateway wiring (110 tests) |
| 6-Workflows | ✅ Complete | Workflow models with versioning, DAG execution (topological sort + asyncio.gather tiers), 6 step types (tool/agent/condition/webhook/delay/approval), named condition branches (if/else), trigger matcher (fnmatch + payload conditions + dedup), NL interpreter (LLM + heuristic fallback + nl_source attribution), WorkflowService + REST API (9 routes), gateway wiring with kill switch, Flutter UI: automation tab (7th nav), workflow list with filter chips, webhook management with register form, interactive DAG visualization (CustomPaint edges, tappable nodes, pulsing/dimmed states, bottom sheet with quick actions), NL workflow creator with preview + source attribution chips, workflow detail screen with triggers + DAG + execution history (258 backend + 82 Flutter tests) |
| 6-Templates | ✅ Complete | WorkflowTemplate + TemplateCategory (8 categories), TemplateStep/TemplateTrigger portable format, WorkflowExportData with $nobla_version schema versioning, TemplateRegistry with 5 bundled templates + search/filter, export (UUID→ref_id), import (ref_id→UUID hydration), template instantiation, REST API (6 routes), gateway wiring, Flutter UI: template gallery (search, categories, instantiate dialog), import screen (JSON preview, validation), export sheet (copy to clipboard) (86 backend + 50 Flutter tests) |

## Claude Code Plugins & Skills for Development

### Essential Skills (Use Throughout)
- **/commit** — Git commits with proper messages
- **/commit-push-pr** — Full commit, push, and PR workflow
- **superpowers:brainstorming** — Before creating any feature, explore requirements and design
- **superpowers:writing-plans** — Create implementation plans before touching code
- **superpowers:executing-plans** — Execute plans with review checkpoints
- **superpowers:test-driven-development** — Write tests before implementation (security-critical code needs 90%+ coverage)
- **superpowers:systematic-debugging** — Debug any failures methodically
- **superpowers:verification-before-completion** — Verify work before claiming done
- **superpowers:dispatching-parallel-agents** — Parallelize independent tasks (e.g., backend + Flutter simultaneously)
- **superpowers:subagent-driven-development** — Execute plan tasks via subagents
- **superpowers:finishing-a-development-branch** — Merge/PR workflow when features complete
- **superpowers:requesting-code-review** — Review before merging
- **superpowers:receiving-code-review** — Handle review feedback properly

### Code Quality Skills
- **simplify** — Review changed code for reuse, quality, efficiency
- **code-review:code-review** — Full PR code review
- **pr-review-toolkit:review-pr** — Comprehensive PR review with specialized agents
- **claude-md-management:revise-claude-md** — Keep this file updated as project evolves

### Frontend Development
- **frontend-design:frontend-design** — Create distinctive, production-grade Flutter/web interfaces
- **playground:playground** — Create interactive HTML prototypes for UI exploration

### API & SDK Integration
- **claude-api** — When integrating Claude as an LLM provider in the brain/router
- **stripe:stripe-best-practices** — If adding payment/subscription features later

### Plugin & Agent Development
- **plugin-dev:create-plugin** — Create Claude Code plugins for Nobla development workflow
- **plugin-dev:plugin-structure** — Understand plugin architecture
- **plugin-dev:skill-development** — Create custom skills for the dev workflow
- **plugin-dev:agent-development** — Create specialized subagents
- **plugin-dev:hook-development** — Automated hooks (e.g., pre-commit security checks)
- **plugin-dev:mcp-integration** — MCP server integration (critical for Phase 6)

### Research & Documentation
- **firecrawl:firecrawl-cli** — Web scraping for researching APIs, docs, competitor analysis
- **firecrawl:skill-gen** — Generate skills from documentation URLs
- **context-mode:context-mode** — Process large outputs (test results, logs, build output)
- **huggingface-skills:hf-cli** — Manage ML models on HuggingFace Hub
- **huggingface-skills:hugging-face-model-trainer** — Fine-tune models (relevant for Levantine Arabic model updates)
- **huggingface-skills:transformers.js** — If adding browser-side ML inference

### DevOps & Deployment
- **vercel:setup** / **vercel:deploy** — If deploying web dashboard to Vercel
- **sentry:sentry-sdk-setup** — Error monitoring for both backend and Flutter
- **sentry:sentry-workflow** — Debug production issues
- **chrome-devtools-mcp:chrome-devtools** — Debug web interfaces via Chrome DevTools
- **chrome-devtools-mcp:a11y-debugging** — Accessibility testing for web components

### Automation & Hooks
- **hookify:hookify** — Create hooks to prevent unwanted behaviors
- **hookify:configure** — Enable/disable hook rules
- **update-config** — Configure Claude Code settings, permissions, hooks
- **loop** — Recurring tasks (e.g., run tests every 5 minutes during development)

### MCP Servers to Configure
These MCP servers should be connected for full development capability:
- **dart-flutter** — Flutter/Dart development tools (already connected)
- **marionette** — Flutter app UI testing and automation (already connected)
- **@modelcontextprotocol/server-filesystem** — File operations in sandbox
- **@modelcontextprotocol/server-github** — GitHub integration for PRs, issues
- **@modelcontextprotocol/server-brave-search** — Web search testing
- **@modelcontextprotocol/server-sqlite** — Database operations testing
- **mcp-server-docker** — Container management for sandbox testing

### Agent Types for Parallel Development
Use these subagent types for efficient parallel work:
- **feature-dev:code-architect** — Design feature architectures before implementation
- **feature-dev:code-reviewer** — Review code for bugs, security, quality
- **feature-dev:code-explorer** — Deep codebase analysis and pattern understanding
- **Explore** — Quick codebase searches and file discovery
- **Plan** — Architecture planning and implementation strategy
