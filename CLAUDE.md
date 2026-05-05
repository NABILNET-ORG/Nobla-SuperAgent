# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nobla Agent** is an open-source, privacy-first AI super agent that unifies 35+ AI agent projects while fixing their security vulnerabilities. Currently in **active development** — Phases 1-4E + Phase 5A + Phase 5B.1-5B.2 + Phase 5-Channels (WhatsApp + Slack + Signal + Teams) + Phase 6 (NL Scheduler + Multi-Agent System v2 + Webhooks & Workflows + Templates & Import/Export) complete. 1723 tests passing (273 Flutter + 1450 backend).

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
- **Phase 5-Channels (WhatsApp)**: WhatsApp Business Cloud API adapter — webhook-only (HMAC-SHA256 signature verification), Graph API media upload/download, interactive messages (reply buttons + lists), keyword commands (!start/!link/!unlink/!status), message status tracking (sent/delivered/read), reaction events, WhatsAppSettings + gateway wiring (94 tests)
- **Phase 5-Channels (Slack)**: Slack adapter — dual mode (Socket Mode WebSocket default + Events API HTTP webhook), Block Kit formatter (headers/code/dividers/buttons), v2 file upload pipeline, slash commands (/nobla start|link|unlink|status) + keyword fallback (!start etc.), RateLimitQueue with Retry-After backoff, thread-aware replies, channel mention-only policy, HMAC-SHA256 signature verification, SlackSettings + gateway wiring (142 tests)
- **Phase 5-Channels (Signal)**: Signal adapter — JSON-RPC daemon transport (signal-cli), plain text formatter, file-path based media with path traversal protection, /start /link /unlink /status commands (case-insensitive), group mention detection, disappearing message TTL honoring, read receipt sending, exponential backoff reconnection, SignalSettings + gateway wiring (72 tests)
- **Phase 5-Channels (Teams)**: Microsoft Teams adapter — Bot Framework REST API (webhook-only), OAuth2 client_credentials token management with auto-refresh, JWT validation (RS256 via cached JWKS, security-first reject-when-unavailable), Adaptive Cards formatter (headings/code/dividers/quotes/buttons), inline base64 media (≤256KB) + hero card links (>256KB), keyword commands (!start/!link/!unlink/!status), mention-only channel policy, conversation reference capture for proactive messaging, multi-tenant support, TeamsSettings + gateway wiring (90 tests)
- **Phase 6-Scheduler**: NL Scheduled Tasks — dateparser + recurrent + LLM interpreter + APScheduler + confirmation flow (76 tests)
- **Phase 6-MultiAgent**: Multi-Agent System v2 — BaseAgent ABC, registry, executor, parallel orchestrator (dependency tiers + asyncio.gather), A2A protocol with capability discovery, depth-limited delegation, workspace isolation, task decomposer with dependency graphs, bridge/cloning, MCP client (stdio + SSE transports) + MCP server (FastAPI SSE endpoints), researcher + coder agents, gateway wiring with kill switch (148 tests)
- **Phase 6-Webhooks**: Webhook system — pluggable signature verification (HMAC-SHA256/SHA1 + custom), inbound/outbound webhooks, exponential retry, dead letter queue with user notifications, health monitoring, REST API (110 tests)
- **Phase 6-Workflows**: Workflow engine — DAG execution (topological sort + asyncio.gather tiers), 6 step types (tool/agent/condition/webhook/delay/approval), named condition branches, trigger matching (fnmatch + payload conditions + dedup), NL interpreter with heuristic fallback, workflow versioning, WorkflowService + REST API, Flutter UI (automation tab, workflow list with filters, webhook management, interactive DAG visualization with tappable nodes + live execution, NL creator with source attribution chips, detail screen) (258 backend + 82 Flutter tests)
- **Phase 6-Templates**: Workflow Templates + Import/Export — WorkflowTemplate model with TemplateCategory enum (8 categories), TemplateStep/TemplateTrigger portable format, WorkflowExportData envelope with `$nobla_version` schema versioning, TemplateRegistry with 5 bundled templates (GitHub CI Notifier, Scheduled Backup, Webhook Relay, Approval Chain, Data Pipeline), search/filter by category/tags/query, export (UUID→ref_id mapping, dedup), import (ref_id→UUID hydration, trigger condition parsing), template instantiation, REST API (6 routes), gateway wiring, Flutter UI (template gallery with search/categories/instantiate, import screen with JSON preview, export bottom sheet with copy) (86 backend + 50 Flutter tests)
- **Phase 5B.1-Learning**: Self-Improving Agent — FeedbackCollector (thumbs + stars + tool chain tracking), PatternDetector (SHA-256 sequence fingerprinting + configurable threshold + max cap), SkillGenerator (macro → skill → publishable lifecycle with security scanning), ABTestManager (epsilon-greedy per-category experiments), ProactiveEngine (configurable aggressiveness + snooze/dismiss/auto-expire with confidence penalties), LearningService orchestrator, LLM Router A/B hook (update_preference/get_preference), REST API (22 routes), gateway wiring with kill switch, Flutter UI (Agent Intelligence screen with 4 tabs, feedback/pattern/suggestion widgets) (106 backend + 24 Flutter tests)
- **Phase 5B.2-Marketplace**: Universal Skills Marketplace — MarketplaceRegistry (publish pipeline with security scan, SemVer versioning, tiered trust COMMUNITY/VERIFIED/OFFICIAL, verification workflow), SkillPackager (.nobla archive + manifest-pointer validation, SHA-256 integrity), SkillDiscovery (keyword search with category/tags/tier/format filters, pagination, pattern-based + similar-to-installed recommendations), UsageTracker (event-driven install_count/active_users/success_rate), MarketplaceService orchestrator, REST API (15 routes), gateway wiring with kill switch, ToolExecutor skill_id payload, Flutter UI (MarketplaceScreen with search + filter chips + recommendations, SkillDetailScreen with stats + versions + ratings, SkillCard/RatingWidget/VersionListWidget) (97 backend + 32 Flutter tests)

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
│   ├── channels/       # Channel abstraction + adapters (Phase 5)
│   │   ├── base.py, manager.py, linking.py, bridge.py  # Channel foundation (Phase 5)
│   │   ├── telegram/   # Telegram adapter: polling + webhook, MarkdownV2, media, commands (Phase 5A)
│   │   ├── discord/    # Discord adapter: WebSocket gateway, ui.Button views, media, commands (Phase 5A)
│   │   ├── whatsapp/   # WhatsApp adapter: Cloud API webhook, Graph API media, interactive messages (Phase 5-Channels)
│   │   ├── slack/      # Slack adapter: Socket Mode + Events API, Block Kit, v2 upload, slash commands (Phase 5-Channels)
│   │   ├── signal/     # Signal adapter: JSON-RPC daemon, plain text, file-path media, disappearing msgs (Phase 5-Channels)
│   │   └── teams/      # Teams adapter: Bot Framework REST API, JWT validation, Adaptive Cards, OAuth2 token mgmt (Phase 5-Channels)
│   ├── automation/     # NL Scheduled Tasks + Webhooks + Workflows + Templates (Phase 6)
│   │   ├── parser.py, interpreter.py, scheduler.py, confirmation.py, service.py  # NL Scheduler
│   │   ├── webhooks/   # Webhook system: models, verification, manager, outbound (Phase 6)
│   │   └── workflows/  # Workflow engine: models, executor, trigger_matcher, interpreter, service, templates, template_registry (Phase 6)
│   ├── skills/         # Skill runtime: universal adapter, security scanner, tool bridge (Phase 5)
│   ├── learning/       # Self-improving agent: feedback, patterns, generator, A/B testing, proactive engine (Phase 5B.1)
│   ├── marketplace/    # Skills marketplace: registry, discovery, packager, stats, service (Phase 5B.2)
│   ├── agents/         # Multi-agent orchestrator, A2A protocol, MCP client/server (Phase 6)
├── app/lib/
│   ├── core/           # Theme, routing, DI (Riverpod), network
│   ├── features/       # auth, chat, dashboard, voice, persona, memory, automation, security, settings, tools, marketplace
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
5. **Phase 5** (Weeks 17-20): Channels & Integrations — 20+ messaging platforms (**5-Foundation ✅, 5A ✅, WhatsApp ✅, Slack ✅, Signal ✅**)
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
| 5-Channels: WhatsApp | ✅ Complete | WhatsApp Business Cloud API adapter — webhook-only, HMAC-SHA256 verification, Graph API media, interactive messages (buttons + lists), keyword commands, status tracking, reaction events, WhatsAppSettings, gateway wiring (94 tests) |
| 5-Channels: Slack | ✅ Complete | Slack adapter — dual mode (Socket Mode WebSocket + Events API HTTP), Block Kit formatter (headers/code/dividers/buttons), v2 file upload, slash commands (/nobla start\|link\|unlink\|status) + keyword fallback, RateLimitQueue with Retry-After, thread-aware replies, channel mention-only, HMAC-SHA256 verification, SlackSettings + gateway wiring (142 tests) |
| 5-Channels: Signal | ✅ Complete | Signal adapter — JSON-RPC daemon (signal-cli), plain text formatter, file-path media with path traversal protection, /start /link /unlink /status (case-insensitive), group mention detection, disappearing message TTL honoring, read receipts, exponential backoff reconnection, SignalSettings + gateway wiring (72 tests) |
| 5-Channels: Teams | ✅ Complete | Microsoft Teams adapter — Bot Framework REST API (webhook-only), OAuth2 client_credentials TokenManager with auto-refresh + asyncio.Lock, JWT validation (RS256 JWKS cached, security-first reject-when-unavailable), Adaptive Cards formatter (headings/code/dividers/quotes/action buttons), inline base64 media ≤256KB + hero card links >256KB, keyword commands (!start/!link/!unlink/!status), mention-only channel policy, conversation reference capture for proactive messaging, multi-tenant support, TeamsSettings + gateway wiring (90 tests) |
| 5-Channels | In Progress | 11 remaining platform adapters (Messenger, LINE, etc.) |
| 5B.1-Learning | ✅ Complete | FeedbackCollector (thumbs+stars+tool chain), PatternDetector (fingerprint+threshold), SkillGenerator (macro→skill→publishable), ABTestManager (epsilon-greedy), ProactiveEngine (snooze/dismiss/auto-expire), LearningService, REST API (22 routes), LLM Router A/B hook, Flutter Agent Intelligence screen (106 backend + 24 Flutter tests) |
| 5B.2-Marketplace | ✅ Complete | MarketplaceRegistry (publish pipeline, SemVer versioning, tiered trust, verification), SkillPackager (.nobla archive + manifest-pointer), SkillDiscovery (keyword search, filters, recommendations), UsageTracker (event-driven stats), MarketplaceService, REST API (15 routes), gateway wiring, Flutter marketplace UI (search, detail, widgets) (97 backend + 32 Flutter tests) |

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

