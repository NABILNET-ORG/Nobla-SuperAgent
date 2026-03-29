# Phase 5-Channels — Continuation Prompt (Post-Slack + Signal)

Paste this at the start of a new session to continue Phase 5 channel adapter development.

---

## Prompt

Continue Phase 5 implementation — building the next batch of messaging channel adapters. WhatsApp, Slack, and Signal are complete. Pick the next adapter(s) from the priority list below.

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
- Business Cloud API adapter (webhook-only), HMAC-SHA256 verification, Graph API media, interactive messages (buttons + lists), keyword commands, status tracking, reaction events

**Phase 5-Channels — Slack (142 tests):**
- Dual mode: Socket Mode (WebSocket, default) + Events API (HTTP webhook)
- Block Kit formatter (headers, code blocks, dividers, buttons)
- v2 file upload pipeline, slash commands + keyword fallback
- RateLimitQueue with Retry-After backoff, thread-aware replies
- Channel mention-only, HMAC-SHA256 with replay protection

**Phase 5-Channels — Signal (72 tests):**
- JSON-RPC daemon (signal-cli), plain text formatter
- File-path media with path traversal protection
- Commands (case-insensitive), group mentions, disappearing messages
- Read receipts, Future-based response routing, exponential backoff reconnect

**Phase 5B.1-Learning (130 tests) + Phase 5B.2-Marketplace (129 tests):**
- Self-improving agent + Skills marketplace (both complete)

**Phase 6 — Complete (858 tests):**
- NL Scheduler, Multi-Agent System v2, Webhooks & Workflows, Templates & Import/Export

**Test count: 1,633 total (273 Flutter + 1,360 backend)**

### Adapter Pattern (6 files per adapter)

Each adapter follows this exact structure under `backend/nobla/channels/<name>/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Lazy import wrapper (`__getattr__`) |
| `models.py` | `<Name>UserContext` dataclass + API constants |
| `formatter.py` | Platform formatting → `format_response()` returning `list[FormattedMessage]` |
| `media.py` | Platform media upload/download → unified `Attachment` |
| `handlers.py` | `<Name>Handlers` — `set_send_fn()` wiring, message routing, commands, linking, event bus emission |
| `adapter.py` | `<Name>Adapter(BaseChannelAdapter)` — 7 ABC methods: name, start, stop, send, send_notification, parse_callback, health_check |

Plus:
- Add `<Name>Settings` to `backend/nobla/config/settings.py` (with `@model_validator` for required fields when enabled)
- Add init block to `backend/nobla/gateway/lifespan.py` → `_init_channels()` (with `try/except` for graceful failure)
- Create `backend/tests/test_<name>_adapter.py` (~75-100 tests)

### What to Build Next

12 remaining platform adapters. Prioritized order:

#### Tier 1 — High Priority
1. **Microsoft Teams** — Bot Framework REST API, Adaptive Cards, OAuth2 bearer token, conversation references for proactive messaging
2. **Facebook Messenger** — Send/Receive API, webhook verification (X-Hub-Signature-256, same as WhatsApp), message templates, quick replies, persistent menu
3. **Slack Enterprise Grid** — extend existing Slack adapter with org-level features (Enterprise Grid API, cross-workspace messaging)

#### Tier 2 — Medium Priority
4. **LINE** — Messaging API, Flex Messages (JSON-based rich layouts), rich menus, multicast
5. **Viber** — REST API, keyboard buttons, carousel, broadcast
6. **WeChat** — Official Account API, XML message format, JSAPI ticket verification
7. **Matrix** — Client-Server API (Synapse), room-based, optional E2EE via libolm

#### Tier 3 — Lower Priority
8. **Twilio SMS** — REST API, webhook (X-Twilio-Signature HMAC-SHA1), MMS media
9. **Email (IMAP/SMTP)** — aiosmtplib + aioimaplib, MIME parsing, attachment handling
10. **IRC** — asyncio IRC client, channel/PM modes, CTCP
11. **XMPP/Jabber** — aioxmpp or slixmpp, presence, MUC (multi-user chat)
12. **Google Chat** — Bot API, Cards v2 (similar to Adaptive Cards), service account auth

### Key Files to Reference

- `backend/nobla/channels/base.py` — BaseChannelAdapter ABC (the contract)
- `backend/nobla/channels/slack/` — Best reference for HTTP API + WebSocket dual mode, Block Kit rich formatting, rate limiting
- `backend/nobla/channels/signal/` — Best reference for non-HTTP transport (JSON-RPC/TCP)
- `backend/nobla/channels/whatsapp/` — Best reference for webhook-only HTTP adapter with signature verification
- `backend/nobla/channels/telegram/` — Reference for polling + webhook dual mode
- `backend/nobla/channels/discord/` — Reference for persistent WebSocket connection
- `backend/nobla/channels/manager.py` — ChannelManager (register adapters)
- `backend/nobla/channels/linking.py` — UserLinkingService (user linking + pairing codes)
- `backend/nobla/events/bus.py` — NoblaEventBus (emit/subscribe events)
- `backend/nobla/config/settings.py` — Settings class (add new settings after SignalSettings)
- `backend/nobla/gateway/lifespan.py` — `_init_channels()` (wire new adapters)
- `backend/tests/test_slack_adapter.py` — Most comprehensive test file (142 tests, good pattern)

### Design Constraints

- 750-line hard limit per file
- All adapters implement BaseChannelAdapter ABC (7 methods)
- Use event bus for cross-component communication
- Security: channel tokens stored encrypted, pairing codes for user linking, timestamp staleness checks where applicable, path sanitization for file-based media
- Graceful degradation: adapter start failure shouldn't block other adapters
- httpx for all HTTP API calls (consistent with existing adapters)
- Handler-to-adapter wiring via `set_send_fn()` pattern
- All adapters support keyword commands: `!start`, `!link`, `!unlink`, `!status` (or platform-native equivalents like slash commands)
- Rate limiting: queue with `Retry-After` backoff for platforms with rate limits
- Reconnection: exponential backoff for persistent connections

### Previous Specs & Plans (for reference)

- `docs/superpowers/specs/2026-03-29-slack-signal-adapters-design.md` — Slack + Signal design spec
- `docs/superpowers/plans/2026-03-29-slack-signal-adapters.md` — Slack + Signal implementation plan
