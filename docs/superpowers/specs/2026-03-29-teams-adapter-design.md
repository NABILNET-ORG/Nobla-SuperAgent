# Microsoft Teams Channel Adapter — Design Spec

**Phase:** 5-Channels (Teams)
**Date:** 2026-03-29
**Status:** Approved
**Test target:** ~100 tests

---

## 1. Overview

Microsoft Teams adapter for Nobla Agent using Azure Bot Framework REST API with OAuth2 client_credentials authentication. Webhook-only inbound transport with JWT validation. Adaptive Cards for rich formatting. Multi-tenant support.

Follows the established 6-file adapter pattern under `backend/nobla/channels/teams/`.

## 2. Architecture & Data Flow

### Inbound (Teams → Nobla)

```
Teams Cloud → POST /webhook/teams (JWT in Authorization header)
  → TeamsAdapter.handle_webhook()
    → Validate JWT (Microsoft OpenID keys, cached with background refresh)
    → Parse Activity object → TeamsUserContext
    → TeamsHandlers.handle_activity()
      → DM? Always process. Channel? Only if @mentioned.
      → Keyword command? Dispatch. Otherwise → linking → event bus emit
```

### Outbound (Nobla → Teams)

```
ChannelResponse → TeamsAdapter.send()
  → format_response() → Adaptive Card JSON
  → POST to conversation service URL with Bearer token (auto-refreshed)
  → Attachments: inline base64 for ≤256KB, link card for larger with URL
```

### Token Lifecycle

```
OAuth2 client_credentials → https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token
  → scope: https://api.botframework.com/.default
  → Cache token in memory, refresh ~5 min before expiry
  → Used for ALL outbound API calls
```

### Proactive Messaging

Store `ConversationReference` (service_url, conversation_id, tenant_id) in `TeamsHandlers._conversation_refs` dict keyed by `channel_user_id`. Captured on every inbound activity. Reused by `send_notification()`.

## 3. File Structure

### 3.1 `backend/nobla/channels/teams/__init__.py`

Lazy `__getattr__` import of `TeamsAdapter`, consistent with all other adapters.

### 3.2 `backend/nobla/channels/teams/models.py`

**`TeamsUserContext` dataclass** (slots=True):
- `user_id: str` — Azure AD user ID (from Activity.from.id)
- `display_name: str` — User display name (from Activity.from.name)
- `tenant_id: str` — Azure AD tenant ID
- `conversation_id: str` — Conversation ID
- `service_url: str` — Bot Framework service URL for replies
- `message_id: str` — Activity ID
- `channel_id: str | None` — Teams channel ID (None for DMs)
- `is_dm: bool` — True if personal chat
- `is_bot_mentioned: bool` — True if bot was @mentioned
- `raw_extras: dict[str, Any]` — Catch-all

Properties: `user_id_str`, `channel_id_str`.

**Constants:**
- `CHANNEL_NAME = "teams"`
- `MAX_CARD_SIZE_BYTES = 28_672` (28KB Adaptive Card limit)
- `MAX_CARD_ACTIONS = 5`
- `MAX_TEXT_BLOCK_LENGTH = 10_000`
- `MAX_ATTACHMENT_INLINE_BYTES = 262_144` (256KB)
- `MAX_FILE_SIZE_BYTES = 104_857_600` (100MB)
- `BOT_FRAMEWORK_TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"`
- `BOT_FRAMEWORK_OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"`
- `BOT_FRAMEWORK_TOKEN_SCOPE = "https://api.botframework.com/.default"`
- `MIME_TO_MEDIA_TYPE: dict[str, str]` — Same mapping pattern as Slack
- `SUPPORTED_ACTIVITY_TYPES = frozenset({"message", "invoke", "conversationUpdate", "messageReaction"})`
- `IGNORED_ACTIVITY_TYPES = frozenset({"typing", "endOfConversation", "event", "installationUpdate"})`

### 3.3 `backend/nobla/channels/teams/formatter.py`

**`format_response(response: ChannelResponse) -> dict[str, Any]`**

Returns a Teams Activity-compatible dict with Adaptive Card attachment.

Markdown → Adaptive Card element mapping:

| Markdown | Adaptive Card Element |
|----------|----------------------|
| `# heading` | `TextBlock` — size "Large", weight "Bolder" |
| `## heading` | `TextBlock` — size "Medium", weight "Bolder" |
| `### heading` | `TextBlock` — size "Default", weight "Bolder" |
| ` ```code``` ` | `TextBlock` — fontType "Monospace", wrap true |
| `---` | `ColumnSet` with separator (no native divider in Adaptive Cards) |
| `> quote` | `Container` with accent style, `TextBlock` subtle color |
| plain text | `TextBlock` — wrap true (supports Teams markdown: bold, italic, links) |
| `InlineAction` buttons | `Action.Submit` — style "positive"/"destructive"/"default", data contains action_id |