---

## Sovereign Memory Protocol (v2.1)

This repository is bound to the Smart Claude Memory (SCM) Sovereign Memory Protocol. The agent operating here MUST follow these rules; they take precedence over generic boot prompts when in conflict.

### Key Definitions

- **SCM** = Smart-Claude-Memory MCP.
- **Core 3** = `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` — load-bearing project documents.

### Relationship & Personality

The Agent is an **Intellectual Sparring Partner**. Two modes: **Brainstorming** (challenge assumptions, prioritize truth over agreement) and **Execution** (do the work, run the gate, return a 2-paragraph synthesis). When mode is ambiguous, ask once.

### Hard Rules (Hook-Enforced)

Enforced by `hooks/md-policy.py` (PreToolUse on Write/Edit/Bash) — hard-blocks, not advisories.

- **750-Line Ceiling.** Writes that push a file past 750 lines are blocked. Files already over are grandfathered (Edit only). Auto-generated files (`types.ts`, `*.g.dart`, `*.freezed.dart`, `*.arb`) are exempt.
- **Zero-Local-MD.** Only `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` allowed at root.
- **Manual Test Gate.** A `verification-pending.json` lock in `~/.claude-memory/` blocks all Write/Edit/Bash. Release via `confirm_verification({ success: true|false })` — never delete the lock manually.

