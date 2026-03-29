# Phase 5-Channels: Slack + Signal Adapters Design

**Date:** 2026-03-29
**Status:** Approved
**Approach:** Parallel build via subagents (Approach B)

---

## Overview

Add Slack and Signal messaging channel adapters to the Phase 5 channel infrastructure. Both follow the established 6-file adapter pattern (models, formatter, media, handlers, adapter, `__init__`) and implement `BaseChannelAdapter` ABC.

**Test targets:** Slack ~100, Signal ~75

---

## Slack Adapter

### Mode

- **Dual mode:** Socket Mode (WebSocket, default) or Events API (HTTP webhook)
- Socket Mode default aligns with Nobla's privacy-first, self-hosted philosophy (no public endpoint needed)
- Events API available for production/hosted deployments

### Files

#### `models.py` (~80 lines)
- `CHANNEL_NAME = "slack"`
- `MAX_MESSAGE_LENGTH = 3000`
- `SlackUserContext`: `user_id`, `team_id`, `channel_id`, `thread_ts`, `is_dm`, `is_bot_mentioned`, `timestamp`
- Rate limit tier constants

#### `formatter.py` (~250 lines)
- Full markdown-to-Block Kit conversion: sections with `mrkdwn`, header blocks, code blocks, dividers, button action blocks
- `escape_slack_text(text)` — escape `&`, `<`, `>`
- `split_message(text, limit=3000)`
- `build_button_blocks(actions)` — InlineAction list to Block Kit button elements
- `format_response(response) -> list[FormattedMessage]`
- `FormattedMessage`: `text`, `blocks: list[dict]`, `thread_ts`

#### `media.py` (~200 lines)
- v2 file upload pipeline: `get_upload_url_external()` -> PUT bytes -> `complete_upload_external()`
- `download_file(url, bot_token, client)` -> bytes
- `send_attachment(bot_token, channel_id, attachment, thread_ts, client)`
- Size validation against `max_file_size_mb`

#### `handlers.py` (~450 lines)
- `SlackHandlers` with `UserLinkingService` + `NoblaEventBus` injection
- `set_send_fn(fn)` — handler-to-adapter wiring (adapter registers its send function after construction, same pattern as WhatsApp)
- `handle_event(payload)` — dispatcher for Socket Mode / Events API events
- `_handle_message(ctx, event)` — text extraction, `<@BOT_USER_ID>` mention detection, command parsing
- Slash command parser: `/nobla start|link|unlink|status` (space-separated sub-commands)
- Also recognizes `!start`, `!link`, `!unlink`, `!status` as fallback keyword commands in text messages (consistency with WhatsApp/Telegram/Discord)
- `_handle_interactive(payload)` — button clicks -> `channel.callback` event
- `RateLimitQueue` — async worker with `Retry-After` header parsing and re-queue
- Events: `channel.message.in`, `channel.callback`, `channel.message.status`

#### `adapter.py` (~300 lines)
- **Socket Mode:** WebSocket to `wss://wss-primary.slack.com`, handles `hello`, `events_api`, `interactive`, `slash_commands` envelope types
- **Events API:** HTTP webhook with `v0=HMAC-SHA256(signing_secret, v0:timestamp:body)` signature verification, `url_verification` challenge
- `start()`: connect WebSocket (socket) or register webhook (events)
- `stop()`: close WebSocket / cleanup
- `send()`: format + `chat.postMessage` with `thread_ts` through rate limit queue
- `send_notification()`: plain text via `chat.postMessage` (implements ABC requirement)
- `parse_callback(raw_callback)`: extract `action_id` from Block Kit interactive payload (implements ABC requirement)
- `health_check()`: `auth.test` API call
- **Socket Mode envelope acknowledgment:** Each received envelope must be acknowledged within 3 seconds by sending `{"envelope_id": "<id>"}` back on the WebSocket. Processing happens after ack to avoid redelivery. Envelope ID is extracted from the `envelope_id` field of each received message.
- **Connection handshake:** POST `https://slack.com/api/apps.connections.open` with `app_token` to get a WebSocket URL, then connect. No external `slack_sdk` dependency — uses raw `websockets` + `httpx`.
- **Reconnect:** On WebSocket close, exponential backoff reconnect (1s, 2s, 4s... max 30s)

#### `__init__.py` (~12 lines)
- Lazy `__getattr__` import pattern

### Settings

```python
class SlackSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""          # xoxb-*
    app_token: str = ""          # xapp-* (Socket Mode)
    signing_secret: str = ""     # Events API HMAC key
    mode: str = "socket"         # "socket" or "events"
    command_name: str = "/nobla"
    webhook_path: str = "/webhook/slack"
    group_activation: str = "mention"
    max_file_size_mb: int = 100
```

### Key Design Decisions

1. **Thread behavior:** Always reply in-thread (`thread_ts`) when message originates from thread. Never mirror to main channel.
2. **Channel response:** Respond only on `<@BOT_USER_ID>` mention in public/private channels. Always respond in DMs (im/mpim).
3. **Block Kit:** Full markdown-to-blocks conversion (sections, headers, code blocks, dividers, buttons). mrkdwn-only not acceptable.
4. **Rate limiting:** Queue with `Retry-After` backoff. Parse header and re-queue, no simple retry loops.
5. **Slash commands:** `/nobla start`, `/nobla link <id>`, `/nobla unlink`, `/nobla status` (space-separated sub-commands).