**`split_message(text: str, limit: int) -> list[str]`** — Same split logic as Slack (newline > space > hard-cut).

**`markdown_to_card_body(text: str) -> list[dict]`** — Converts markdown into Adaptive Card body elements.

**`build_card_actions(actions: list[InlineAction]) -> list[dict]`** — Converts InlineActions to Action.Submit list (capped at MAX_CARD_ACTIONS).

**Card envelope structure:**
```json
{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "type": "AdaptiveCard",
      "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
      "version": "1.4",
      "body": [],
      "actions": []
    }
  }]
}
```

### 3.4 `backend/nobla/channels/teams/media.py`

**`download_attachment(attachment: dict, bot_token: str, client: httpx.AsyncClient, max_size_bytes: int) -> Attachment | None`**
- Extract URL from `contentUrl` or `content.downloadUrl`
- GET with Bearer token auth (for contentUrl) or direct (for downloadUrl)
- Size check via Content-Length header before downloading body
- Map contentType → AttachmentType via MIME dict

**`send_attachment(service_url: str, conversation_id: str, attachment: Attachment, bot_token: str, client: httpx.AsyncClient) -> bool`**
- ≤256KB: Inline as base64 data URI in Activity attachments array
- >256KB with URL: Send as hero card with download link
- >256KB without URL: Log warning, return False

**`detect_attachment_type(mime_type: str) -> AttachmentType`** — MIME → AttachmentType mapping.

### 3.5 `backend/nobla/channels/teams/handlers.py`

**`TeamsHandlers` class:**

```python
def __init__(self, linking_service, event_bus, app_id, max_file_size_mb=100):
    self._linking = linking_service
    self._event_bus = event_bus
    self._app_id = app_id
    self._max_file_size_mb = max_file_size_mb
    self._send_fn = None
    self._conversation_refs = {}  # channel_user_id → ConversationReference dict
```

**Public methods:**
- `set_send_fn(fn)` — Register adapter's raw send function
- `handle_activity(activity: dict)` — Main dispatch by activity type

**Activity dispatch:**

| Activity Type | Handler | Behavior |
|---------------|---------|----------|
| `message` | `_handle_message()` | Extract TeamsUserContext, store conversation ref, apply channel policy (DM=always, channel=mention-only), check keyword commands, resolve linking, emit `channel.message.in` |
| `invoke` | `_handle_invoke()` | Action.Submit button callbacks → parse action_id from data, emit `channel.callback` |
| `conversationUpdate` | `_handle_conversation_update()` | Bot added → send welcome. Members added/removed → log. |
| `messageReaction` | `_handle_reaction()` | Emit `channel.reaction` event (low priority). |

**Keyword commands** (same 4 as all adapters):
- `!start` → Create pairing code, reply with instructions
- `!link <code>` → Link Teams user to Nobla account
- `!unlink` → Remove link
- `!status` → Show link status + adapter health

**Mention detection:**
- Check Activity `entities` array for `type: "mention"` with `mentioned.id` matching `app_id`
- Strip `<at>BotName</at>` XML tags from message text before processing

**Event bus emissions:**
- `channel.message.in` — Inbound message (after linking resolution)
- `channel.user.linked` / `channel.user.unlinked` — Linking state changes
- `channel.callback` — Button press action

**Conversation reference capture:**
On every inbound activity, extract and cache `{service_url, conversation_id, tenant_id, channel_id}` keyed by `channel_user_id`. Used by `send_notification()` for proactive messaging.

### 3.6 `backend/nobla/channels/teams/adapter.py`

**`TeamsAdapter(BaseChannelAdapter)` — 7 ABC methods:**

| Method | Implementation |
|--------|---------------|
| `name` | `"teams"` |
| `start()` | Init httpx client, TokenManager, JWKS cache (background fetch), wire handlers via `set_send_fn()` |
| `stop()` | Close httpx client, cancel background tasks, clear caches |
| `send(channel_user_id, response)` | Format → Adaptive Card, send attachments, POST to service_url with Bearer token |
| `send_notification(channel_user_id, text)` | Look up conversation ref, POST plain text via proactive message |
| `parse_callback(raw_callback)` | Extract action_id from invoke Activity data |
| `health_check()` | Verify token is valid + JWKS cache is populated |

**`TokenManager` (inner helper):**
- `get_token() -> str` — Return cached token or refresh
- `_refresh() -> str` — POST client_credentials to Microsoft token endpoint
- Cache token in memory, refresh when within `refresh_margin` seconds of expiry
- Thread-safe: use `asyncio.Lock` to prevent concurrent refresh storms

**JWT Validation:**
- Fetch OpenID metadata from `BOT_FRAMEWORK_OPENID_URL`
- Extract `jwks_uri`, fetch JWKS, cache keys (~24h TTL)
- On inbound request: decode JWT, match `kid` against cached keys, verify RS256 signature
- Validate: `iss` starts with `https://api.botframework.com`, `aud` == `app_id`, `exp` not past
- Multi-tenant: accept any valid `tid` claim
- **Security-first:** If JWKS unavailable, reject ALL requests (return 503). Background task retries JWKS fetch with exponential backoff.

