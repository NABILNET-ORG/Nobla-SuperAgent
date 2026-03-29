# Changelog

All notable changes to Nobla Agent are documented here.

Built by [NABILNET.AI](https://nabilnet.ai)

---

## [Unreleased] — Phase 5B.2: Universal Skills Marketplace

### Planned
- Marketplace registry with tiered publishing (community auto-approve, verified manual review)
- Dual package format: `.nobla` archive + manifest-pointer (MCP, OpenClaw, Claude, LangChain)
- Discovery: keyword search (PostgreSQL FTS) + semantic search (ChromaDB) + recommendations
- SemVer versioning with update notifications
- Star ratings + usage stats + security scan badge
- 15 REST API routes
- Flutter marketplace screen under Tools tab with search, grid, skill detail

---

## [0.5.1] — 2026-03-29 — Phase 5B.1: Self-Improving Agent

### Added
- **FeedbackCollector** — thumbs up/down + expandable 1-5 star ratings + optional comments, tool chain tracking by correlation_id
- **PatternDetector** — SHA-256 sequence fingerprinting, configurable threshold (3x default), variable parameter extraction, max patterns per user cap
- **SkillGenerator** — 3-tier lifecycle: workflow macro (auto) -> promoted NoblaSkill (user) -> publishable (marketplace-ready), security scanning gate on promotion
- **ABTestManager** — epsilon-greedy variant assignment with per-category epsilon (hard=0.1, medium=0.15, easy=0.2), auto-conclusion on win rate gap > 0.1
- **ProactiveEngine** — configurable aggressiveness (OFF/CONSERVATIVE/MODERATE/AGGRESSIVE), snooze vs dismiss semantics, auto-expire at 5x snooze, confidence penalties (+0.1 accept, -0.2 dismiss, -0.05 soft)
- **LearningService** orchestrator with event bus wiring and kill switch integration
- **LLM Router A/B hook** — `update_preference()` and `get_preference()` methods
- **LearningSettings** in config with per-feature toggles
- **22 REST API routes** under `/api/learning/` (feedback, patterns, macros, experiments, suggestions, settings)
- **Flutter Agent Intelligence screen** — 4 tabs (Overview, Patterns, Auto-Skills, Settings), sub-route under Settings
- **Flutter widgets** — FeedbackWidget (thumbs + stars), PatternCard (status chip + review/dismiss), SuggestionCard (accept/snooze dropdown/dismiss), LearningStatsWidget

### Tests
- 106 backend tests + 24 Flutter tests = 130 new tests
- Total project: 1,192 tests (951 backend + 241 Flutter)

---

## [0.5.0] — 2026-03-28 — Phase 6: Templates & Import/Export

### Added
- **WorkflowTemplate** model with TemplateCategory enum (8 categories)
- **TemplateStep/TemplateTrigger** portable format
- **WorkflowExportData** envelope with `$nobla_version` schema versioning
- **TemplateRegistry** with 5 bundled templates (GitHub CI Notifier, Scheduled Backup, Webhook Relay, Approval Chain, Data Pipeline)
- Search/filter by category, tags, query
- Export (UUID -> ref_id mapping, dedup) and import (ref_id -> UUID hydration)
- Template instantiation
- 6 REST API routes + gateway wiring
- Flutter template gallery, import screen, export bottom sheet

### Tests
- 86 backend + 50 Flutter = 136 new tests

---

## [0.4.0] — 2026-03-28 — Phase 6: Webhooks & Workflows

### Added
- **Webhook system** — pluggable signature verification (HMAC-SHA256/SHA1 + custom registry), inbound/outbound webhooks, exponential retry with dead letter queue, health monitoring
- **Workflow engine** — DAG execution (topological sort + asyncio.gather tiers), 6 step types (tool/agent/condition/webhook/delay/approval), named condition branches, trigger matching
- **NL interpreter** — LLM + heuristic fallback with nl_source attribution
- **Workflow versioning** — bump/rollback/history
- **WorkflowService** + 9 REST routes + gateway wiring with kill switch
- Flutter automation tab (7th nav), DAG visualization, NL creator, workflow detail screen

### Tests
- 258 backend + 82 Flutter = 340 new tests

---

## [0.3.0] — 2026-03-27 — Phase 6: Multi-Agent System v2

### Added
- **BaseAgent ABC**, AgentRegistry, AgentExecutor
- **Parallel orchestrator** — dependency tiers with asyncio.gather, cascade failure
- **A2A protocol** with capability discovery (Future pattern)
- **TaskDecomposer** with dependency-aware graphs
- **MCP client** (stdio + SSE transports, JSON-RPC 2.0) + **MCP server** (FastAPI SSE endpoints)
- **AgentWorkspace** with isolation levels and resource limits
- Researcher + Coder built-in agents
- Gateway wiring with kill switch

### Tests
- 148 backend tests

---

## [0.2.0] — Phase 5: Events, Channels & Skills

### Added
- **Event bus** — async pub/sub, fnmatch wildcards, priority dispatch, backpressure
- **Channel abstraction** — BaseChannelAdapter, ChannelManager, UserLinkingService
- **Skill runtime** — SkillManifest, NoblaSkill ABC, SkillToolBridge, UniversalSkillAdapter (MCP, OpenClaw, Claude, LangChain, Nobla), SkillSecurityScanner
- **Telegram adapter** — polling + webhook, MarkdownV2, media, commands, group mention-only
- **Discord adapter** — WebSocket gateway, ui.Button views, media, commands
- **NL Scheduled Tasks** — dateparser + recurrent + LLM interpreter + APScheduler + confirmation flow

### Tests
- 106 (foundation) + 95 (Telegram) + 78 (Discord) + 76 (scheduler) = 355 tests

---

## [0.1.0] — Phases 1-4E: Foundation + Intelligence + Voice + Tools

### Added
- Gateway (FastAPI + WebSocket), Auth (JWT + OAuth), Sandbox (Docker/gVisor), Kill Switch
- LLM Router (6 providers: Gemini, Groq, Ollama, OpenAI, Anthropic, DeepSeek)
- 5-layer Memory Engine (episodic, semantic, procedural, knowledge graph, working)
- Voice Pipeline (Whisper STT + Levantine Arabic, Fish Speech/CosyVoice TTS, PersonaPlex)
- Persona Engine with emotion detection
- Tool Platform (BaseTool ABC, registry, executor, approval)
- Screen Vision (OCR, UI detection, NL targeting)
- Computer Control (mouse, keyboard, files, apps, clipboard)
- Code Execution (sandboxed runner, package manager, codegen, debug, git)
- Remote Control (SSH connect/exec, SFTP manage)
- Flutter Tool UI (mirror, activity feed, tool browser)
- Flutter app with Riverpod, WebSocket chat, voice UI, security dashboard