---

## Signal Adapter

### Mode

- **JSON-RPC daemon only** (persistent connection, better performance)
- Subprocess mode not supported as default
- Assumes signal-cli is already registered with a phone number (registration is a setup/docs concern)

### Files

#### `models.py` (~60 lines)
- `CHANNEL_NAME = "signal"`
- `MAX_MESSAGE_LENGTH = 6000`
- `SignalUserContext`: `source_number`, `source_uuid`, `group_id`, `is_group`, `is_bot_mentioned`, `timestamp`, `expires_in_seconds`
- JSON-RPC method constants

#### `formatter.py` (~100 lines)
- Plain text only (no rich formatting — Signal doesn't support it)
- `split_message(text, limit=6000)`
- `format_response(response) -> list[FormattedMessage]`
- `FormattedMessage`: `text` only

#### `media.py` (~150 lines)
- File-path based (signal-cli uses local paths)
- `save_attachment_to_disk(attachment, data_dir) -> str`
- `load_attachment_from_path(path, mime_type) -> Attachment`
- `send_attachment(phone_number, attachment, data_dir, rpc_client)`
- Size validation

#### `handlers.py` (~350 lines)
- `SignalHandlers` with `UserLinkingService` + `NoblaEventBus` injection
- `set_send_fn(fn)` — handler-to-adapter wiring (adapter registers its send function after construction)
- `handle_message(envelope)` — JSON-RPC envelope dispatcher
- `_handle_data_message(ctx, data_message)` — text + attachments, command parsing, disappearing message TTL
- `_handle_receipt(ctx, receipt)` — delivery/read receipts -> `channel.message.status`
- Send read receipts back via `sendReceipt` RPC
- Commands: `/start`, `/link`, `/unlink`, `/status` (text prefix)
- Group mention detection: bot number in `mentions` array
- Disappearing messages: if `expires_in_seconds > 0`, set metadata flag preventing downstream persistence beyond TTL

#### `adapter.py` (~250 lines)
- JSON-RPC daemon: connect to signal-cli socket (`localhost:7583` default)
- `start()`: connect, start receive loop
- `stop()`: close connection
- `send()`: format + `sendMessage` RPC (to number or group)
- `send_notification()`: plain text via `sendMessage` RPC (implements ABC requirement)
- `parse_callback(raw_callback)`: no-op passthrough — Signal has no interactive callbacks, returns `("", {})`
- `send_read_receipt()`: `sendReceipt` RPC with type=read
- `health_check()`: `version` RPC call
- Reconnection logic for daemon connection drops

#### `__init__.py` (~12 lines)
- Lazy `__getattr__` import pattern

### Settings

```python
class SignalSettings(BaseModel):
    enabled: bool = False
    phone_number: str = ""
    signal_cli_path: str = "signal-cli"
    mode: str = "json-rpc"
    rpc_host: str = "localhost"
    rpc_port: int = 7583
    data_dir: str = ""
    group_activation: str = "mention"
    max_file_size_mb: int = 100
```

### Key Design Decisions

1. **JSON-RPC only:** Subprocess mode not acceptable as default. Persistent daemon for performance.
2. **No registration flow:** Assume signal-cli is pre-registered. Setup belongs in docs.
3. **Disappearing messages:** Honor the timer. Bot must not store/forward content beyond TTL.
4. **Read receipts:** Send read receipts when bot processes a message.
5. **Plain text only:** No rich formatting (Signal limitation).

---

## Gateway Wiring

### `_init_channels()` additions
- Slack: `SlackHandlers(linking, event_bus, ...)` -> `SlackAdapter(settings, handlers)` -> register + start
- Signal: `SignalHandlers(linking, event_bus, ...)` -> `SignalAdapter(settings, handlers)` -> register + start

### Webhook routes
- `/webhook/slack` — Slack Events API + slash commands + interactivity (only used in Events API mode)
- Signal has no webhook route — communication is via JSON-RPC daemon only

### Settings additions
- `SlackSettings` in `ChannelSettings` or top-level `Settings`
- `SignalSettings` in `ChannelSettings` or top-level `Settings`

---

## Test Strategy

### Slack (~100 tests)
- Models + constants validation
- Formatter: escape, split, Block Kit conversion (sections, headers, code, dividers, buttons)
- Media: upload v2 pipeline, download, size validation
- Handlers: message routing, mention detection, slash commands, interactive callbacks, rate limit queue, event emission
- Adapter: Socket Mode WebSocket lifecycle, Events API signature verification, challenge response, send, health check
- Settings: validation, required fields when enabled

### Signal (~75 tests)
- Models + constants validation
- Formatter: split, plain text formatting
- Media: save to disk, load from path, size validation
- Handlers: envelope dispatch, data message, receipts, read receipt sending, commands, group mentions, disappearing messages, event emission
- Adapter: JSON-RPC connection, send, receive loop, reconnection, health check
- Settings: validation, required fields when enabled