### Core 3 Integrity (Anti-Corruption)

Modify Core 3 files ONLY via surgical `Edit`. `Write` (full-file replacement) is FORBIDDEN — it destroys context, ordering, and human-authored sections. Decompose substantial restructuring into a sequence of `Edit` calls.

### Branding & Self-Audit

- **Branding.** Every `README.md` MUST link to [NABILNET.AI](https://nabilnet.ai).
- **Decision IDs.** Every `DECISION` save MUST be tagged `SCM-S<N>-D<i>` at the top of the `content` field (e.g., `SCM-S11-D1`).
- **Pre-Wrap Checklist.** Before wrap-up: `npm run build` zero errors, no dead code or stub functions, no `.tmp` artefacts at root.

### Sovereign Taxonomy

Every `save_memory` call MUST set `metadata.type` ∈ {`DECISION` (architectural choices + rationale), `PATTERN` (code standards / cross-project conventions), `ERROR` (bug post-mortems + fixes), `LOG` (general session progress)}. Untyped saves lose GIN-index pre-filter.

### Rule 10 — Sovereign Vetting (runtime-enforced)

`metadata.is_global: true` routes the row to `project_id='GLOBAL'`. The server REJECTS any global save whose `metadata.global_rationale` is missing or under 10 chars (error: `SOVEREIGN VETTING FAILED`). **Cross-Project Test:** if this project were deleted tomorrow, would the memory still be a gold-standard reference for others? If no, keep it local.

### Proactive Sovereign Scout

The Agent actively scouts for global candidates. After major decisions, branding changes, or universal bug fixes, evaluate against the Cross-Project Test. If it passes, propose promotion before saving:

> "This looks like a Global Candidate. Should I save it to GLOBAL? Suggested rationale: *[universal-truth rationale]*."

Never write to GLOBAL silently — promotion always waits on user confirmation.

### Auto-Hygiene (Sovereign Purge)

`init_project` audits token counts on `CLAUDE.md` and the hidden `~/.claude/projects/<encoded>/memory/MEMORY.md`. When either exceeds the bloat threshold (default 10000 tokens), the response includes a `recommendations` entry with `id: "sovereign_purge"`. The Agent MUST:

1. Surface the recommendation and ask for explicit YES/NO consent.
2. On YES: create `docs/scm-memory/`, archive the bloated files there, vectorize via `sync_local_memory({ force: true })`, then regenerate via `ensureSovereignConstitution({ force: true })`.
3. On NO: take no action — the recommendation resurfaces next boot.

Archive, never delete — Supabase vectors keep the on-disk source recoverable.

### Active Retriever Protocol

Before any non-trivial edit (multi-file refactor, new feature, architectural change, or any single-file Edit > ~30 lines), the Agent MUST call `search_memory` with a query summarizing the change AND a `metadata_filter` (`{ type: 'PATTERN' }` for conventions, `{ type: 'DECISION' }` for prior architectural choices, `{ type: 'ERROR' }` for known regression hot spots). Skipping this risks contradicting prior decisions or re-introducing fixed regressions. Trivial edits (typo, single-line change) are exempt.

### SCM Tool Conventions

- `init_project()` — first call of every session; verifies env, hook, MCP registration, dist, Core 3 sync.
- `sync_local_memory()` — second call; aligns vector DB with local notes (incremental, hash-gated).
- `search_memory({ query, metadata_filter })` — typed retrieval; default dual-scope (project + GLOBAL).
- `save_memory({ content, metadata: { type } })` — typed write; never `is_global: true` without `global_rationale`.
- `manage_backlog({ action: "session_end" })` — session close; flushes backlog, regenerates diagrams, runs `sync_artefacts`, emits `next_session_command_markdown`.
- Mandatory delegation: read-heavy investigations (> 3 files OR > 100 lines raw output) go through `delegate_task` with a 2-paragraph synthesis.

### Strategic Context Policy (Orchestrator-Worker)

The Orchestrator (main session) is strategic context only; tactical execution lives in isolated Background Workers.

- **Context Hygiene First.** Orchestrator MUST NOT read large files (> 100 lines) or run multi-file research directly. Reads of that size go through `delegate_task`. Reading ≤ 100 lines for a surgical `Edit` is the only exception.
- **Mandatory Delegation.** Tasks touching > 3 files OR producing > 100 lines of raw output MUST be delegated.
- **Synthesis Only.** Orchestrator accepts only a 2-paragraph synthesis from the Worker. No raw code, full stack traces, or long logs unless the User explicitly asks. Workers summarize compiler errors in ≤ 1 sentence each.
- **Orchestrator Mode.** When `SMART_CLAUDE_MEMORY_ORCHESTRATOR_MODE` is set, all direct Write/Edit/Bash in the main session are forbidden — every unit MUST be delegated. Hard-blocked by `md-policy.py`.

### Session Handoff Protocol — Atomic Wrap-Up Ritual

**Triggers.** Sessions span multiple missions to preserve flow. Wrap-up fires ONLY on:
1. **Context Saturation** — context-window usage > 50%.
2. **Explicit User Command** — "session end", "wrap up", etc.

Task completion alone is NOT a trigger. When fired, execute these five steps in order:

**0. Living Docs Sync.** Call `manage_backlog({ action: "session_end" })` FIRST. Verify both `readme_sync.updated === true` AND `architecture_sync.updated === true` in the response. README's "Recent Progress" and ARCHITECTURE's Mermaid diagrams MUST be current — stale docs ship a lie to the next agent.

**1. Detailed Report.** Write `docs/session-reports/SESSION-N-REPORT.md`: code changes, hurdles + solutions, decisions referencing DECISION IDs.

**2. Auto-Commit.** Stage and commit with message `session: wrap-up Session [N]`. Never end with uncommitted work.

**3. Dynamic Numbering.** Detect current N from the highest `SESSION-N-REPORT.md`; increment for next.

**4. Next Session Command.** The block below MUST be the absolute final output of the session, formatted exactly as:

```
🚀 NEXT SESSION START COMMAND (Copy-Paste)

init_project()
check_system_health()
search_memory({ query: "Active Backlog", project_id: "[current_project_id]", k: 10 })
# Then read docs/NEXT-SESSION-PROMPT.md for the full Session [N+1] plan.
```

---

