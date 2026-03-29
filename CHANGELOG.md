# Changelog

All notable changes to Nobla Agent are documented here.

Built by [NABILNET.AI](https://nabilnet.ai)

---

## [0.6.0] — 2026-03-29 — Phase 5-Channels: Slack + Signal Adapters

### Added
- **Slack adapter** (142 tests) — dual transport mode: Socket Mode (WebSocket, default for privacy-first self-hosted) + Events API (HTTP webhook for hosted deployments)
  - Block Kit formatter — full markdown-to-blocks conversion (headers, code fences, dividers, mrkdwn sections, action buttons with style mapping)
  - v2 file upload pipeline (getUploadURLExternal → PUT → completeUploadExternal)
  - Slash commands: `/nobla start|link|unlink|status` (space-separated sub-commands)
  - Keyword commands: `!start`, `!link`, `!unlink`, `!status` (fallback, consistent with all other adapters)
  - RateLimitQueue — async worker with `Retry-After` header parsing and full-payload re-queue (preserves Block Kit blocks)
  - Thread-aware replies — `thread_ts` propagation, never mirrors to main channel
  - Channel mention-only policy — responds only on `<@BOT_USER_ID>` mention in channels, always in DMs (im/mpim)
  - Socket Mode envelope acknowledgment within 3 seconds before processing
  - HMAC-SHA256 signature verification (`v0=HMAC-SHA256(signing_secret, v0:timestamp:body)`) with 5-minute timestamp staleness check (replay attack protection)
  - Exponential backoff WebSocket reconnect (1s, 2s, 4s... max 30s)
  - `SlackSettings` with mode/token validation + gateway wiring in `_init_channels()`

- **Signal adapter** (72 tests) — JSON-RPC daemon transport via signal-cli (`asyncio.open_connection`)
  - Plain text formatter (Signal has no rich formatting support)
  - File-path based media with UUID-prefixed path traversal protection (`os.path.basename` + `uuid4().hex` prefix)
  - `/start`, `/link`, `/unlink`, `/status` commands (case-insensitive text prefix)
  - Group mention detection — checks bot UUID and phone number in `mentions` array
  - Disappearing messages — honors `expiresInSeconds` TTL, sets `metadata.disappearing` + `metadata.expires_in_seconds`
  - Read receipts sent via `sendReceipt` RPC when bot processes a message
  - Future-based response routing dispatcher — prevents StreamReader race between receive loop and outbound RPC calls
  - Exponential backoff reconnection (`min(2^attempt, 30)` seconds)
  - `SignalSettings` with phone validation + gateway wiring in `_init_channels()`

- **Settings** — `SlackSettings` (dual mode validation: socket requires app_token, events requires signing_secret) and `SignalSettings` (phone_number required) added to config with `Settings.slack` and `Settings.signal` fields
- **Gateway wiring** — both adapters initialized in `_init_channels()` with graceful failure handling (adapter start failure doesn't block other adapters)

### Security Fixes
- Slack: 5-minute timestamp staleness check prevents replay attacks on Events API webhook
- Signal: UUID-prefixed filenames prevent attachment filename collisions; `os.path.basename` prevents path traversal in media handler
- Signal: `asyncio.wait_for` timeout on RPC reads prevents deadlock under unresponsive daemon

### Tests
- 142 Slack tests + 72 Signal tests + 4 settings validation = 218 new tests
- Total project: 1,633 tests (1,360 backend + 273 Flutter)

---

## [0.5.2] — 2026-03-29 — Phase 5B.2: Universal Skills Marketplace

### Added
- **MarketplaceRegistry** — tiered publishing pipeline (community auto-approve after security scan, verified badge via manual admin review), SemVer versioning with update checks, star ratings (upsert + running average), unpublish support
- **SkillPackager** — dual package format: `.nobla` zip archive (nobla-skill.json manifest + skill.py + optional deps) + manifest-pointer for external skills (MCP, OpenClaw, Claude, LangChain), SHA-256 integrity hashing, archive size enforcement
- **SkillDiscovery** — keyword search (case-insensitive on name/description/tags), category/tags/trust_tier/source_format filters, pagination, sort by install_count/avg_rating/created_at, pattern-based recommendations (via Phase 5B.1 PatternDetector), similar-to-installed recommendations (same-category matching)
- **UsageTracker** — event-driven stats tracking: install_count and active_users via `skill.installed`/`skill.uninstalled` events, success_rate via `tool.executed`/`tool.failed` events correlated by `skill_id` payload
- **MarketplaceService** orchestrator — start/stop lifecycle with event subscriptions stored as `(event_type, handler)` tuples, install/uninstall delegation to SkillRuntime, delegates to registry/discovery/stats for all other operations
- **MarketplaceSettings** — `enabled`, `max_skills_per_author` (50), `max_archive_size_mb` (10), `storage_dir`
- **15 REST API routes** under `/api/marketplace/` — search, skill detail, versions, ratings, publish, publish version, rate, install, uninstall, updates, recommendations, categories, unpublish, request verification, admin review
- **Gateway wiring** — MarketplaceService initialized in lifespan after LearningService, kill switch integration, cleanup on shutdown
- **ToolExecutor enhancement** — `skill_id` field added to `tool.executed`/`tool.failed` event payloads for SkillToolBridge tools
- **Flutter MarketplaceScreen** — search bar with submit, category FilterChip row (9 categories), recommendation horizontal ScrollViews ("Based on your patterns", "Similar to installed"), GridView of SkillCards with responsive layout
- **Flutter SkillDetailScreen** — header with display name/author/trust badge, Install button, description + tag Chips, 4-stat row (installs/active/rating/success), VersionListWidget (expandable with changelog), RatingWidget + reviews list
- **Flutter widgets** — SkillCard (name, author, stars, install count, trust badge, Install/Installed button), RatingWidget (5 tappable stars), VersionListWidget (ExpansionTile with scan badge)
- **Flutter models** — MarketplaceSkill, SkillVersion, SkillRating, UpdateNotification, SearchResults with fromJson/toJson, enums (PackageType, TrustTier, VerificationStatus)
- **Riverpod providers** — marketplaceSearchProvider (state-driven), skillDetailProvider, skillRatingsProvider, updateListProvider, recommendationsProvider, categoryListProvider
- **Router wiring** — `/home/tools/marketplace` and `/home/tools/marketplace/:id` routes under ShellRoute

### Tests
- 97 backend tests + 32 Flutter tests = 129 new tests
- Total project: 1,321 tests (1,048 backend + 273 Flutter)

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
