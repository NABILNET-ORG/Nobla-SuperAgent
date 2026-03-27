# Phase 5 — Channel Adapters Continuation Prompt

Paste this at the start of a new session to continue Phase 5 development.

---

## Prompt

Continue Phase 5 implementation — building the first messaging channel adapters on top of the Phase 5-Foundation infrastructure.

### What's Already Done (Phase 5-Foundation — 106 tests passing)

**Event Bus** (`backend/nobla/events/`):
- `models.py` — NoblaEvent frozen dataclass (event_type, source, payload, user_id, conversation_id, timestamp, correlation_id, priority)
- `bus.py` — NoblaEventBus: async pub/sub, fnmatch wildcard subscriptions (tool.*, *), priority dispatch (higher first, FIFO within same), handler isolation (try/except per handler), backpressure (10K queue, drops non-urgent on overflow, urgent never dropped), start/stop lifecycle with drain
- 25 unit tests in `backend/tests/test_event_bus.py`

**Channel Abstraction** (`backend/nobla/channels/`):
- `base.py` — AttachmentType, Attachment, InlineAction, ChannelMessage, ChannelResponse, BaseChannelAdapter ABC (name, start, stop, send, send_notification, parse_callback, health_check)
- `manager.py` — ChannelManager: register/unregister adapters, start_all/stop_all, deliver to preferred channel with fallback, broadcast for urgent, health check
- `linking.py` — UserLinkingService: link/unlink nobla user to channel identity, resolve user from any channel, get all channels for a user, pairing code flow with 5-min TTL
- `bridge.py` — ChannelConnectionState helper (mirrors gateway ConnectionState interface)
- 31 unit tests in `backend/tests/test_channels.py`

**Skill Runtime** (`backend/nobla/skills/`):
- `models.py` — SkillSource enum, SkillCategory enum (9 existing + 7 marketplace) with to_tool_category(), SkillManifest dataclass, NoblaSkill ABC
- `bridge.py` — SkillToolBridge(BaseTool) wraps NoblaSkill for ToolRegistry
- `adapter.py` — FormatAdapter ABC, UniversalSkillAdapter with priority-ordered detection
- `adapters/nobla.py` — NoblaAdapter for native format
- `runtime.py` — SkillRuntime: transactional install with rollback, uninstall, enable/disable, upgrade, event emission
- `security.py` — SkillSecurityScanner: dependency blocklist, tier escalation, source code patterns, manifest sanity
- 39 unit tests in `backend/tests/test_skills.py`

**Tool Event Wiring** (`backend/nobla/tools/executor.py`):
- ToolExecutor accepts optional event_bus, emits tool.executed / tool.failed events with correlation_id
- Wired in `backend/nobla/gateway/app.py` lifespan

**Gateway Wiring** (`backend/nobla/gateway/`):
- `app.py` — event bus inits first, channel manager + skill runtime init after tool platform, cleanup on shutdown
- `channel_handlers.py` — service setters/getters for channel_manager, linking_service, event_bus

**Settings** (`backend/nobla/config/settings.py`):
- EventBusSettings (max_queue_depth), ChannelSettings (enabled_channels, max_reconnect_attempts, health_check_interval_seconds), SkillRuntimeSettings (skills_dir, max_installed, auto_update)

**Integration Tests** (11 tests in `backend/tests/integration/test_phase5_foundation.py`):
- Event bus pipeline: tool.executed/tool.failed events reach subscribers, wildcards, correlation_id propagation
- Channel manager: register/start/stop lifecycle, subscribes to tool events
- Skill runtime: install emits event, registers bridge in tool registry
- Full pipeline: tool execution → event bus → subscriber notification, multi-subscriber fan-out, handler isolation

### What to Build Next

Build the first 2-3 channel adapters. Recommended order:

1. **Telegram adapter** — Most straightforward bot API, good starting point
   - Implement `BaseChannelAdapter` with python-telegram-bot or aiogram
   - Handle text messages, inline buttons, media (images/audio/files)
   - Support group chat with @mention activation
   - Emit `channel.message.in` / `channel.message.out` events on the event bus
   - Register RPC handlers in `channel_handlers.py` for config/status

2. **Discord adapter** — Similar to Telegram, uses discord.py
   - Text channels + DM support
   - Slash commands integration
   - Embed formatting for rich responses

3. **WebChat adapter** — Browser-based fallback (REST/WebSocket)
   - Simplest adapter, useful for testing
   - Maps to existing WebSocket gateway connection

For each adapter:
- Create `backend/nobla/channels/adapters/<name>.py`
- Write tests in `backend/tests/test_channel_<name>.py`
- Add configuration to `ChannelSettings` if needed
- Wire into gateway lifespan (register adapter with ChannelManager)
- Test with the event bus (channel events should propagate)

### Key Files to Reference
- `backend/nobla/channels/base.py` — BaseChannelAdapter ABC (the contract)
- `backend/nobla/channels/manager.py` — ChannelManager (register here)
- `backend/nobla/channels/linking.py` — UserLinkingService (link channel users to Nobla users)
- `backend/nobla/events/bus.py` — NoblaEventBus (emit/subscribe events)
- `backend/nobla/events/models.py` — NoblaEvent (event data model)
- `backend/nobla/gateway/app.py` — Lifespan (wire new adapters here)
- `backend/nobla/gateway/channel_handlers.py` — RPC handlers for channel operations
- `Plan.md` — Phase 5 channel list (Telegram, Discord, WhatsApp, Slack, etc.)

### Design Constraints
- 750-line hard limit per file
- Each adapter is a separate file in `backend/nobla/channels/adapters/`
- All adapters must implement BaseChannelAdapter ABC
- Use event bus for cross-component communication (don't import other modules directly)
- Security: channel tokens stored encrypted, pairing codes for user linking
- Graceful degradation: adapter start failure shouldn't block other adapters