**Rate limit handling:**
- On HTTP 429 from Teams API: read `Retry-After` header, delay before retry
- Simple backoff (not a full queue like Slack — Teams rate limits are less aggressive)

**`handle_webhook(body: bytes, auth_header: str) -> dict`** — Gateway entry point. Validates JWT, parses Activity, dispatches to handlers.

## 4. Configuration

### TeamsSettings (in `backend/nobla/config/settings.py`, after SignalSettings)

```python
class TeamsSettings(BaseModel):
    enabled: bool = False
    app_id: str = ""          # Azure Bot registration App ID
    app_password: str = ""    # Azure Bot registration password
    tenant_id: str = ""       # Empty = multi-tenant (default)
    webhook_path: str = "/webhook/teams"
    group_activation: str = "mention"  # "mention" or "all"
    max_file_size_mb: int = 100
    token_refresh_margin_seconds: int = 300  # Refresh 5 min before expiry

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.enabled and not self.app_id:
            raise ValueError("app_id is required when Teams is enabled")
        if self.enabled and not self.app_password:
            raise ValueError("app_password is required when Teams is enabled")
        return self
```

Add `teams: TeamsSettings = Field(default_factory=TeamsSettings)` to the main `Settings` class.

### Lifespan Wiring (in `backend/nobla/gateway/lifespan.py`, `_init_channels()`)

Add Teams init block after Signal, following the same try/except pattern:

```python
if settings.teams.enabled and settings.teams.app_id:
    try:
        from nobla.channels.teams.handlers import TeamsHandlers
        from nobla.channels.teams.adapter import TeamsAdapter

        teams_handlers = TeamsHandlers(
            linking_service=linking_service,
            event_bus=event_bus,
            app_id=settings.teams.app_id,
        )
        teams_adapter = TeamsAdapter(
            settings=settings.teams,
            handlers=teams_handlers,
        )
        channel_manager.register(teams_adapter)
        await teams_adapter.start()
        logger.info("teams_adapter_started")
    except Exception:
        logger.exception("teams_adapter_start_failed")
else:
    logger.info("teams_adapter_disabled")
```

## 5. Dependencies

- `httpx` — HTTP client (already in use)
- `PyJWT` — JWT decoding and RS256 verification (new dependency)
- `cryptography` — Required by PyJWT for RS256 (likely already transitive)

No Azure SDK required.

## 6. Testing Strategy (~100 tests)

**Test file:** `backend/tests/test_teams_adapter.py`

| Category | Count | Coverage |
|----------|-------|----------|
| Models & Constants | ~8 | TeamsUserContext creation, properties, defaults, MIME mapping, constant values |
| Formatter | ~20 | Each markdown→card element type (h1/h2/h3, code, dividers, quotes, plain text), action buttons (styles, max cap), split logic, empty input, mixed content, card envelope |
| Media | ~12 | Download with Bearer auth, download direct URL, size rejection, inline base64 ≤256KB, link card >256KB with URL, skip >256KB without URL, MIME detection, errors |
| JWT Validation | ~15 | Valid token, expired rejection, wrong audience, wrong issuer, invalid signature, JWKS cache hit, JWKS refresh on unknown kid, JWKS fetch failure → 503, missing auth header, malformed token |
| Token Manager | ~8 | Initial fetch, cache hit, auto-refresh near expiry, refresh on expired, endpoint error, concurrent refresh lock |
| Handlers | ~25 | Message routing, DM always responds, channel mention-only, mention stripping, each keyword command (4), linking flow, already-linked passthrough, conversation ref capture, invoke → callback, conversationUpdate → welcome, event bus emission per event, set_send_fn wiring |
| Adapter Lifecycle | ~12 | start() init, stop() cleanup, send() text+attachments, send_notification() via conv ref, parse_callback(), health_check() ok/fail, handle_webhook() e2e, double-start guard, send-before-start guard |
| **Total** | **~100** | |

All tests mock external calls (httpx, JWT, event bus). No real Microsoft API calls.

## 7. Design Constraints Compliance

- **750-line limit:** adapter.py will be the largest (~400-500 lines with TokenManager + JWT). All others well under limit.
- **BaseChannelAdapter ABC:** All 7 methods implemented.
- **Event bus:** All cross-component communication via event bus.
- **Security-first:** JWT validation mandatory (503 when JWKS unavailable), tokens encrypted in settings, no validation bypass.
- **Graceful degradation:** Adapter start failure doesn't block other adapters (try/except in lifespan).
- **httpx:** All HTTP calls via httpx (consistent with existing adapters).
- **Handler wiring:** `set_send_fn()` pattern.
- **Keyword commands:** `!start`, `!link`, `!unlink`, `!status`.
- **Rate limiting:** Retry-After backoff for 429 responses.
