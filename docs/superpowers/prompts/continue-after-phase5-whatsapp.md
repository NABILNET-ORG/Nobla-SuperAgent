# Phase 5-Channels — Continuation Prompt (Post-Slack + Signal)

Paste this at the start of a new session to continue development. Slack and Signal are complete — next up is the remaining channel adapters.

---

## Prompt

Continue Phase 5 implementation — the next batch of messaging channel adapters. WhatsApp, Slack, and Signal are complete.

### What's Already Done

**Phase 5-Foundation (106 tests):**
- Event bus (async pub/sub, wildcards, priority, backpressure)
- Channel abstraction (BaseChannelAdapter ABC, ChannelManager, UserLinkingService, bridge)
- Skill runtime (universal adapter, security scanner, tool bridge)
- Tool event wiring + gateway lifespan wiring

**Phase 5A — Telegram + Discord (173 tests):**
- Telegram adapter: polling + webhook, MarkdownV2, media, /commands, group mention-only, inline buttons (95 tests)
- Discord adapter: WebSocket gateway, ui.Button views, media, !commands, guild mention-only, interactions (78 tests)

**Phase 5-Channels — WhatsApp ✅ (94 tests):**
- WhatsApp Business Cloud API adapter (webhook-only)
- HMAC-SHA256 signature verification (`X-Hub-Signature-256`)
- Webhook challenge verification (GET subscribe flow)
- Graph API media upload/download (`files.uploadV2` equivalent)
- Interactive messages (reply buttons max 3, lists max 10)
- Keyword commands (`!start`, `!link`, `!unlink`, `!status`)
- Message status tracking (sent/delivered/read/failed events)
- Reaction events (emoji on message)
- `WhatsAppSettings` in config + gateway wiring
- httpx async client for all Graph API calls

**Phase 5-Channels — Slack ✅ (142 tests):**
- Dual mode: Socket Mode (WebSocket, default) + Events API (HTTP webhook)
- Block Kit formatter (headers, code blocks, dividers, buttons via `markdown_to_blocks`)
- v2 file upload pipeline (getUploadURLExternal → PUT → completeUploadExternal)
- Slash commands (`/nobla start|link|unlink|status`) + keyword fallback (`!start` etc.)
- RateLimitQueue with `Retry-After` header parsing and re-queue
- Thread-aware replies (`thread_ts` propagation)
- Channel mention-only policy (`<@BOT_USER_ID>`), always respond in DMs
- Socket Mode envelope acknowledgment within 3s + exponential backoff reconnect
- HMAC-SHA256 signature verification with 5-min timestamp staleness check (replay protection)
- `SlackSettings` in config + gateway wiring
- Response-routing for concurrent sends through rate limit queue

**Phase 5-Channels — Signal ✅ (72 tests):**
- JSON-RPC daemon transport (signal-cli, `asyncio.open_connection`)
- Plain text formatter (Signal has no rich formatting)
- File-path based media with path traversal protection (`os.path.basename` + UUID prefix)
- `/start`, `/link`, `/unlink`, `/status` commands (case-insensitive)
- Group mention detection (bot number/UUID in `mentions` array)
- Disappearing messages: honors `expiresInSeconds` TTL, sets `metadata.disappearing` flag
- Read receipts sent via `sendReceipt` RPC when bot processes a message
- Exponential backoff reconnection (`min(2^attempt, 30)` seconds)
- Response-routing dispatcher (Future-based) to prevent StreamReader race between receive loop and outbound RPC calls
- `SignalSettings` in config + gateway wiring

**Phase 5B.1-Learning ✅ (106 backend + 24 Flutter tests):**
- FeedbackCollector, PatternDetector, SkillGenerator, ABTestManager, ProactiveEngine
- LearningService orchestrator, REST API (22 routes), LLM Router A/B hook
- Flutter Agent Intelligence screen (4 tabs)

**Phase 5B.2-Marketplace ✅ (97 backend + 32 Flutter tests):**
- MarketplaceRegistry, SkillPackager, SkillDiscovery, UsageTracker
- MarketplaceService, REST API (15 routes), Flutter marketplace UI

