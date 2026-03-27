# Phase 5 Redesign: Shared Foundation, Channels, Scheduler, Self-Improving Agent & Universal Marketplace

**Date:** 2026-03-26
**Author:** [NABILNET.AI](https://nabilnet.ai)
**Status:** Approved — review pass complete (pending implementation plan)
**Phases Covered:** 5-Foundation, 5A, 5B
**Prerequisite:** Phase 4 (all sub-phases including 4E) complete

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Hard Rules](#2-hard-rules)
3. [Phase Structure](#3-phase-structure)
4. [Phase 5-Foundation: Shared Foundation](#4-phase-5-foundation)
   - 4.1 Event Bus
   - 4.2 Channel Abstraction Layer
   - 4.3 Skill Runtime & Universal Adapter
5. [Phase 5A: Ship Fast](#5-phase-5a-ship-fast)
   - 5.1 Telegram Bot
   - 5.2 Discord Bot
   - 5.3 NL Scheduled Tasks
6. [Phase 5B: Intelligence Layer](#6-phase-5b-intelligence-layer)
   - 6.1 Self-Improving Agent
   - 6.2 Universal Skills Marketplace
7. [Restructured Phase Roadmap](#7-restructured-phase-roadmap)
8. [Configuration Reference](#8-configuration-reference)
9. [File Structure Reference](#9-file-structure-reference)
10. [Integration Points](#10-integration-points)
11. [JSON-RPC Error Codes](#11-json-rpc-error-codes)
12. [Security Invariants](#12-security-invariants)
13. [Competitive Context](#13-competitive-context)

---

## 1. Executive Summary

This spec restructures Phases 5-7 of the Nobla Agent roadmap based on competitive analysis of MiniMax MaxClaw and strategic prioritization. The core insight: MaxClaw ships channel integrations, scheduled tasks, and a skills marketplace today while Nobla has superior security, privacy, and computer control but no user-facing distribution channels.

The redesign merges the most competitive features from Phases 5 and 6 into a focused three-stage delivery:

- **5-Foundation** — Shared event bus, channel abstraction, skill runtime with universal adapter (1 week)
- **5A** — Telegram bot, Discord bot, NL scheduled tasks (2-3 weeks)
- **5B** — Self-improving agent with transparent audit trail, universal skills marketplace with hosted + self-hosted registry (3-4 weeks)

Architecture approach: **Shared Foundation** — build the event bus, channel abstraction, and skill runtime first, then every feature plugs into the same infrastructure. One week of clean architecture beats four weeks of refactoring.

Key differentiators from MaxClaw:
- Every skill runs in Docker/gVisor sandbox, no exceptions
- Self-improving agent logs every change with one-click rollback
- Weekly Improvement Digest sent to user's channel
- Universal skill adapter imports from MCP, OpenClaw/MaxClaw, Claude Code, and LangChain
- Self-hosted marketplace registry as a first-class deployment option
- Privacy-first: all data stays local unless user explicitly connects external services

---

## 2. Hard Rules

These are non-negotiable constraints that apply across all sub-phases:

### 2.1 Foundation Sequencing
**Phase 5-Foundation must be 100% complete and tested before a single line of 5A or 5B code is written.** No parallel development on the foundation. The event bus, channel abstraction, and skill runtime are the substrate everything else builds on — a flaw here propagates everywhere.

### 2.2 Security Defaults
- All channel bots require linked Nobla accounts. Unlinked users receive a pairing prompt and nothing else. No open bots.
- All skills (bundled, marketplace, manually imported) default to `enabled: false`. Nothing executes without explicit user activation.
- All external skills run inside Docker/gVisor sandbox. No exceptions, even for "verified" skills.
- Install dry-run has a 10-second hard timeout. Skill doesn't complete test execution in 10 seconds → install rejected.

### 2.3 Transparency
- Every self-improvement action is logged with reason, evidence, and one-click rollback.
- Auto-rollback triggers send immediate notification to user's active channel — never silent.
- Scheduled task creation always requires explicit user confirmation before activation.
- Draft skill notifications are capped at 1 per day, batched if multiple.

### 2.4 Correlation Tracing
`correlation_id` propagates end-to-end from `channel.message.in` through every event, audit entry, and log line to `channel.message.out`. Any full conversation flow is traceable in the audit trail.

### 2.5 File Size
750-line hard limit per file. No exceptions. Split into well-named modules if approaching limit.

---

## 3. Phase Structure

| Phase | Name | Scope | Dependency |
|-------|------|-------|------------|
| 5-Foundation | Shared Foundation | Event bus, channel abstraction, skill runtime + universal adapter | Phase 4 complete |
| 5A | Ship Fast | Telegram bot, Discord bot, NL scheduled tasks | 5-Foundation 100% complete + tested |
| 5B | Intelligence Layer | Self-improving agent, universal marketplace MVP | 5A complete |

---

## 4. Phase 5-Foundation: Shared Foundation

### 4.1 Event Bus

The backbone all components communicate through. Async pub/sub with typed events and wildcard subscriptions.

#### Data Models

```python
# backend/nobla/events/models.py

@dataclass
class NoblaEvent:
    event_type: str           # e.g. "channel.message.in"
    source: str               # e.g. "telegram", "scheduler", "tool.code.run"
    user_id: str | None
    conversation_id: str | None
    timestamp: datetime
    payload: dict[str, Any]
    correlation_id: str       # UUID — propagates end-to-end for full trace
```

#### Event Bus Interface

```python
# backend/nobla/events/bus.py

class NoblaEventBus:
    subscribe(event_type: str, handler: Callable)  # Supports wildcards: "tool.*"
    unsubscribe(event_type: str, handler: Callable)
    async emit(event: NoblaEvent)  # Dispatches to all matching handlers
```

#### Error Handling & Backpressure

- **Handler isolation:** If a handler raises an exception, the exception is logged with `correlation_id` context but does **not** block dispatch to remaining handlers. Each handler runs in its own `try/except`.
- **Priority levels:** Events carry an optional `priority: int` field (default `0`). Higher priority events are dispatched first. `self.improvement.rollback` uses `priority: 10` (urgent).
- **Queue depth:** Maximum 10,000 pending events. If exceeded, oldest non-urgent events (priority < 5) are dropped and a `bus.overflow` warning is logged. Urgent events are never dropped.
- **Ordering:** Within the same priority level, events are dispatched in FIFO order. No cross-handler ordering guarantees — handlers are concurrent.

#### Core Event Types

| Event | Emitted By | Consumed By |
|-------|-----------|-------------|
| `channel.message.in` | Channel adapters | Gateway (routes to LLM) |
| `channel.message.out` | Gateway | Channel adapters (deliver response) |
| `channel.auth.required` | Channel adapters | Linking service (send pairing prompt) |
| `tool.executed` | Tool executor | Self-improver, audit |
| `tool.failed` | Tool executor | Self-improver, audit |
| `tool.approval.requested` | Approval manager | Channel adapters (inline buttons) |
| `tool.approval.resolved` | Channel adapters / Flutter | Approval manager |
| `schedule.fired` | Scheduler | Gateway (execute task) |
| `schedule.result` | Gateway | Scheduler (store + notify via channel) |
| `skill.installed` | Skill runtime | Registry, notification |
| `skill.executed` | Skill runtime | Self-improver |
| `self.improvement` | Self-improver | Audit, notification |
| `self.improvement.rollback` | Self-improver | Channel adapter (immediate notification, priority: urgent) |
| `memory.consolidated` | Memory orchestrator | Self-improver |

#### Integration
Initialized during `app.py` lifespan before all services. Passed to each service that needs it. Existing components (tool executor, memory, etc.) emit events at their natural boundaries without changing core logic.

#### Files
```
backend/nobla/events/
├── __init__.py
├── bus.py              # NoblaEventBus
└── models.py           # NoblaEvent
```

---

### 4.2 Channel Abstraction Layer

Generic adapter interface. Adding any new channel = implementing one class.

#### Unified Message Format

```python
# backend/nobla/channels/base.py

class ChannelMessage:
    channel: str              # "telegram", "discord", "flutter"
    channel_user_id: str      # Platform-specific user ID
    nobla_user_id: str | None # Mapped Nobla user (after auth)
    conversation_id: str | None
    content: str
    attachments: list[Attachment]
    reply_to: str | None
    metadata: dict             # Channel-specific extras

class Attachment:
    type: AttachmentType       # IMAGE, AUDIO, VIDEO, DOCUMENT
    url: str | None
    data: bytes | None
    filename: str
    mime_type: str
    size_bytes: int

class ChannelResponse:
    content: str
    attachments: list[Attachment]
    actions: list[InlineAction] | None

class InlineAction:
    action_id: str             # "approval:{request_id}:approve"
    label: str                 # "Approve ✅"
    style: str                 # "primary", "danger"
```

#### Adapter Interface

```python
class BaseChannelAdapter(ABC):
    name: str                  # "telegram"

    async def start() -> None
    async def stop() -> None
    async def send(channel_user_id: str, response: ChannelResponse) -> None
    async def send_notification(channel_user_id: str, text: str) -> None
    def parse_callback(raw_callback) -> tuple[str, dict]
    async def health_check() -> bool
```

#### Channel Manager

```python
# backend/nobla/channels/manager.py

class ChannelManager:
    register(adapter: BaseChannelAdapter) -> None
    unregister(channel: str) -> None
    get(channel: str) -> BaseChannelAdapter | None
    list_active() -> list[str]
    async start_all() -> None
    async stop_all() -> None
    async deliver(user_id: str, response: ChannelResponse) -> None
```

#### User Linking

```python
# backend/nobla/channels/linking.py

class LinkedUser:
    nobla_user_id: str
    tier: Tier                 # User's permission tier (SAFE/STANDARD/ELEVATED/ADMIN)
    preferred_channel: str     # Most recently active channel

class UserLinkingService:
    async def link(channel: str, channel_user_id: str, nobla_user_id: str) -> None
    async def unlink(channel: str, channel_user_id: str) -> None
    async def resolve(channel: str, channel_user_id: str) -> LinkedUser | None
    async def get_channels(nobla_user_id: str) -> list[LinkedChannel]
```

**Auth flow:** Unlinked user sends message → adapter cannot resolve → emits `channel.auth.required` → adapter sends one-time pairing code → user enters it in Flutter or via `/link` command → accounts linked. All subsequent messages auto-resolve. **Unlinked users get a pairing prompt and nothing else — no open access.**

#### Channel-to-Executor Bridge (ConnectionState)

The existing executor pipeline requires `ConnectionState` (a WebSocket-specific dataclass with `connection_id`, `user_id`, `tier`, `passphrase_hash`). Channel adapters construct a synthetic `ChannelConnectionState` from the `LinkedUser` returned by `UserLinkingService.resolve()`:

```python
# backend/nobla/channels/bridge.py

class ChannelConnectionState:
    """Synthetic ConnectionState for channel-originated requests."""
    connection_id: str         # "{channel}:{channel_user_id}" (e.g. "telegram:123456")
    user_id: str               # From LinkedUser.nobla_user_id
    tier: Tier                 # From LinkedUser.tier
    passphrase_hash: str       # Retrieved from user's auth record
    source_channel: str        # "telegram", "discord"
```

This is constructed by each adapter's message handler before routing to the gateway. The executor pipeline sees a valid `ConnectionState` and requires no changes.

#### Multi-Channel Delivery

When `ChannelManager.deliver()` is called, it sends to the user's **most recently active channel** (tracked via `LinkedUser.preferred_channel`). Users can override this with a `/notify` command to set their preferred notification channel explicitly. Broadcast to all channels is never done by default — it only happens for `priority: urgent` events (kill switch, auto-rollback).

#### Design Decision
The existing Flutter WebSocket handler does NOT become a channel adapter. It remains the primary interface with richer capabilities (streaming, activity feed, security dashboard). Channels are a secondary interface routing through the same brain/memory/tools with a simpler interaction model.

#### Files
```
backend/nobla/channels/
├── __init__.py
├── base.py          # BaseChannelAdapter, ChannelMessage, ChannelResponse, InlineAction, Attachment
├── manager.py       # ChannelManager
├── linking.py       # UserLinkingService
├── telegram.py      # TelegramAdapter (Phase 5A)
└── discord.py       # DiscordAdapter (Phase 5A)
```

---

### 4.3 Skill Runtime & Universal Adapter

Loads, validates, sandboxes, and executes skills from any source.

#### Normalized Skill Model

```python
# backend/nobla/skills/models.py

class SkillSource(str, Enum):
    NOBLA = "nobla"
    MCP = "mcp"
    OPENCLAW = "openclaw"
    CLAUDE = "claude"
    LANGCHAIN = "langchain"

class SkillCategory(str, Enum):
    """Extends ToolCategory for marketplace skills. Existing ToolCategory values
    (VISION, INPUT, FILE_SYSTEM, etc.) map 1:1. New categories are marketplace-only."""
    # Existing ToolCategory mappings (same values)
    VISION = "vision"
    INPUT = "input"
    FILE_SYSTEM = "file_system"
    APP_CONTROL = "app_control"
    CODE = "code"
    GIT = "git"
    SSH = "ssh"
    CLIPBOARD = "clipboard"
    SEARCH = "search"
    # New marketplace categories
    PRODUCTIVITY = "productivity"
    MEDIA = "media"
    FINANCE = "finance"
    AUTOMATION = "automation"
    COMMUNICATION = "communication"
    RESEARCH = "research"
    UTILITIES = "utilities"

class SkillManifest:
    id: str                    # "nobla://image-gen" or "mcp://github"
    name: str
    description: str
    version: str
    source: SkillSource
    author: str
    category: SkillCategory
    tier: Tier                 # Permission tier required
    requires_approval: bool
    enabled: bool = False      # ALWAYS false by default — no exceptions
    capabilities: list[str]
    dependencies: list[str]
    config_schema: dict | None
    original_format: dict      # Raw source manifest preserved

class NoblaSkill:
    """Mirrors BaseTool interface — registers into existing ToolRegistry."""
    manifest: SkillManifest

    async def execute(params: ToolParams) -> ToolResult
    async def validate(params: ToolParams) -> None
    def describe_action(params: ToolParams) -> str
    def get_params_summary(params: ToolParams) -> dict
```

#### BaseTool Bridge

Skills are external — they don't subclass `BaseTool` directly. `SkillToolBridge` wraps any `NoblaSkill` into a proper `BaseTool` subclass so it can register into the existing `ToolRegistry` and flow through the standard executor pipeline (permissions, approval, sandbox, audit).

```python
# backend/nobla/skills/bridge.py

class SkillToolBridge(BaseTool):
    """Wraps a NoblaSkill as a BaseTool for ToolRegistry integration."""

    def __init__(self, skill: NoblaSkill):
        self._skill = skill
        m = skill.manifest
        # Map manifest fields → BaseTool required class attributes
        self.name = m.name
        self.description = m.description
        self.category = m.category.to_tool_category()  # SkillCategory → ToolCategory
        self.tier = m.tier
        self.requires_approval = m.requires_approval

    async def execute(self, params: ToolParams) -> ToolResult:
        return await self._skill.execute(params)

    async def validate(self, params: ToolParams) -> None:
        return await self._skill.validate(params)

    def describe_action(self, params: ToolParams) -> str:
        return self._skill.describe_action(params)

    def get_params_summary(self, params: ToolParams) -> dict:
        return self._skill.get_params_summary(params)
```

`SkillRuntime.install()` calls `ToolRegistry.register(bridge_instance)` — this requires adding a non-decorator `register()` method to `ToolRegistry` that accepts a pre-built `BaseTool` instance (in addition to the existing `@register_tool` decorator).

For `SkillCategory` values that don't exist in `ToolCategory` (e.g., PRODUCTIVITY, FINANCE), `to_tool_category()` returns a new `ToolCategory.SKILL` catch-all value. The executor pipeline does not filter by category — it only checks `tier` — so this is safe.

#### Universal Adapter

```python
# backend/nobla/skills/adapter.py

class UniversalSkillAdapter:
    def __init__(self, adapters: dict[SkillSource, FormatAdapter])
    async def import_skill(source: str | dict | Path) -> NoblaSkill
    def detect_format(source) -> SkillSource
```

#### Format Adapters (priority order)

| # | Adapter | Detection Heuristic | Execution Strategy |
|---|---------|--------------------|--------------------|
| 1 | `MCPAdapter` | URL with `/mcp`, `stdio://`, or MCP manifest JSON | Spawns MCP client, proxies tool calls through sandbox. **Per-call timeout: 30s default (configurable per skill). Retries: 0 (idempotency safety). Unreachable → `tool.failed` with `error_type: "mcp_unreachable"`.** |
| 2 | `OpenClawAdapter` | `skill.json` with `openclaw_version` or `claw_` prefixed keys | Translates schema → NoblaSkill, runs in sandbox |
| 3 | `ClaudeAdapter` | `.md` with YAML frontmatter containing `name:` + `description:` | Frontmatter as manifest, body as system prompt for LLM execution |
| 4 | `LangChainAdapter` | Python module with `Tool` or `BaseTool` subclass | Wraps `_run()` in sandbox subprocess |
| 5 | `NoblaAdapter` | `skill.json` with `nobla_version` field | Native — loads directly |

#### Skill Runtime

```python
# backend/nobla/skills/runtime.py

class SkillRuntime:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox_manager: SandboxManager,
        permission_checker: PermissionChecker,
        event_bus: NoblaEventBus,
        adapter: UniversalSkillAdapter,
    )

    async def install(source: str | dict | Path) -> SkillManifest:
        # Transactional install — all-or-nothing:
        # 1. Adapter detects format, parses manifest
        # 2. Security scan (SkillSecurityScanner)
        # 3. Sandbox dry-run with 10-SECOND HARD TIMEOUT (20s for MCP) — reject if exceeded
        # 4. Persist to installed_skills table (DB first — source of truth)
        # 5. Wrap in SkillToolBridge, register via ToolRegistry.register()
        #    - If registration fails → delete DB row → raise
        # 6. Emit skill.installed event
        # 7. Skill defaults to enabled: false
        #
        # On any failure after step 4: rollback DB row.
        # On restart: skills loaded from DB, re-registered in ToolRegistry.

    async def uninstall(skill_id: str) -> None
    async def enable(skill_id: str) -> None
    async def disable(skill_id: str) -> None
    async def list_installed() -> list[SkillManifest]
    async def upgrade(skill_id: str) -> SkillManifest
```

Every skill execution goes through the existing pipeline:
1. `PermissionChecker.check()` — 4-tier model
2. `ApprovalManager` — if `requires_approval`
3. `SandboxManager.execute()` — Docker/gVisor, always
4. `AuditEntry` logged
5. `tool.executed` or `tool.failed` event emitted
6. Cost tracked if skill consumes LLM tokens

#### Security Scanner

```python
# backend/nobla/skills/security.py

class SkillSecurityScanner:
    async def scan(manifest: SkillManifest, source_code: str | None) -> ScanResult:
        # 1. Pattern matching: network calls, file system access, env var reads
        # 2. Dependency check: known malicious packages
        # 3. Permission escalation: does it claim higher tier than justified?
        # 4. Sandbox dry-run: execute with mock data, 10-second hard timeout
```

#### Files
```
backend/nobla/skills/
├── __init__.py
├── models.py              # SkillManifest, NoblaSkill, SkillSource, SkillCategory
├── adapter.py             # UniversalSkillAdapter
├── runtime.py             # SkillRuntime
├── security.py            # SkillSecurityScanner
├── adapters/
│   ├── __init__.py
│   ├── nobla.py           # Native format
│   ├── mcp.py             # MCP server client (priority #1)
│   ├── openclaw.py        # OpenClaw/MaxClaw format
│   ├── claude.py          # Claude Code skill format
│   └── langchain.py       # LangChain tool wrapper
└── store/
    ├── __init__.py
    ├── registry.py         # Installed skills DB (PostgreSQL)
    ├── marketplace.py      # Marketplace API client
    └── packages.py         # .nsk package download, verify, extract
```

---

## 5. Phase 5A: Ship Fast

**Prerequisite:** Phase 5-Foundation 100% complete and tested.

### 5.1 Telegram Bot

Implementation of `BaseChannelAdapter` using `python-telegram-bot`.

**Capabilities (MVP):**
- Text chat routed through LLM router
- File sharing: send/receive images, documents, audio
- Inline tool approval: message with action description + Approve/Deny buttons
- Schedule confirmation: parsed schedule details + Approve/Cancel buttons
- Schedule result notifications: formatted results with Pause/Edit/Delete buttons
- Pairing flow: `/start` → pairing code → link to Nobla account

**Interaction model:**
```
User sends message
  → TelegramAdapter.parse() → ChannelMessage
  → Emit channel.message.in (with correlation_id)
  → Gateway processes (LLM router, memory, tools)
  → Emit channel.message.out (same correlation_id)
  → TelegramAdapter.send() → formatted Telegram message
```

**Tool approval format:**
```
🔧 Tool: code.run
📋 Run Python script: data_analysis.py

[Approve ✅]  [Deny ❌]
```

**Settings:**
```python
class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    webhook_url: str | None = None   # None = long polling mode
    # No allowed_user_ids — auth is handled by UserLinkingService
    # Unlinked users get pairing prompt only
```

### 5.2 Discord Bot

Implementation of `BaseChannelAdapter` using `discord.py`.

**Capabilities (MVP):**
- Text chat in DMs and designated guild channels
- File sharing: send/receive attachments
- Inline tool approval via Discord buttons (discord.ui.View)
- Schedule confirmation and notification via embeds
- Pairing flow: `/link` slash command → pairing code

**Settings:**
```python
class DiscordSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    command_prefix: str = "!"
    allowed_guild_ids: list[str] = []  # Empty = DM only
    # Auth handled by UserLinkingService — linked users only
```

### 5.3 NL Scheduled Tasks

Hybrid scheduler: dedicated NLP time parser for reliability, LLM for task understanding, APScheduler for execution.

#### Schedule Parser (Two-Stage)

```python
# backend/nobla/scheduler/parser.py

class ParsedSchedule:
    trigger_type: TriggerType          # CRON, DATE, INTERVAL
    cron_expression: str | None        # "0 10 * * 0" (Sunday 10am)
    run_at: datetime | None            # One-shot
    interval_seconds: int | None
    timezone: str
    task_description: str              # "check my emails"
    task_prompt: str                   # Full prompt for LLM when firing
    human_readable: str                # "Every Sunday at 10:00 AM"
    confidence: float                  # 0.0-1.0

class ScheduleParser:
    def __init__(self, router: LLMRouter, confidence_threshold: float = 0.8)

    async def parse(user_input: str, user_tz: str) -> ParsedSchedule:
        # Stage 1: NLP Time Extraction
        #   - dateparser for absolute dates ("March 30th at 3pm")
        #   - recurrent for recurring patterns ("every other Tuesday")
        #   - regex fallback for explicit cron expressions
        #   - Reject if confidence < threshold → AmbiguousTimeError
        #
        # Stage 2: LLM Task Extraction
        #   - LLM extracts task description from user input
        #   - Builds execution prompt for when task fires

    async def validate(schedule: ParsedSchedule) -> list[str]:
        # No interval < 1 minute
        # No schedule > 1 year out
        # Warn if > 10 active schedules per user
        # Warn if task_description is vague
```

**Why two libraries:** `dateparser` excels at absolute dates in 200+ languages. `recurrent` excels at recurring patterns ("every other Tuesday", "last Friday of each month"). Together they cover the full spectrum. The LLM never touches time parsing.

#### Schedule Manager

```python
# backend/nobla/scheduler/manager.py

class ScheduledTask(BaseModel):
    id: str
    user_id: str
    name: str
    schedule: ParsedSchedule
    status: ScheduleStatus            # ACTIVE, PAUSED, COMPLETED, FAILED
    created_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_count: int = 0
    last_result: str | None
    max_consecutive_failures: int = 3

class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"                 # Auto-paused after max failures

class ScheduleManager:
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        parser: ScheduleParser,
        event_bus: NoblaEventBus,
        router: LLMRouter,
        memory: MemoryOrchestrator,
        tool_executor: ToolExecutor,
    )

    async def create(user_input: str, user_id: str, user_tz: str) -> ScheduledTask:
        # 1. Parse user input (two-stage)
        # 2. Validate
        # 3. Send confirmation to user with parsed details:
        #    "⏰ I understood: Check your emails
        #     📅 Every Sunday at 10:00 AM (Asia/Riyadh)
        #     [Confirm ✅]  [Cancel ❌]"
        # 4. ONLY create after explicit user confirmation
        # 5. Persist to PostgreSQL
        # 6. Register with APScheduler

    async def pause(task_id: str, user_id: str) -> None
    async def resume(task_id: str, user_id: str) -> None
    async def delete(task_id: str, user_id: str) -> None
    async def list_tasks(user_id: str) -> list[ScheduledTask]
    async def get_task(task_id: str, user_id: str) -> ScheduledTask
    async def update(task_id: str, user_input: str, user_id: str) -> ScheduledTask

    async def _execute_task(task: ScheduledTask) -> None:
        # 1. Build conversation context from memory
        # 2. Send task_prompt to LLM router
        # 3. If LLM requests tool use → tool executor
        # 4. Store result
        # 5. Emit schedule.result event → channel adapter notifies user
        # 6. Update run_count, next_run_at
        # 7. If failed: increment failure counter, auto-pause if max reached
```

**Confirmation requirement:** Before creating any scheduled task, always send a confirmation message showing the parsed time, recurrence, and task description with Confirm and Cancel buttons. This catches parser misunderstandings before they become silent failures two weeks later.

**Offline result handling:** When a scheduled task fires and the user has no active channel session:
1. Result is always persisted in `ScheduledTask.last_result` (already in the model).
2. A `pending_notifications` table stores undelivered results with `created_at` and `delivered_at`.
3. When the user next connects to any channel or Flutter, all pending notifications are delivered in chronological order.
4. The `schedule.results` RPC method lets the user pull missed results on demand.
5. Pending notifications are retained for **30 days**, then pruned.

**Implicit scheduling via chat:** User says "remind me every Sunday at 10am to check my emails" in normal chat → LLM detects scheduling intent → calls `schedule.create` tool → parser extracts time + task → confirmation sent → user approves → task active.

**Notification format when task fires:**
```
⏰ Scheduled Task: Check emails
✅ You have 3 unread emails:
  - From: boss@company.com — Q1 Review
  - From: github.com — PR #142 merged
  - From: mom — Dinner Sunday?

Next run: Sunday, April 5 at 10:00 AM

[Pause ⏸️]  [Edit ✏️]  [Delete 🗑️]
```

#### Gateway RPC Handlers
```python
@rpc_method("schedule.create")    # {input: "every Sunday at 10am check emails"}
@rpc_method("schedule.list")      # {} → user's scheduled tasks
@rpc_method("schedule.get")       # {task_id}
@rpc_method("schedule.pause")     # {task_id}
@rpc_method("schedule.resume")    # {task_id}
@rpc_method("schedule.delete")    # {task_id}
@rpc_method("schedule.update")    # {task_id, input: "change to every Monday"}
```

#### Files
```
backend/nobla/scheduler/
├── __init__.py
├── parser.py              # ScheduleParser (NLP time + LLM task)
├── manager.py             # ScheduleManager (APScheduler wrapper)
├── models.py              # ScheduledTask, ParsedSchedule, ScheduleStatus
├── persistence.py         # PostgreSQL CRUD
└── tool.py                # schedule.create BaseTool subclass for LLM function-calling
```

---

## 6. Phase 5B: Intelligence Layer

**Prerequisite:** Phase 5A complete.

### 6.1 Self-Improving Agent

Active self-tuning with full audit trail and one-click rollback. Every modification logged, explained, and reversible.

#### Observation Layer

```python
# backend/nobla/improver/observer.py

class ObservationRecord:
    id: str
    timestamp: datetime
    event_type: str
    user_id: str
    correlation_id: str
    category: str              # "llm_routing", "tool_execution", "scheduling"
    outcome: Outcome           # SUCCESS, FAILURE, TIMEOUT, USER_CORRECTION
    details: dict

class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    USER_CORRECTION = "user_correction"

class Observer:
    def __init__(self, event_bus: NoblaEventBus, store: ObservationStore)

    async def start() -> None:
        # Subscribe to: tool.*, schedule.*, channel.message.in, skill.*
        # Detect user corrections ("no, I meant...", "that's wrong")

    async def record_user_feedback(user_id: str, rating: int, context: str) -> None
```

#### Three Analyzers (one file each to stay under 750 lines)

```python
# backend/nobla/improver/failure_detector.py, routing_analyzer.py, workflow_recognizer.py

class FailureDetector:
    """Same tool failing 3+ times, timeout patterns, cascading failures."""
    async def analyze(observations: list[ObservationRecord]) -> list[FailurePattern]

class RoutingAnalyzer:
    """Provider X fails on task type Y but Z succeeds. Cost outliers."""
    async def analyze(observations: list[ObservationRecord]) -> list[RoutingSuggestion]

class WorkflowRecognizer:
    """User performs A → B → C three or more times. Candidate for auto-skill."""
    async def analyze(observations: list[ObservationRecord]) -> list[WorkflowCandidate]
```

#### Improvement Actions (all reversible)

```python
# backend/nobla/improver/actions.py

class ImprovementAction(ABC):
    action_type: str
    reason: str                # Human-readable explanation
    evidence: list[str]        # Observation IDs that triggered this

    async def apply() -> None
    async def rollback() -> None
    def describe() -> str

class RoutePreferenceAction(ImprovementAction):
    """Adjusts LLM routing preferences for a task type."""
    action_type = "route_preference"
    task_pattern: str
    old_preference: list[str]
    new_preference: list[str]
    override_source: str = "auto"  # "auto" (self-improver) or "user" (manual)
    # Stored in routing_overrides table, NOT the config file
    # Router checks overrides before default fallback chain
    # Precedence: user-manual overrides ALWAYS win over auto-generated
    # Self-improver skips categories where user has set manual overrides

class ProceduralMemoryAction(ImprovementAction):
    """Saves successful workflow to procedural memory layer."""
    action_type = "procedural_save"
    workflow_steps: list[dict]
    success_context: str

class DraftSkillAction(ImprovementAction):
    """Creates a draft skill from repeated workflow. NEVER auto-enabled."""
    action_type = "draft_skill"
    skill_manifest: SkillManifest  # enabled: false, always
    workflow_definition: dict
    # Writes to skills/drafts/, notifies user to review
    # Draft skill notifications capped at 1/day — batched if multiple
```

#### Improvement Log

```python
# backend/nobla/improver/log.py

class ImprovementLog:
    id: str
    timestamp: datetime
    user_id: str
    action: ImprovementAction
    status: ImprovementStatus  # APPLIED, ROLLED_BACK, PENDING_REVIEW
    applied_at: datetime | None
    rolled_back_at: datetime | None
    rolled_back_by: str | None  # "user" or "auto"

class ImprovementStatus(str, Enum):
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    PENDING_REVIEW = "pending_review"
```

#### Weekly Improvement Digest

```python
# backend/nobla/improver/digest.py

class DigestGenerator:
    async def generate(user_id: str, period_days: int = 7) -> DigestReport

class DigestReport:
    summary: str
    improvements: list[DigestItem]
    stats: DigestStats

class DigestItem:
    action_type: str
    description: str           # "Switched SQL tasks to Claude — 40% fewer errors"
    evidence_summary: str      # "Based on 12 failed SQL generations with Groq"
    rollback_available: bool

class DigestStats:
    tasks_observed: int
    success_rate: float        # This week vs last week
    improvements_applied: int
    improvements_rolled_back: int
    draft_skills_created: int
    estimated_time_saved: str
```

**Digest format (delivered to Telegram/Discord):**
```
📊 Nobla Weekly Improvement Digest
📅 March 19 – March 26, 2026

This week I observed 142 tasks (89% success rate, up from 82%).

🔧 Improvements Made:
1. Routing: Switched SQL tasks to Claude — error rate 35% → 8%
   [Rollback ↩️]

2. Memory: Saved your "morning standup prep" workflow
   [Rollback ↩️]

3. Draft Skills (1 new):
   - "csv-to-json" — detected 4 repetitions this week
   [Review & Enable 👀]  [Dismiss 🗑️]

⏱️ Estimated time saved: ~15 minutes

📈 Trends:
• Code tasks: ████████░░ 82% success
• Search tasks: █████████░ 94% success
• Scheduling: ██████████ 100% success
```

#### Self-Improver Orchestrator

```python
# backend/nobla/improver/engine.py

class SelfImprover:
    def __init__(
        self,
        observer: Observer,
        failure_detector: FailureDetector,
        routing_analyzer: RoutingAnalyzer,
        workflow_recognizer: WorkflowRecognizer,
        improvement_log: ImprovementLogStore,
        event_bus: NoblaEventBus,
        digest_generator: DigestGenerator,
    )

    async def start() -> None:
        # 1. Start observer
        # 2. Schedule periodic analysis (every 6 hours)
        # 3. Schedule weekly digest
        # 4. Register threshold triggers (3 failures → immediate analysis)

    async def run_analysis(user_id: str) -> list[ImprovementAction]:
        # Fetch observations → run analyzers → deduplicate → apply → log → emit event

    async def rollback(log_id: str, user_id: str) -> None
    async def get_improvements(user_id: str, limit: int) -> list[ImprovementLog]
```

#### Auto-Rollback Safety Net
If an applied improvement causes success rate for that task category to drop by 15%+ over the next 24 hours, the engine automatically rolls it back and **immediately notifies the user** via their active channel:
```
⚠️ Auto-Rollback Triggered
I rolled back "Switch SQL tasks to Claude" because SQL task
success rate dropped from 85% to 68% in the last 24 hours.
Your system is back to the previous routing behavior.
[View Details 📊]
```

#### Gateway RPC Handlers
```python
@rpc_method("improver.history")     # {limit?}
@rpc_method("improver.rollback")    # {log_id}
@rpc_method("improver.digest")      # {} → on-demand digest
@rpc_method("improver.pause")       # {} → pause self-improvement
@rpc_method("improver.resume")      # {} → resume
```

#### Design Principle
The self-improver is a **consumer** of the event bus, never a **controller**. It observes, analyzes, and makes small targeted adjustments. It never takes over routing logic or tool execution — it nudges preferences via a separate overrides layer that can be wiped clean with zero impact on core functionality.

#### Files
```
backend/nobla/improver/
├── __init__.py
├── observer.py            # Observer
├── analyzers.py           # FailureDetector, RoutingAnalyzer, WorkflowRecognizer
├── actions.py             # ImprovementAction ABC + concrete actions
├── engine.py              # SelfImprover orchestrator
├── log.py                 # ImprovementLog models
├── digest.py              # DigestGenerator + DigestReport
├── persistence.py         # PostgreSQL storage
└── models.py              # ObservationRecord, Outcome, shared types
```

---

### 6.2 Universal Skills Marketplace

App Store for AI skills. Hosted registry with self-hosted option as a first-class feature.

#### Architecture: Two Deployment Modes

The marketplace registry is designed from the ground up to support both hosted and self-hosted deployment equally. This is not a footnote — it's a core architectural requirement driven by Nobla's privacy-first identity and enterprise customer needs.

**Hosted Registry (default):**
- Operated by Nobla team at `marketplace.nobla.dev`
- Central catalog, community ratings, trending, featured skills
- Zero setup for individual users

**Self-Hosted Registry (first-class):**
- Same codebase, same API, same features
- Deployed as a single Docker container with PostgreSQL
- Enterprise customers run their own private registry
- Can sync curated skills from the public registry (opt-in)
- Fully air-gapped mode: no external network access needed
- Configuration: user points `registry_url` to their own instance

```
┌─────────────────────────────────────────┐
│         nobla-registry service           │
│     (identical for hosted & self-hosted) │
│                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │ Catalog   │  │ Publish  │  │ Search ││
│  │ API       │  │ Pipeline │  │ API    ││
│  └──────────┘  └──────────┘  └────────┘│
│                     │                    │
│              PostgreSQL + S3/local       │
│         (metadata + skill packages)      │
└─────────────────────┬────────────────────┘
                      │ HTTPS API (same for both modes)
          ┌───────────┴───────────┐
          ▼                       ▼
   Nobla Agent               Nobla Agent
   (connects to              (connects to
    marketplace.nobla.dev)    registry.corp.internal)
```

**Self-hosted deployment:**
```bash
# One-command deploy for enterprise
docker run -d \
  -p 8080:8080 \
  -v nobla-registry-data:/data \
  -e DATABASE_URL=postgresql://... \
  -e STORAGE_PATH=/data/packages \
  nobla/registry:latest

# Optional: sync from public registry
docker exec nobla-registry sync --source https://marketplace.nobla.dev --categories productivity,dev
```

#### Registry API

```
# Catalog
GET    /api/v1/skills                    # Browse (paginated, filterable)
GET    /api/v1/skills/{id}               # Detail
GET    /api/v1/skills/featured           # Editor's picks
GET    /api/v1/skills/trending           # By installs (7-day window)
GET    /api/v1/categories                # Category list with counts

# Search
GET    /api/v1/search?q=...&source=...&category=...&sort=...

# Publishing
POST   /api/v1/skills                    # Submit (authenticated)
PUT    /api/v1/skills/{id}/versions      # New version
GET    /api/v1/skills/{id}/versions      # Version history

# User actions
POST   /api/v1/skills/{id}/install       # Record install (analytics)
POST   /api/v1/skills/{id}/rate          # 1-5 stars + optional review
GET    /api/v1/skills/{id}/reviews       # Read reviews

# Author
GET    /api/v1/authors/{id}              # Profile + published skills
GET    /api/v1/authors/{id}/stats        # Install counts, ratings

# Sync (self-hosted only)
POST   /api/v1/sync                      # Pull from upstream registry
GET    /api/v1/sync/status               # Sync health
```

#### Skill Package Format (.nsk)

```
my-skill-1.0.0.nsk                  # Nobla Skill Package (zip)
├── skill.json                       # Manifest (NoblaSkill format)
├── SKILL.md                         # System prompt / instructions
├── icon.png                         # 256x256 skill icon
├── README.md                        # Marketplace listing description
├── src/                             # Skill source code
│   └── ...
└── test/                            # Required: at least one test case
    └── test_skill.py
```

#### Publish Pipeline

```python
# nobla-registry/pipeline/

class PublishPipeline:
    async def process(package: SkillPackage, author_id: str) -> PublishResult:
        # 1. Format validation (schema, required files, size limits)
        # 2. Security scan (SkillSecurityScanner)
        # 3. Sandbox test execution (10-second hard timeout)
        # 4. Metadata extraction (categories, tags, search index)
        # 5. Pass → PUBLISHED. Fail → REJECTED with reasons.
```

#### Marketplace Client (inside Nobla agent)

```python
# backend/nobla/skills/store/marketplace.py

class MarketplaceClient:
    def __init__(
        self,
        registry_url: str,          # Hosted or self-hosted — same API
        skill_runtime: SkillRuntime,
    )

    async def browse(category?, source?, sort?, page?, per_page?) -> MarketplacePage
    async def search(query: str, **filters) -> MarketplacePage
    async def get_detail(skill_id: str) -> MarketplaceSkillDetail

    async def install(skill_id: str) -> SkillManifest:
        # 1. Download .nsk from registry
        # 2. Verify package signature
        # 3. SkillRuntime.install() (sandbox validation, 10s timeout)
        # 4. Register as disabled (enabled: false — always)
        # 5. Record install with registry (analytics)
        # 6. Emit skill.installed event

    async def uninstall(skill_id: str) -> None
    async def rate(skill_id: str, stars: int, review: str | None) -> None
    async def check_updates() -> list[SkillUpdate]
    async def upgrade(skill_id: str) -> SkillManifest
```

#### Channel-Based Skill Browsing (Telegram/Discord)

```
User: /skills trending

Nobla: 🏪 Trending Skills This Week:

1. 📧 Email Summarizer ★★★★★ (342 installs)
   Summarizes unread emails into bullet points
   Source: Nobla Native

2. 🐙 GitHub PR Review ★★★★☆ (218 installs)
   Reviews PRs using your project's conventions
   Source: MCP Server

3. 🎨 DALL-E Image Gen ★★★★☆ (195 installs)
   Generate images from text descriptions
   Source: Nobla Native (bundled, disabled)

[Install #1]  [Install #2]  [Install #3]
[Next Page ▶️]  [Search 🔍]
```

#### Image/Video Generation as Bundled Skills

```
skills/
├── bundled/
│   ├── image-gen-dalle/
│   │   ├── skill.json        # enabled: false
│   │   └── SKILL.md
│   ├── image-gen-stable-diffusion/
│   │   ├── skill.json        # enabled: false
│   │   └── SKILL.md
│   ├── video-gen-runway/
│   │   ├── skill.json        # enabled: false
│   │   └── SKILL.md
│   └── ...
└── marketplace/               # User-installed skills
```

Pre-installed, disabled by default. User explicitly enables what they want. Each wraps the relevant API — user provides their own API key via the skill's `config_schema`.

#### Categories (MVP)

| Category | Examples |
|----------|---------|
| Productivity | Email summarizer, meeting notes, calendar assistant |
| Development | Code reviewer, git helper, API tester |
| Media | DALL-E, Stable Diffusion, video gen, audio transcription |
| Finance | Stock tracker, expense parser, crypto alerts |
| Automation | Web scraper, form filler, data pipeline |
| Communication | Email drafter, social media poster |
| Research | Deep research, fact checker, academic search |
| Utilities | CSV converter, JSON formatter, file organizer |

#### Gateway RPC Handlers
```python
@rpc_method("marketplace.browse")       # {category?, source?, sort?, page?}
@rpc_method("marketplace.search")       # {query, filters?}
@rpc_method("marketplace.detail")       # {skill_id}
@rpc_method("marketplace.install")      # {skill_id}
@rpc_method("marketplace.uninstall")    # {skill_id}
@rpc_method("marketplace.enable")       # {skill_id}
@rpc_method("marketplace.disable")      # {skill_id}
@rpc_method("marketplace.rate")         # {skill_id, stars, review?}
@rpc_method("marketplace.updates")      # {} → available updates
@rpc_method("marketplace.upgrade")      # {skill_id}
@rpc_method("marketplace.installed")    # {} → installed skills list
```

#### Files (Agent-Side)
```
backend/nobla/skills/store/
├── __init__.py
├── marketplace.py      # MarketplaceClient
├── registry.py         # Local installed skills DB
└── packages.py         # .nsk download, verify, extract
```

#### Files (Registry Service — Separate Repo)
```
nobla-registry/
├── api/
│   ├── catalog.py      # Browse, featured, trending
│   ├── search.py       # Full-text search with filters
│   ├── publish.py      # Submit, version
│   ├── reviews.py      # Rate, review
│   ├── authors.py      # Author profiles
│   └── sync.py         # Self-hosted sync from upstream
├── pipeline/
│   ├── validator.py    # Format + schema validation
│   ├── scanner.py      # Security scan
│   └── tester.py       # Sandbox test execution
├── models/
│   ├── skill.py
│   ├── author.py
│   └── review.py
├── config.py
├── Dockerfile          # Single-container deployment
└── docker-compose.yml  # With PostgreSQL for self-hosted
```

---

## 7. Restructured Phase Roadmap

| Phase | Name | Scope | Status |
|-------|------|-------|--------|
| 1 | Secure Foundation | Gateway, Auth, Sandbox, Kill Switch, Flutter basic chat | Complete |
| 2 | Intelligence Core | LLM router, memory system, search | Complete |
| 3 | Voice & Persona | STT/TTS, PersonaPlex, avatar | Complete |
| 4 | Computer Control | Vision, mouse/keyboard, code, remote, Flutter UI | Complete |
| **5-Foundation** | **Shared Foundation** | **Event bus, channel abstraction, skill runtime + universal adapter** | **Planned** |
| **5A** | **Ship Fast** | **Telegram bot, Discord bot, NL scheduled tasks** | **Planned** |
| **5B** | **Intelligence Layer** | **Self-improving agent, universal marketplace MVP** | **Planned** |
| 6 | Remaining Channels & Automation | WhatsApp, Slack, Signal, 14 more channels, productivity integrations, workflow builder, multi-agent orchestrator, MCP server mode | Planned |
| 7 | Full Feature Set | Finance, health, social, smart home, education, travel, sysadmin. Media/creative are marketplace skills, not core. | Planned |

**Key changes from original plan:**
1. Phase 5 split into Foundation + 5A + 5B
2. Telegram/Discord pulled from original Phase 5 into 5A (priority)
3. Scheduled tasks pulled from original Phase 6 into 5A (priority)
4. Self-improving agent (was vaguely described in "Self-Improvement System") now has full spec in 5B
5. Skills marketplace pulled from Phase 6 into 5B with universal adapter (import from any platform)
6. Image/video/music generation removed from Phase 7 core → bundled marketplace skills
7. MCP integration split: client-side adapter in 5-Foundation, server mode deferred to Phase 6
8. Remaining 15 channels + productivity integrations deferred to Phase 6
9. Multi-agent orchestrator deferred to Phase 6

---

## 8. Configuration Reference

All new settings added to `backend/nobla/config/settings.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    channels: ChannelSettings = ChannelSettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    improver: ImproverSettings = ImproverSettings()
    marketplace: MarketplaceSettings = MarketplaceSettings()

class ChannelSettings(BaseModel):
    telegram: TelegramSettings | None = None
    discord: DiscordSettings | None = None

class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    webhook_url: str | None = None

class DiscordSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    command_prefix: str = "!"
    allowed_guild_ids: list[str] = []

class SchedulerSettings(BaseModel):
    enabled: bool = True
    max_tasks_per_user: int = 50
    min_interval_seconds: int = 60
    max_consecutive_failures: int = 3
    default_timezone: str = "UTC"
    task_execution_timeout_s: int = 120
    confidence_threshold: float = 0.8

class ImproverSettings(BaseModel):
    enabled: bool = True
    analysis_interval_hours: int = 6
    failure_threshold: int = 3
    workflow_repeat_threshold: int = 3
    digest_day: str = "sunday"
    digest_hour: int = 20
    max_route_overrides: int = 20
    auto_rollback_on_degradation: bool = True
    degradation_threshold: float = 0.15
    max_draft_skill_notifications_per_day: int = 1

class MarketplaceSettings(BaseModel):
    registry_url: str = "https://marketplace.nobla.dev/api/v1"
    self_hosted: bool = False
    allow_external_installs: bool = True
    auto_check_updates: bool = True
    update_check_interval_hours: int = 24
```

---

## 9. File Structure Reference

### New Directories (Phase 5)

```
backend/nobla/
├── events/                    # 5-Foundation
│   ├── __init__.py
│   ├── bus.py
│   └── models.py
├── channels/                  # 5-Foundation + 5A
│   ├── __init__.py
│   ├── base.py
│   ├── bridge.py              # ChannelConnectionState
│   ├── manager.py
│   ├── linking.py
│   ├── telegram.py            # 5A
│   └── discord.py             # 5A
├── skills/                    # 5-Foundation + 5B
│   ├── __init__.py
│   ├── models.py
│   ├── bridge.py              # SkillToolBridge(BaseTool)
│   ├── adapter.py
│   ├── runtime.py
│   ├── security.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── nobla.py
│   │   ├── mcp.py
│   │   ├── openclaw.py
│   │   ├── claude.py
│   │   └── langchain.py
│   └── store/
│       ├── __init__.py
│       ├── registry.py
│       ├── marketplace.py     # 5B
│       └── packages.py        # 5B
├── scheduler/                 # 5A
│   ├── __init__.py
│   ├── parser.py
│   ├── manager.py
│   ├── models.py
│   ├── persistence.py
│   └── tool.py
├── improver/                  # 5B
│   ├── __init__.py
│   ├── observer.py
│   ├── failure_detector.py    # Pre-split from analyzers.py (750-line limit)
│   ├── routing_analyzer.py
│   ├── workflow_recognizer.py
│   ├── actions.py
│   ├── engine.py
│   ├── log.py
│   ├── digest.py
│   ├── persistence.py
│   └── models.py
└── gateway/
    ├── schedule_handlers.py   # 5A
    ├── marketplace_handlers.py # 5B
    └── improver_handlers.py   # 5B
```

### Separate Repo: nobla-registry
```
nobla-registry/
├── api/
│   ├── catalog.py
│   ├── search.py
│   ├── publish.py
│   ├── reviews.py
│   ├── authors.py
│   └── sync.py
├── pipeline/
│   ├── validator.py
│   ├── scanner.py
│   └── tester.py
├── models/
│   ├── skill.py
│   ├── author.py
│   └── review.py
├── config.py
├── Dockerfile
└── docker-compose.yml
```

### Bundled Skills
```
skills/
├── bundled/
│   ├── image-gen-dalle/
│   ├── image-gen-stable-diffusion/
│   ├── video-gen-runway/
│   └── ...
├── drafts/                    # Auto-created by self-improver
└── marketplace/               # User-installed from marketplace
```

---

## 10. Integration Points

How Phase 5 connects to existing architecture:

| New Component | Integrates With | How |
|---------------|----------------|-----|
| Event Bus | app.py lifespan | Initialized first, passed to all services |
| Event Bus | Tool Executor | Emits tool.executed/tool.failed after each execution |
| Event Bus | Memory Orchestrator | Emits memory.consolidated after warm path |
| Event Bus | Approval Manager | Emits tool.approval.requested/resolved |
| Channel Adapters | Gateway | Bridge channel.message.in → chat.send logic |
| Channel Adapters | Approval Manager | Deliver inline approval buttons, resolve via callbacks |
| User Linking | Auth Service | Maps platform identity → Nobla user (JWT-authenticated) |
| Skill Runtime | Tool Registry | Skills register as tools, same executor pipeline |
| Skill Runtime | Sandbox Manager | All skills execute in Docker/gVisor |
| Skill Runtime | Permission Checker | Skills have assigned Tier, enforced by executor |
| Scheduler | APScheduler | Wraps AsyncIOScheduler for cron/date/interval triggers |
| Scheduler | LLM Router | Task execution goes through normal LLM routing |
| Scheduler | Event Bus | Emits schedule.fired/result, consumed by channels |
| Self-Improver | Event Bus | Consumes all events (read-only observer) |
| Self-Improver | LLM Router | Writes routing_overrides table, router checks before defaults |
| Self-Improver | Procedural Memory | Stores successful workflows via existing memory layer |
| Self-Improver | Skill Runtime | Creates draft skills (disabled) from repeated workflows |
| Marketplace Client | Skill Runtime | install() delegates to SkillRuntime.install() |
| Kill Switch | Channel Manager | stop_all() on hard kill |
| Kill Switch | Scheduler | Pause all active tasks on soft kill |
| Kill Switch | Self-Improver | Pause observation and analysis on kill |

---

## 11. JSON-RPC Error Codes

New subsystems extend the existing error code range (`-32001` to `-32012` in `backend/nobla/gateway/protocol.py`):

| Code | Name | Subsystem |
|------|------|-----------|
| `-32020` | `CHANNEL_NOT_LINKED` | Channels — user not linked |
| `-32021` | `CHANNEL_UNAVAILABLE` | Channels — adapter offline |
| `-32030` | `SCHEDULE_AMBIGUOUS_TIME` | Scheduler — parser confidence below threshold |
| `-32031` | `SCHEDULE_VALIDATION_FAILED` | Scheduler — interval/date validation failed |
| `-32032` | `SCHEDULE_LIMIT_REACHED` | Scheduler — max tasks per user |
| `-32033` | `SCHEDULE_NOT_FOUND` | Scheduler — task ID not found |
| `-32040` | `SKILL_INSTALL_TIMEOUT` | Skills — sandbox dry-run exceeded timeout |
| `-32041` | `SKILL_SECURITY_REJECTED` | Skills — security scan failed |
| `-32042` | `SKILL_NOT_FOUND` | Skills — skill ID not found |
| `-32043` | `SKILL_FORMAT_UNKNOWN` | Skills — adapter cannot detect format |
| `-32044` | `SKILL_MCP_UNREACHABLE` | Skills — MCP server connection failed |
| `-32050` | `IMPROVER_PAUSED` | Improver — action rejected while paused |
| `-32051` | `IMPROVER_ROLLBACK_FAILED` | Improver — rollback target not found |
| `-32060` | `MARKETPLACE_UNAVAILABLE` | Marketplace — registry unreachable |
| `-32061` | `MARKETPLACE_PACKAGE_INVALID` | Marketplace — .nsk validation failed |

**Handler registration note:** New handler files (`schedule_handlers.py`, `marketplace_handlers.py`, `improver_handlers.py`) must be imported with `# noqa: F401` in `app.py` to trigger `@rpc_method` decorator registration, matching the existing pattern.

---

## 12. Security Invariants

These hold true across all Phase 5 components (updated post-review):

1. **No open channel access.** Every channel interaction requires a linked Nobla account. Unlinked users get a pairing prompt only.
2. **All skills sandboxed.** Docker/gVisor for every execution, regardless of source or verification status.
3. **Skills disabled by default.** `enabled: false` for every installed skill — bundled, marketplace, or manually imported.
4. **10-second install timeout.** Sandbox dry-run during skill install has a hard 10-second timeout. Exceeded → rejected.
5. **Scheduled tasks require confirmation.** Parser output shown to user with Confirm/Cancel before task creation.
6. **Self-improvements are transparent.** Every action logged with reason, evidence, and one-click rollback.
7. **Auto-rollback notifies immediately.** Degradation-triggered rollbacks send urgent notification, never wait for digest.
8. **Correlation tracing.** `correlation_id` propagates from channel.message.in through all events/audit to channel.message.out.
9. **Kill switch stops everything.** Channels stop, scheduler pauses, improver pauses, pending approvals denied.
10. **750-line file limit.** No source file exceeds 750 lines.
11. **Transactional skill install.** DB persistence before registry registration. Any failure after DB write triggers rollback.
12. **Routing override precedence.** User-manual overrides always win over self-improver auto-overrides.
13. **Offline notifications retained.** Scheduled task results stored for 30 days, delivered on next connection.

---

## 13. Competitive Context

This redesign directly addresses the MaxClaw competitive gap analysis (see `.firecrawl/competitor-research/ANALYSIS-MaxClaw-vs-Nobla.md`):

| MaxClaw Feature | Nobla Response | Phase |
|----------------|---------------|-------|
| Telegram/Discord/Slack bots | Telegram + Discord with generic abstraction | 5A |
| NL scheduled tasks | Hybrid NLP + LLM parser with confirmation | 5A |
| Self-evolution loop | Self-improving agent with transparent audit | 5B |
| SkillHub (8,700+ skills) | Universal adapter (MCP + OpenClaw + Claude + LangChain) | 5B |
| Cloud-hosted 24/7 | Event-driven scheduler + always-on channel bots | 5A |
| Skill monetization | Free MVP, payments deferred | Future |

**Nobla advantages MaxClaw cannot match:**
- Privacy-first: all data local, self-hosted marketplace option
- Security: 4-tier permissions, kill switch, sandbox, audit trail (MaxClaw: 1.6/10)
- LLM flexibility: 6 providers + Ollama (MaxClaw: locked to MiniMax M2.7)
- OS-level control: mouse, keyboard, files, apps, SSH/SFTP (MaxClaw: browser only)
- Transparency: every self-improvement logged, explained, rollbackable
- Data jurisdiction: no Chinese data law exposure (MaxClaw: PIPL)
