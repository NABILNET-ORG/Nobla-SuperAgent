# Phase 5-Channels — Continuation Prompt (Post-WhatsApp)

Paste this at the start of a new session to continue Phase 5 channel adapter development.

---

## Prompt

Continue Phase 5 implementation — building the next messaging channel adapters (Slack, Signal) on top of the Phase 5-Foundation infrastructure. WhatsApp is complete.

### What's Already Done

**Phase 5-Foundation (106 tests):**
- Event bus (async pub/sub, wildcards, priority, backpressure)
- Channel abstraction (BaseChannelAdapter ABC, ChannelManager, UserLinkingService, bridge)
- Skill runtime (universal adapter, security scanner, tool bridge)
- Tool event wiring + gateway lifespan wiring

**Phase 5A — Telegram + Discord (173 tests):**
- Telegram adapter: polling + webhook, MarkdownV2, media, /commands, group mention-only, inline buttons (95 tests)
- Discord adapter: WebSocket gateway, ui.Button views, media, !commands, guild mention-only, interactions (78 tests)

**Phase 5-Channels — WhatsApp (94 tests):**
- WhatsApp Business Cloud API adapter (webhook-only)
- HMAC-SHA256 signature verification (`X-Hub-Signature-256`)
- Webhook challenge verification (GET subscribe flow)
- Graph API media upload/download (`files.uploadV2` equivalent)
- Interactive messages (reply buttons max 3, lists max 10)
- Keyword commands (`!start`, `!link`, `!unlink`, `!status`) — WhatsApp has no slash commands
- Message status tracking (sent/delivered/read/failed events)
- Reaction events (emoji on message)
- `WhatsAppSettings` in config (access_token, phone_number_id, app_secret, verify_token, api_version)
- Gateway wiring in `_init_channels()` lifespan
- httpx async client for all Graph API calls

**Test count: 1,415 total (273 Flutter + 1,142 backend)**

### Adapter Pattern (6 files per adapter)

Each adapter follows this exact structure under `backend/nobla/channels/<name>/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Lazy import wrapper |
| `models.py` | `<Name>UserContext` dataclass + API constants (MAX_MSG, MIME map) |
| `formatter.py` | Platform formatting (escaping, splitting, button building) → `format_response()` |
| `media.py` | Platform media upload/download → unified `Attachment` |
| `handlers.py` | `<Name>Handlers` class — message routing, commands, linking, event bus emission |
| `adapter.py` | `<Name>Adapter(BaseChannelAdapter)` — lifecycle, send, health_check |

Plus:
- Add `<Name>Settings` to `backend/nobla/config/settings.py` + wire into `Settings` class
- Add init block to `backend/nobla/gateway/lifespan.py` → `_init_channels()`
- Create `backend/tests/test_<name>_adapter.py` (~90 tests)

### What to Build Next

#### 1. Slack Adapter

**Key design decisions:**
- **Dual mode:** Socket Mode (WebSocket, needs `app_token` xapp-*) or Events API (HTTP, needs `signing_secret`)
- **Signature verification:** `v0=HMAC-SHA256(signing_secret, v0:timestamp:body)` in `X-Slack-Signature`
- **Block Kit:** Rich formatting via structured JSON blocks (sections, buttons, dividers)
- **Slash commands:** Native `/nobla start`, `/nobla link <id>`, `/nobla status`
- **Threads:** Reply in-thread by setting `thread_ts`
- **Channel types:** DM, group DM, public/private channels; mention-only for non-DM
- **Bot mention:** `<@BOT_USER_ID>` in message text
- **File upload v2:** `files.getUploadURLExternal` → PUT → `files.completeUploadExternal`
- **Rate limits:** Tier-based (1-4), respect `Retry-After` headers
- **Max message:** 3000 chars for `chat.postMessage`

**SlackSettings fields:**
- enabled, bot_token (xoxb-*), app_token (xapp-*, for Socket Mode), signing_secret, mode ("socket" or "events"), command_name ("/nobla"), group_activation, max_file_size_mb

**Target: ~90 tests**

#### 2. Signal Adapter

**Key design decisions:**
- **signal-cli** as subprocess or JSON-RPC daemon (no official bot API)
- **Plain text** formatting only (no rich blocks)
- **Groups:** Via group ID, mention-only activation
- **Media:** Attachments via file paths
- **Commands:** `/start`, `/link`, `/unlink`, `/status` (text prefix)
- **Receipts:** Delivery/read receipts as events
- **Registration:** Requires a phone number for the bot

**SignalSettings fields:**
- enabled, phone_number, signal_cli_path, mode ("json-rpc" or "subprocess"), data_dir, group_activation, max_file_size_mb

**Target: ~75 tests**

### Key Files to Reference

- `backend/nobla/channels/base.py` — BaseChannelAdapter ABC (the contract)
- `backend/nobla/channels/whatsapp/` — Most recent adapter (closest pattern to follow)
- `backend/nobla/channels/telegram/` — Reference for dual-mode (polling + webhook)
- `backend/nobla/channels/discord/` — Reference for WebSocket persistent connection
- `backend/nobla/channels/manager.py` — ChannelManager (register here)
- `backend/nobla/channels/linking.py` — UserLinkingService (link users)
- `backend/nobla/events/bus.py` — NoblaEventBus (emit/subscribe events)
- `backend/nobla/config/settings.py` — Settings (add SlackSettings, SignalSettings)
- `backend/nobla/gateway/lifespan.py` — `_init_channels()` (wire new adapters)
- `backend/tests/test_whatsapp_adapter.py` — Most recent test file (pattern to follow)

### Design Constraints

- 750-line hard limit per file
- All adapters implement BaseChannelAdapter ABC
- Use event bus for cross-component communication
- Security: channel tokens stored encrypted, pairing codes for user linking
- Graceful degradation: adapter start failure shouldn't block other adapters
- httpx for all HTTP API calls (consistent with WhatsApp)