**Test count: 1,633 total (273 Flutter + 1,360 backend)**

### Adapter Pattern (6 files per adapter)

Each adapter follows this exact structure under `backend/nobla/channels/<name>/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Lazy import wrapper (`__getattr__`) |
| `models.py` | `<Name>UserContext` dataclass + API constants (MAX_MSG, MIME map) |
| `formatter.py` | Platform formatting (escaping, splitting, button building) → `format_response()` |
| `media.py` | Platform media upload/download → unified `Attachment` |
| `handlers.py` | `<Name>Handlers` class — `set_send_fn()` wiring, message routing, commands, linking, event bus emission |
| `adapter.py` | `<Name>Adapter(BaseChannelAdapter)` — lifecycle, send, send_notification, parse_callback, health_check |

Plus:
- Add `<Name>Settings` to `backend/nobla/config/settings.py` + wire into `Settings` class
- Add init block to `backend/nobla/gateway/lifespan.py` → `_init_channels()`
- Create `backend/tests/test_<name>_adapter.py` (~75-100 tests)

### What to Build Next

12 remaining platform adapters. Prioritized order:

#### Tier 1 — High Priority
1. **Microsoft Teams** — Bot Framework REST API, Adaptive Cards, OAuth2
2. **Facebook Messenger** — Send/Receive API, webhook verification, templates
3. **Slack Enterprise Grid** — (extend existing Slack adapter with org-level features)

#### Tier 2 — Medium Priority
4. **LINE** — Messaging API, Flex Messages, rich menus
5. **Viber** — REST API, keyboard buttons, carousel
6. **WeChat** — Official Account API, XML message format
7. **Matrix** — Client-Server API (Synapse), E2EE optional

#### Tier 3 — Lower Priority
8. **Twilio SMS** — REST API, webhook
9. **Email (IMAP/SMTP)** — aiosmtplib + aioimaplib
10. **IRC** — asyncio IRC client
11. **XMPP/Jabber** — aioxmpp or slixmpp
12. **Google Chat** — Bot API, Cards v2

### Key Files to Reference

- `backend/nobla/channels/base.py` — BaseChannelAdapter ABC (the contract)
- `backend/nobla/channels/slack/` — Most recent adapter (dual mode, Block Kit, rate limiting)
- `backend/nobla/channels/signal/` — Reference for non-HTTP transport (JSON-RPC)
- `backend/nobla/channels/whatsapp/` — Reference for webhook-only HTTP adapter
- `backend/nobla/channels/telegram/` — Reference for dual-mode (polling + webhook)
- `backend/nobla/channels/discord/` — Reference for WebSocket persistent connection
- `backend/nobla/channels/manager.py` — ChannelManager (register here)
- `backend/nobla/channels/linking.py` — UserLinkingService (link users)
- `backend/nobla/events/bus.py` — NoblaEventBus (emit/subscribe events)
- `backend/nobla/config/settings.py` — Settings (add new adapter settings here)
- `backend/nobla/gateway/lifespan.py` — `_init_channels()` (wire new adapters)

### Design Constraints

- 750-line hard limit per file
- All adapters implement BaseChannelAdapter ABC (7 methods: name, start, stop, send, send_notification, parse_callback, health_check)
- Use event bus for cross-component communication
- Security: channel tokens stored encrypted, pairing codes for user linking, timestamp staleness checks where applicable
- Graceful degradation: adapter start failure shouldn't block other adapters
- httpx for all HTTP API calls (consistent with existing adapters)
- Handler-to-adapter wiring via `set_send_fn()` pattern
- All adapters support: `!start`/`!link`/`!unlink`/`!status` keyword commands (or platform-native equivalents)

### Design Specs & Plans

- `docs/superpowers/specs/2026-03-29-slack-signal-adapters-design.md` — Slack + Signal spec (reference for adapter design decisions)
- `docs/superpowers/plans/2026-03-29-slack-signal-adapters.md` — Slack + Signal implementation plan (reference for task structure)
