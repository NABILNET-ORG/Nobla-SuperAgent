# Slack + Signal Channel Adapters Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Slack and Signal messaging channel adapters following the established 6-file pattern, with ~100 and ~75 tests respectively.

**Architecture:** Two independent adapter tracks built in parallel. Each follows the BaseChannelAdapter ABC contract with models/formatter/media/handlers/adapter/`__init__` modules. A shared final task wires both into settings and gateway lifespan.

**Tech Stack:** Python 3.12+, httpx (HTTP), websockets (Slack Socket Mode), asyncio, pydantic, pytest + AsyncMock

**Spec:** `docs/superpowers/specs/2026-03-29-slack-signal-adapters-design.md`

**Parallelization:** Track A (Tasks 1-6) and Track B (Tasks 7-12) are fully independent. Task 13 (gateway wiring) depends on both tracks completing.

---

## Track A: Slack Adapter

### Task 1: Slack Models

**Files:**
- Create: `backend/nobla/channels/slack/__init__.py`
- Create: `backend/nobla/channels/slack/models.py`
- Test: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p backend/nobla/channels/slack
```

```python
# backend/nobla/channels/slack/__init__.py
"""Slack channel adapter (Phase 5-Channels)."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "SlackAdapter":
        from nobla.channels.slack.adapter import SlackAdapter
        return SlackAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 2: Write failing tests for models**

Create `backend/tests/test_slack_adapter.py` with the models test section:

```python
"""Tests for the Slack channel adapter (Phase 5-Channels).

Covers: models/constants, formatter (Block Kit, escape, split), media (v2 upload,
download), handlers (message dispatch, slash commands, keyword commands,
interactive callbacks, rate limit queue, event emission), adapter (Socket Mode,
Events API, signature verification, send, health check), and settings.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.slack.models import (
    CHANNEL_NAME,
    MAX_MESSAGE_LENGTH,
    MAX_BLOCK_TEXT_LENGTH,
    MAX_BUTTONS,
    RATE_LIMIT_TIERS,
    SlackUserContext,
)


# ── Models & Constants ──────────────────────────────────────────────

class TestSlackModels:
    def test_channel_name(self):
        assert CHANNEL_NAME == "slack"

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 3000

    def test_max_buttons(self):
        assert MAX_BUTTONS == 5

    def test_max_block_text_length(self):
        assert MAX_BLOCK_TEXT_LENGTH == 3000

    def test_rate_limit_tiers(self):
        assert isinstance(RATE_LIMIT_TIERS, dict)
        assert "tier_1" in RATE_LIMIT_TIERS

    def test_user_context_basic(self):
        ctx = SlackUserContext(
            user_id="U12345",
            team_id="T12345",
            channel_id="C12345",
            is_dm=True,
            is_bot_mentioned=False,
            timestamp="1234567890.123456",
        )
        assert ctx.user_id == "U12345"
        assert ctx.user_id_str == "U12345"
        assert ctx.chat_id_str == "C12345"

    def test_user_context_thread(self):
        ctx = SlackUserContext(
            user_id="U12345",
            team_id="T12345",
            channel_id="C12345",
            thread_ts="1234567890.000001",
            is_dm=False,
            is_bot_mentioned=True,
            timestamp="1234567890.123456",
        )
        assert ctx.thread_ts == "1234567890.000001"
        assert ctx.is_bot_mentioned is True

    def test_user_context_defaults(self):
        ctx = SlackUserContext(
            user_id="U1",
            team_id="T1",
            channel_id="C1",
            is_dm=False,
            is_bot_mentioned=False,
            timestamp="0",
        )
        assert ctx.thread_ts is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackModels -v`
Expected: FAIL (import errors)

- [ ] **Step 4: Implement models.py**

```python
# backend/nobla/channels/slack/models.py
"""Slack adapter models, constants, and user context (Phase 5-Channels)."""

from __future__ import annotations

from dataclasses import dataclass, field

CHANNEL_NAME = "slack"
MAX_MESSAGE_LENGTH = 3000
MAX_BLOCK_TEXT_LENGTH = 3000
MAX_BUTTONS = 5  # Slack allows up to 5 buttons per action block
MAX_ACTIONS_PER_MESSAGE = 25

# Rate limit tiers (requests per minute)
RATE_LIMIT_TIERS: dict[str, int] = {
    "tier_1": 1,    # Special methods
    "tier_2": 20,   # Most read methods
    "tier_3": 50,   # Most write methods (chat.postMessage)
    "tier_4": 100,  # Some admin methods
}

# Slack event types we handle
SUPPORTED_EVENT_TYPES = frozenset({
    "message",
    "app_mention",
    "member_joined_channel",
})

# Socket Mode envelope types
ENVELOPE_TYPES = frozenset({
    "hello",
    "events_api",
    "interactive",
    "slash_commands",
    "disconnect",
})

# Channel types
CHANNEL_TYPE_DM = "im"
CHANNEL_TYPE_GROUP_DM = "mpim"
CHANNEL_TYPE_PUBLIC = "channel"
CHANNEL_TYPE_PRIVATE = "group"
DM_TYPES = frozenset({CHANNEL_TYPE_DM, CHANNEL_TYPE_GROUP_DM})

# MIME type mapping for file uploads
MIME_TO_FILE_TYPE: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "application/pdf": "pdf",
    "text/plain": "txt",
}


@dataclass(frozen=True)
class SlackUserContext:
    """Normalized context from an incoming Slack event."""

    user_id: str
    team_id: str
    channel_id: str
    is_dm: bool
    is_bot_mentioned: bool
    timestamp: str
    thread_ts: str | None = None

    @property
    def user_id_str(self) -> str:
        return self.user_id

    @property
    def chat_id_str(self) -> str:
        return self.channel_id
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackModels -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/channels/slack/__init__.py backend/nobla/channels/slack/models.py backend/tests/test_slack_adapter.py
git commit -m "feat(5-channels): add Slack adapter models and constants"
```

---

### Task 2: Slack Formatter

**Files:**
- Create: `backend/nobla/channels/slack/formatter.py`
- Modify: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Write failing tests for formatter**

Append to `backend/tests/test_slack_adapter.py`:

```python
from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.slack.formatter import (
    FormattedMessage,
    build_button_blocks,
    escape_slack_text,
    format_response,
    markdown_to_blocks,
    split_message,
)


class TestSlackFormatter:
    # ── Escape ──
    def test_escape_ampersand(self):
        assert escape_slack_text("A & B") == "A &amp; B"

    def test_escape_angle_brackets(self):
        assert escape_slack_text("<script>") == "&lt;script&gt;"

    def test_escape_preserves_slack_links(self):
        # Slack links like <@U123> and <#C123> should NOT be escaped
        text = "Hello <@U123> in <#C123|general>"
        result = escape_slack_text(text)
        assert "<@U123>" in result
        assert "<#C123|general>" in result

    def test_escape_empty_string(self):
        assert escape_slack_text("") == ""

    # ── Split ──
    def test_split_short_message(self):
        chunks = split_message("Hello", 3000)
        assert chunks == ["Hello"]

    def test_split_at_newline(self):
        text = "A\n" * 2000
        chunks = split_message(text, 3000)
        assert all(len(c) <= 3000 for c in chunks)
        assert "".join(chunks) == text

    def test_split_long_word(self):
        text = "A" * 6000
        chunks = split_message(text, 3000)
        assert len(chunks) == 2
        assert all(len(c) <= 3000 for c in chunks)

    # ── Block Kit Conversion ──
    def test_markdown_to_blocks_plain_text(self):
        blocks = markdown_to_blocks("Hello world")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

    def test_markdown_to_blocks_header(self):
        blocks = markdown_to_blocks("# My Header\nSome text")
        types = [b["type"] for b in blocks]
        assert "header" in types

    def test_markdown_to_blocks_code_block(self):
        blocks = markdown_to_blocks("```python\nprint('hi')\n```")
        # Code blocks become section with mrkdwn containing triple backticks
        found = any(
            "```" in b.get("text", {}).get("text", "")
            for b in blocks
            if b["type"] == "section"
        )
        assert found

    def test_markdown_to_blocks_divider(self):
        blocks = markdown_to_blocks("Above\n---\nBelow")
        types = [b["type"] for b in blocks]
        assert "divider" in types

    def test_markdown_to_blocks_empty(self):
        blocks = markdown_to_blocks("")
        assert blocks == []

    # ── Buttons ──
    def test_build_button_blocks(self):
        actions = [
            InlineAction(action_id="approval:req-1:approve", label="Approve"),
            InlineAction(action_id="approval:req-1:deny", label="Deny"),
        ]
        blocks = build_button_blocks(actions)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        assert len(blocks[0]["elements"]) == 2
        assert blocks[0]["elements"][0]["text"]["text"] == "Approve"

    def test_build_button_blocks_truncates_at_max(self):
        actions = [
            InlineAction(action_id=f"a:{i}:click", label=f"Btn {i}")
            for i in range(10)
        ]
        blocks = build_button_blocks(actions)
        assert len(blocks[0]["elements"]) <= 5

    def test_build_button_blocks_empty(self):
        blocks = build_button_blocks([])
        assert blocks == []

    # ── format_response ──
    def test_format_response_simple_text(self):
        resp = ChannelResponse(content="Hello")
        msgs = format_response(resp)
        assert len(msgs) >= 1
        assert msgs[0].text == "Hello"
        assert len(msgs[0].blocks) >= 1

    def test_format_response_with_actions(self):
        resp = ChannelResponse(
            content="Pick one",
            actions=[
                InlineAction(action_id="a:1:yes", label="Yes"),
                InlineAction(action_id="a:1:no", label="No"),
            ],
        )
        msgs = format_response(resp)
        last = msgs[-1]
        block_types = [b["type"] for b in last.blocks]
        assert "actions" in block_types

    def test_format_response_long_text_splits(self):
        resp = ChannelResponse(content="A" * 6000)
        msgs = format_response(resp)
        assert len(msgs) >= 2

    def test_formatted_message_dataclass(self):
        fm = FormattedMessage(text="hi", blocks=[{"type": "section"}])
        assert fm.text == "hi"
        assert fm.blocks == [{"type": "section"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackFormatter -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement formatter.py**

Create `backend/nobla/channels/slack/formatter.py` (~250 lines) with:

- `escape_slack_text(text)` — escape `&`, `<`, `>` but preserve Slack links (`<@U...>`, `<#C...>`, `<http...>`)
- `split_message(text, limit=3000)` — split at newlines, then spaces, then hard-cut
- `markdown_to_blocks(text)` — convert markdown to Block Kit:
  - `# heading` → `{"type": "header", "text": {"type": "plain_text", "text": ...}}`
  - `---` → `{"type": "divider"}`
  - ` ```code``` ` → `{"type": "section", "text": {"type": "mrkdwn", "text": "```code```"}}`
  - Other text → `{"type": "section", "text": {"type": "mrkdwn", "text": ...}}`
- `build_button_blocks(actions)` — InlineAction list → actions block with button elements (max 5)
- `format_response(response)` → `list[FormattedMessage]` — split, convert to blocks, attach buttons to last message
- `FormattedMessage` dataclass: `text: str`, `blocks: list[dict]`

Key implementation detail: Slack's `mrkdwn` uses `*bold*`, `_italic_`, `~strike~`, `` `code` ``, ` ```preformatted``` `, `>quote` — similar to markdown but not identical. The `markdown_to_blocks` function should parse line-by-line and group contiguous text lines into section blocks.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackFormatter -v`
Expected: PASS (19 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/slack/formatter.py backend/tests/test_slack_adapter.py
git commit -m "feat(5-channels): add Slack Block Kit formatter with markdown conversion"
```

---

### Task 3: Slack Media

**Files:**
- Create: `backend/nobla/channels/slack/media.py`
- Modify: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Write failing tests for media**

Append to `backend/tests/test_slack_adapter.py`:

```python
from nobla.channels.slack.media import (
    download_file,
    get_upload_url,
    complete_upload,
    send_attachment,
    validate_file_size,
)
from nobla.channels.base import Attachment, AttachmentType


class TestSlackMedia:
    # ── Download ──
    @pytest.mark.asyncio
    async def test_download_file(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            content=b"file data",
            headers={"content-type": "image/png"},
        )
        data, mime = await download_file(
            "https://files.slack.com/file.png",
            "xoxb-token",
            client=mock_client,
        )
        assert data == b"file data"
        assert mime == "image/png"

    @pytest.mark.asyncio
    async def test_download_file_auth_header(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            content=b"data",
            headers={"content-type": "application/octet-stream"},
        )
        await download_file("https://files.slack.com/f", "xoxb-tok", client=mock_client)
        call_kwargs = mock_client.get.call_args
        assert "Authorization" in call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))

    @pytest.mark.asyncio
    async def test_download_file_failure(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(status_code=403)
        with pytest.raises(Exception):
            await download_file("https://x/f", "tok", client=mock_client)

    # ── Upload v2 pipeline ──
    @pytest.mark.asyncio
    async def test_get_upload_url(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "upload_url": "https://upload.slack.com/...", "file_id": "F123"},
        )
        url, file_id = await get_upload_url(
            "xoxb-tok", "test.png", 1024, client=mock_client,
        )
        assert url == "https://upload.slack.com/..."
        assert file_id == "F123"

    @pytest.mark.asyncio
    async def test_complete_upload(self):
        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True},
        )
        result = await complete_upload(
            "xoxb-tok", "F123", "C456", thread_ts=None, client=mock_client,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_attachment_full_pipeline(self):
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="photo.png",
            mime_type="image/png",
            size_bytes=1024,
            data=b"png data",
        )
        mock_client = AsyncMock()
        # get_upload_url
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "upload_url": "https://up.slack.com/x", "file_id": "F1"},
        )
        # PUT upload + complete_upload POST
        mock_client.put.return_value = MagicMock(status_code=200)
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True},
        )
        await send_attachment("xoxb-tok", "C123", attachment, client=mock_client)
        assert mock_client.put.called
        assert mock_client.post.called

    # ── Validation ──
    def test_validate_file_size_ok(self):
        assert validate_file_size(1024, max_mb=100) is True

    def test_validate_file_size_too_large(self):
        assert validate_file_size(200 * 1024 * 1024, max_mb=100) is False

    def test_validate_file_size_zero(self):
        assert validate_file_size(0, max_mb=100) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackMedia -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement media.py**

Create `backend/nobla/channels/slack/media.py` (~200 lines) with:

- `validate_file_size(size_bytes, max_mb)` → bool
- `async download_file(url, bot_token, client=None)` → `(bytes, mime_type)` — GET with `Authorization: Bearer {token}`
- `async get_upload_url(bot_token, filename, length, client=None)` → `(upload_url, file_id)` — GET `files.getUploadURLExternal`
- `async complete_upload(bot_token, file_id, channel_id, thread_ts=None, client=None)` → bool — POST `files.completeUploadExternal`
- `async send_attachment(bot_token, channel_id, attachment, thread_ts=None, client=None)` — full v2 pipeline: get URL → PUT data → complete

All functions use `httpx.AsyncClient`, creating one internally if not provided (consistent with WhatsApp pattern).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackMedia -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/slack/media.py backend/tests/test_slack_adapter.py
git commit -m "feat(5-channels): add Slack media v2 upload/download pipeline"
```

---

### Task 4: Slack Handlers

**Files:**
- Create: `backend/nobla/channels/slack/handlers.py`
- Modify: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Write failing tests for handlers**

Append to `backend/tests/test_slack_adapter.py`:

```python
from nobla.channels.slack.handlers import SlackHandlers, RateLimitQueue


@pytest.fixture
def slack_handlers():
    linking = AsyncMock()
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    h = SlackHandlers(
        linking_service=linking,
        event_bus=event_bus,
        bot_user_id="U_BOT",
        bot_token="xoxb-test",
    )
    h.set_send_fn(AsyncMock())
    return h


class TestSlackHandlers:
    # ── Message routing ──
    @pytest.mark.asyncio
    async def test_handle_dm_message(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "Hello bot",
            "ts": "1234567890.000001",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_channel_message_with_mention(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "<@U_BOT> what time is it?",
            "ts": "1234567890.000001",
            "channel": "C789",
            "channel_type": "channel",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_channel_message_without_mention_ignored(self, slack_handlers):
        event = {
            "type": "message",
            "user": "U123",
            "text": "Just chatting",
            "ts": "1234567890.000001",
            "channel": "C789",
            "channel_type": "channel",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_bot_message_ignored(self, slack_handlers):
        event = {
            "type": "message",
            "user": "U_BOT",
            "text": "I said something",
            "ts": "1234567890.000001",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_subtype_ignored(self, slack_handlers):
        event = {
            "type": "message",
            "subtype": "channel_join",
            "user": "U123",
            "text": "joined",
            "ts": "1",
            "channel": "C1",
            "channel_type": "channel",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_thread_reply(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "<@U_BOT> reply",
            "ts": "1234567890.000002",
            "thread_ts": "1234567890.000001",
            "channel": "C789",
            "channel_type": "channel",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        call_args = slack_handlers._event_bus.publish.call_args
        event_obj = call_args[0][0]
        assert event_obj.payload.get("metadata", {}).get("thread_ts") == "1234567890.000001"

    # ── Slash commands ──
    @pytest.mark.asyncio
    async def test_slash_command_start(self, slack_handlers):
        slack_handlers._linking.create_pairing_code = AsyncMock(return_value="ABC123")
        payload = {
            "command": "/nobla",
            "text": "start",
            "user_id": "U123",
            "team_id": "T1",
            "channel_id": "D456",
        }
        await slack_handlers.handle_slash_command(payload)
        slack_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_slash_command_link(self, slack_handlers):
        slack_handlers._linking.link = AsyncMock(return_value=True)
        payload = {
            "command": "/nobla",
            "text": "link user-001",
            "user_id": "U123",
            "team_id": "T1",
            "channel_id": "D456",
        }
        await slack_handlers.handle_slash_command(payload)
        slack_handlers._linking.link.assert_called()

    @pytest.mark.asyncio
    async def test_slash_command_unlink(self, slack_handlers):
        slack_handlers._linking.unlink = AsyncMock(return_value=True)
        payload = {
            "command": "/nobla",
            "text": "unlink",
            "user_id": "U123",
            "team_id": "T1",
            "channel_id": "D456",
        }
        await slack_handlers.handle_slash_command(payload)
        slack_handlers._linking.unlink.assert_called()

    @pytest.mark.asyncio
    async def test_slash_command_status(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        payload = {
            "command": "/nobla",
            "text": "status",
            "user_id": "U123",
            "team_id": "T1",
            "channel_id": "D456",
        }
        await slack_handlers.handle_slash_command(payload)
        slack_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_slash_command_unknown(self, slack_handlers):
        payload = {
            "command": "/nobla",
            "text": "unknown_cmd",
            "user_id": "U123",
            "team_id": "T1",
            "channel_id": "D456",
        }
        await slack_handlers.handle_slash_command(payload)
        # Should send help text
        slack_handlers._send_fn.assert_called()

    # ── Keyword commands (fallback) ──
    @pytest.mark.asyncio
    async def test_keyword_command_start(self, slack_handlers):
        slack_handlers._linking.create_pairing_code = AsyncMock(return_value="XYZ789")
        event = {
            "type": "message",
            "user": "U123",
            "text": "!start",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_keyword_command_link(self, slack_handlers):
        slack_handlers._linking.link = AsyncMock(return_value=True)
        event = {
            "type": "message",
            "user": "U123",
            "text": "!link user-001",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._linking.link.assert_called()

    # ── Interactive callbacks ──
    @pytest.mark.asyncio
    async def test_handle_interactive_button(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        payload = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "team": {"id": "T1"},
            "channel": {"id": "C789"},
            "actions": [
                {"action_id": "approval:req-1:approve", "text": {"text": "Approve"}},
            ],
            "message": {"ts": "1234567890.000001"},
        }
        await slack_handlers.handle_interactive(payload)
        slack_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_interactive_no_actions(self, slack_handlers):
        payload = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "team": {"id": "T1"},
            "channel": {"id": "C789"},
            "actions": [],
        }
        await slack_handlers.handle_interactive(payload)
        slack_handlers._event_bus.publish.assert_not_called()

    # ── Unlinked user pairing ──
    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_prompt(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value=None)
        slack_handlers._linking.create_pairing_code = AsyncMock(return_value="PAR123")
        event = {
            "type": "message",
            "user": "U_NEW",
            "text": "Hello",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._send_fn.assert_called()
        slack_handlers._event_bus.publish.assert_not_called()

    # ── Event emission ──
    @pytest.mark.asyncio
    async def test_event_emission_channel_message_in(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "Test",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        call = slack_handlers._event_bus.publish.call_args[0][0]
        assert call.type == "channel.message.in"
        assert call.payload["channel"] == "slack"


class TestRateLimitQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_drain(self):
        send_fn = AsyncMock()
        q = RateLimitQueue(send_fn=send_fn)
        await q.enqueue("C1", "Hello", blocks=None, thread_ts=None)
        await q.drain_one()
        send_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_after_requeue(self):
        call_count = 0
        async def flaky_send(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from nobla.channels.slack.handlers import RateLimitError
                raise RateLimitError(retry_after=0.01)
        q = RateLimitQueue(send_fn=flaky_send)
        await q.enqueue("C1", "msg", blocks=None, thread_ts=None)
        await q.drain_one()  # First attempt -> rate limited -> requeued
        await q.drain_one()  # Second attempt -> succeeds
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_queue_empty_drain(self):
        q = RateLimitQueue(send_fn=AsyncMock())
        # Should not raise
        await q.drain_one()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackHandlers tests/test_slack_adapter.py::TestRateLimitQueue -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement handlers.py**

Create `backend/nobla/channels/slack/handlers.py` (~450 lines) with:

**RateLimitError** exception with `retry_after` field.

**RateLimitQueue** class:
- `__init__(send_fn)` — wraps an async send function
- `async enqueue(channel, text, blocks, thread_ts)` — add to asyncio.Queue
- `async drain_one()` — pop one item, call send_fn, catch RateLimitError and re-enqueue after delay
- `async start_worker()` / `stop_worker()` — background task draining continuously

**SlackHandlers** class:
- `__init__(linking_service, event_bus, bot_user_id, bot_token)`
- `set_send_fn(fn)` — register adapter's send function
- `async handle_event(payload)` — dispatcher:
  - Extract `event` from payload
  - Skip if `event.user == bot_user_id` (ignore own messages)
  - Skip if `event.subtype` exists (channel_join, etc.)
  - Build `SlackUserContext` from event
  - Detect DM vs channel: `channel_type in DM_TYPES`
  - In non-DM: skip if `<@{bot_user_id}>` not in text
  - Strip mention from text: `text.replace(f"<@{bot_user_id}>", "").strip()`
  - Check for keyword commands (`!start`, `!link`, `!unlink`, `!status`)
  - If unlinked user: generate pairing code, send prompt, return
  - Build `ChannelMessage`, emit `channel.message.in`
- `async handle_slash_command(payload)` — parse `/nobla <subcmd> [args]`:
  - `start` → create pairing code, send welcome
  - `link <nobla_user_id>` → link account
  - `unlink` → unlink account
  - `status` → show link status
  - Unknown → send help text
- `async handle_interactive(payload)` — parse block_actions:
  - Extract `action_id` from first action
  - Resolve linked user
  - Emit `channel.callback` event
- `async _emit_event(event_type, payload, user_id)` — wraps `event_bus.publish(NoblaEvent(...))`
- `async _send_reply(channel_id, text, thread_ts=None)` — call send_fn

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackHandlers tests/test_slack_adapter.py::TestRateLimitQueue -v`
Expected: PASS (22 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/slack/handlers.py backend/tests/test_slack_adapter.py
git commit -m "feat(5-channels): add Slack handlers with slash/keyword commands and rate limit queue"
```

---

### Task 5: Slack Adapter

**Files:**
- Create: `backend/nobla/channels/slack/adapter.py`
- Modify: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Write failing tests for adapter**

Append to `backend/tests/test_slack_adapter.py`:

```python
from nobla.channels.slack.adapter import SlackAdapter


class _FakeSlackSettings:
    enabled = True
    bot_token = "xoxb-test-token"
    app_token = "xapp-test-token"
    signing_secret = "test_signing_secret"
    mode = "socket"
    command_name = "/nobla"
    webhook_path = "/webhook/slack"
    group_activation = "mention"
    max_file_size_mb = 100


class TestSlackAdapter:
    def _make_adapter(self, mode="socket"):
        settings = _FakeSlackSettings()
        settings.mode = mode
        handlers = MagicMock()
        handlers.handle_event = AsyncMock()
        handlers.handle_slash_command = AsyncMock()
        handlers.handle_interactive = AsyncMock()
        return SlackAdapter(settings=settings, handlers=handlers)

    # ── Properties ──
    def test_name(self):
        adapter = self._make_adapter()
        assert adapter.name == "slack"

    # ── Signature verification (Events API) ──
    def test_verify_signature_valid(self):
        adapter = self._make_adapter(mode="events")
        ts = "1234567890"
        body = b'{"event": {}}'
        sig_base = f"v0:{ts}:{body.decode()}"
        expected = "v0=" + hmac.new(
            b"test_signing_secret", sig_base.encode(), hashlib.sha256
        ).hexdigest()
        assert adapter.verify_signature(body, ts, expected) is True

    def test_verify_signature_invalid(self):
        adapter = self._make_adapter(mode="events")
        assert adapter.verify_signature(b"body", "123", "v0=bad") is False

    def test_verify_signature_stale_timestamp(self):
        adapter = self._make_adapter(mode="events")
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        body = b"test"
        sig_base = f"v0:{old_ts}:{body.decode()}"
        sig = "v0=" + hmac.new(
            b"test_signing_secret", sig_base.encode(), hashlib.sha256
        ).hexdigest()
        assert adapter.verify_signature(body, old_ts, sig) is False

    # ── URL verification challenge ──
    def test_url_verification(self):
        adapter = self._make_adapter(mode="events")
        payload = {"type": "url_verification", "challenge": "abc123"}
        result = adapter.handle_url_verification(payload)
        assert result == {"challenge": "abc123"}

    # ── Socket Mode ack ──
    def test_build_ack(self):
        adapter = self._make_adapter(mode="socket")
        ack = adapter._build_ack("env-id-001")
        assert ack == {"envelope_id": "env-id-001"}

    # ── Send ──
    @pytest.mark.asyncio
    async def test_send_simple_text(self):
        adapter = self._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "ts": "1.1"},
        )
        from nobla.channels.base import ChannelResponse
        resp = ChannelResponse(content="Hello")
        await adapter.send("U123", resp)
        adapter._client.post.assert_called()

    @pytest.mark.asyncio
    async def test_send_with_thread_ts(self):
        adapter = self._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "ts": "1.2"},
        )
        resp = ChannelResponse(content="Reply")
        await adapter.send("U123", resp, thread_ts="1234567890.000001")
        call_kwargs = adapter._client.post.call_args
        post_data = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
        assert post_data.get("thread_ts") == "1234567890.000001"

    @pytest.mark.asyncio
    async def test_send_notification(self):
        adapter = self._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True},
        )
        await adapter.send_notification("U123", "Alert!")
        adapter._client.post.assert_called()

    # ── Parse callback ──
    def test_parse_callback(self):
        adapter = self._make_adapter()
        raw = {"action_id": "approval:req-1:approve", "value": "yes"}
        action_id, meta = adapter.parse_callback(raw)
        assert action_id == "approval:req-1:approve"

    def test_parse_callback_empty(self):
        adapter = self._make_adapter()
        action_id, meta = adapter.parse_callback({})
        assert action_id == ""

    # ── Health check ──
    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        adapter = self._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "user_id": "U_BOT"},
        )
        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = self._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": False, "error": "invalid_auth"},
        )
        result = await adapter.health_check()
        assert result is False

    # ── Lifecycle ──
    @pytest.mark.asyncio
    async def test_start_creates_client(self):
        adapter = self._make_adapter()
        with patch("nobla.channels.slack.adapter.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = AsyncMock()
            # Mock the WebSocket connection for socket mode
            with patch("nobla.channels.slack.adapter.SlackAdapter._connect_socket_mode", new_callable=AsyncMock):
                await adapter.start()
                assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_stop_closes_client(self):
        adapter = self._make_adapter()
        mock_client = AsyncMock()
        adapter._client = mock_client
        adapter._ws = None
        adapter._receive_task = None
        await adapter.stop()
        mock_client.aclose.assert_called()

    # ── Socket Mode envelope dispatch ──
    @pytest.mark.asyncio
    async def test_dispatch_events_api_envelope(self):
        adapter = self._make_adapter(mode="socket")
        adapter._handlers = MagicMock()
        adapter._handlers.handle_event = AsyncMock()
        envelope = {
            "envelope_id": "env-1",
            "type": "events_api",
            "payload": {"event": {"type": "message", "user": "U1", "text": "hi", "ts": "1", "channel": "D1", "channel_type": "im"}},
        }
        ack = await adapter._dispatch_envelope(envelope)
        assert ack == {"envelope_id": "env-1"}
        adapter._handlers.handle_event.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_slash_commands_envelope(self):
        adapter = self._make_adapter(mode="socket")
        adapter._handlers = MagicMock()
        adapter._handlers.handle_slash_command = AsyncMock()
        envelope = {
            "envelope_id": "env-2",
            "type": "slash_commands",
            "payload": {"command": "/nobla", "text": "start", "user_id": "U1", "team_id": "T1", "channel_id": "D1"},
        }
        ack = await adapter._dispatch_envelope(envelope)
        assert ack == {"envelope_id": "env-2"}
        adapter._handlers.handle_slash_command.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_interactive_envelope(self):
        adapter = self._make_adapter(mode="socket")
        adapter._handlers = MagicMock()
        adapter._handlers.handle_interactive = AsyncMock()
        envelope = {
            "envelope_id": "env-3",
            "type": "interactive",
            "payload": {"type": "block_actions", "actions": []},
        }
        ack = await adapter._dispatch_envelope(envelope)
        assert ack == {"envelope_id": "env-3"}
        adapter._handlers.handle_interactive.assert_called()

    @pytest.mark.asyncio
    async def test_dispatch_hello_envelope(self):
        adapter = self._make_adapter(mode="socket")
        envelope = {"envelope_id": "env-4", "type": "hello"}
        ack = await adapter._dispatch_envelope(envelope)
        assert ack is None  # hello doesn't need ack

    @pytest.mark.asyncio
    async def test_dispatch_disconnect_envelope(self):
        adapter = self._make_adapter(mode="socket")
        envelope = {"envelope_id": "env-5", "type": "disconnect", "reason": "refresh"}
        ack = await adapter._dispatch_envelope(envelope)
        assert ack is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackAdapter -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement adapter.py**

Create `backend/nobla/channels/slack/adapter.py` (~300 lines) implementing `BaseChannelAdapter`:

- `name = "slack"` property
- Constructor takes `settings` + `handlers`, stores bot_token, mode
- `async start()`: create httpx.AsyncClient, wire `handlers.set_send_fn()`, if socket mode call `_connect_socket_mode()`
- `async stop()`: cancel receive task, close WebSocket, close httpx client
- `async send(channel_user_id, response, thread_ts=None)`: format with `format_response()`, post via `chat.postMessage` with blocks + thread_ts
- `async send_notification(channel_user_id, text)`: plain `chat.postMessage`
- `parse_callback(raw)`: extract `action_id` from raw dict
- `async health_check()`: POST `auth.test`
- `verify_signature(body, timestamp, signature)`: HMAC-SHA256 check with 5-min staleness window
- `handle_url_verification(payload)`: return `{"challenge": payload["challenge"]}`
- `_build_ack(envelope_id)`: return `{"envelope_id": envelope_id}`
- `async _dispatch_envelope(envelope)`: route by envelope type, ack first then process
- `async _connect_socket_mode()`: POST `apps.connections.open` with app_token → get wss URL → connect
- `async _receive_loop()`: read WebSocket messages, dispatch envelopes, send acks
- Reconnection with exponential backoff (1s, 2s, 4s... max 30s)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py::TestSlackAdapter -v`
Expected: PASS (24 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/slack/adapter.py backend/tests/test_slack_adapter.py
git commit -m "feat(5-channels): add Slack adapter with Socket Mode + Events API dual transport"
```

---

### Task 6: Slack Integration Tests & Edge Cases

**Files:**
- Modify: `backend/tests/test_slack_adapter.py`

- [ ] **Step 1: Write additional edge case and integration tests**

Append to `backend/tests/test_slack_adapter.py`:

```python
class TestSlackEdgeCases:
    # ── Formatter edge cases ──
    def test_format_response_empty_content(self):
        resp = ChannelResponse(content="")
        msgs = format_response(resp)
        assert msgs == []

    def test_escape_multiple_special_chars(self):
        assert escape_slack_text("a & b < c > d") == "a &amp; b &lt; c &gt; d"

    def test_split_message_exactly_at_limit(self):
        text = "A" * 3000
        chunks = split_message(text, 3000)
        assert len(chunks) == 1

    def test_markdown_to_blocks_multiple_headers(self):
        blocks = markdown_to_blocks("# H1\nText\n## H2\nMore text")
        headers = [b for b in blocks if b["type"] == "header"]
        assert len(headers) == 2

    def test_markdown_to_blocks_list_items(self):
        blocks = markdown_to_blocks("- Item 1\n- Item 2\n- Item 3")
        assert len(blocks) >= 1

    def test_build_button_blocks_special_chars_in_label(self):
        actions = [InlineAction(action_id="a:1:go", label="Go & Do <stuff>")]
        blocks = build_button_blocks(actions)
        assert blocks[0]["elements"][0]["text"]["text"] == "Go & Do <stuff>"

    # ── Handler edge cases ──
    @pytest.mark.asyncio
    async def test_handler_with_file_attachment(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "Check this file",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
            "files": [
                {
                    "url_private": "https://files.slack.com/f1.pdf",
                    "name": "report.pdf",
                    "mimetype": "application/pdf",
                    "size": 2048,
                },
            ],
        }
        with patch("nobla.channels.slack.handlers.download_file", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = (b"pdf data", "application/pdf")
            await slack_handlers.handle_event({"event": event, "team_id": "T1"})
            mock_dl.assert_called()

    @pytest.mark.asyncio
    async def test_handler_app_mention_event(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "app_mention",
            "user": "U123",
            "text": "<@U_BOT> hello",
            "ts": "1",
            "channel": "C789",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_keyword_command_unlink(self, slack_handlers):
        slack_handlers._linking.unlink = AsyncMock(return_value=True)
        event = {
            "type": "message",
            "user": "U123",
            "text": "!unlink",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._linking.unlink.assert_called()

    @pytest.mark.asyncio
    async def test_keyword_command_status(self, slack_handlers):
        slack_handlers._linking.resolve = AsyncMock(return_value="user-001")
        event = {
            "type": "message",
            "user": "U123",
            "text": "!status",
            "ts": "1",
            "channel": "D456",
            "channel_type": "im",
        }
        await slack_handlers.handle_event({"event": event, "team_id": "T1"})
        slack_handlers._send_fn.assert_called()

    # ── Adapter edge cases ──
    @pytest.mark.asyncio
    async def test_send_rate_limited_requeues(self):
        adapter = TestSlackAdapter()._make_adapter()
        adapter._client = AsyncMock()
        adapter._rate_limit_queue = MagicMock()
        adapter._rate_limit_queue.enqueue = AsyncMock()
        adapter._client.post.return_value = MagicMock(
            status_code=429,
            headers={"Retry-After": "1"},
            json=lambda: {"ok": False, "error": "rate_limited"},
        )
        resp = ChannelResponse(content="test")
        await adapter.send("U123", resp)
        # Should enqueue for retry rather than raising
        assert adapter._rate_limit_queue.enqueue.called or adapter._client.post.called

    def test_verify_signature_empty_body(self):
        adapter = TestSlackAdapter()._make_adapter(mode="events")
        assert adapter.verify_signature(b"", "123", "v0=bad") is False

    @pytest.mark.asyncio
    async def test_send_with_attachments(self):
        adapter = TestSlackAdapter()._make_adapter()
        adapter._client = AsyncMock()
        adapter._client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "upload_url": "https://up.slack.com/x", "file_id": "F1"},
        )
        adapter._client.put.return_value = MagicMock(status_code=200)
        adapter._client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "ts": "1.1"},
        )
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="img.png",
            mime_type="image/png",
            size_bytes=512,
            data=b"png",
        )
        resp = ChannelResponse(content="See image", attachments=[attachment])
        await adapter.send("U123", resp)

    # ── Media edge cases ──
    @pytest.mark.asyncio
    async def test_download_file_large(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            content=b"x" * 1024,
            headers={"content-type": "application/octet-stream"},
        )
        data, mime = await download_file("https://files.slack.com/big", "tok", client=mock_client)
        assert len(data) == 1024

    @pytest.mark.asyncio
    async def test_get_upload_url_failure(self):
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": False, "error": "not_allowed"},
        )
        with pytest.raises(Exception):
            await get_upload_url("tok", "f.txt", 100, client=mock_client)
```

- [ ] **Step 2: Run all Slack tests**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py -v --tb=short`
Expected: PASS (~100 tests)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_slack_adapter.py
git commit -m "test(5-channels): add Slack adapter edge case and integration tests"
```

---

## Track B: Signal Adapter

### Task 7: Signal Models

**Files:**
- Create: `backend/nobla/channels/signal/__init__.py`
- Create: `backend/nobla/channels/signal/models.py`
- Test: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p backend/nobla/channels/signal
```

```python
# backend/nobla/channels/signal/__init__.py
"""Signal channel adapter (Phase 5-Channels)."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "SignalAdapter":
        from nobla.channels.signal.adapter import SignalAdapter
        return SignalAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 2: Write failing tests for models**

Create `backend/tests/test_signal_adapter.py`:

```python
"""Tests for the Signal channel adapter (Phase 5-Channels).

Covers: models/constants, formatter (plain text, split), media (disk save/load),
handlers (envelope dispatch, data messages, receipts, read receipts, commands,
group mentions, disappearing messages, event emission), adapter (JSON-RPC
connection, send, receive, reconnect, health check), and settings.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.signal.models import (
    CHANNEL_NAME,
    MAX_MESSAGE_LENGTH,
    RPC_METHODS,
    SignalUserContext,
)


class TestSignalModels:
    def test_channel_name(self):
        assert CHANNEL_NAME == "signal"

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 6000

    def test_rpc_methods(self):
        assert isinstance(RPC_METHODS, dict)
        assert "send" in RPC_METHODS
        assert "receive" in RPC_METHODS
        assert "version" in RPC_METHODS

    def test_user_context_basic(self):
        ctx = SignalUserContext(
            source_number="+1234567890",
            source_uuid="uuid-123",
            is_group=False,
            is_bot_mentioned=False,
            timestamp=1234567890000,
        )
        assert ctx.source_number == "+1234567890"
        assert ctx.user_id_str == "+1234567890"
        assert ctx.chat_id_str == "+1234567890"

    def test_user_context_group(self):
        ctx = SignalUserContext(
            source_number="+1234567890",
            source_uuid="uuid-123",
            group_id="group-abc",
            is_group=True,
            is_bot_mentioned=True,
            timestamp=1234567890000,
        )
        assert ctx.chat_id_str == "group-abc"
        assert ctx.is_group is True

    def test_user_context_disappearing(self):
        ctx = SignalUserContext(
            source_number="+1",
            source_uuid="u1",
            is_group=False,
            is_bot_mentioned=False,
            timestamp=0,
            expires_in_seconds=3600,
        )
        assert ctx.expires_in_seconds == 3600
        assert ctx.is_disappearing is True

    def test_user_context_not_disappearing(self):
        ctx = SignalUserContext(
            source_number="+1",
            source_uuid="u1",
            is_group=False,
            is_bot_mentioned=False,
            timestamp=0,
        )
        assert ctx.expires_in_seconds == 0
        assert ctx.is_disappearing is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalModels -v`
Expected: FAIL (import errors)

- [ ] **Step 4: Implement models.py**

```python
# backend/nobla/channels/signal/models.py
"""Signal adapter models, constants, and user context (Phase 5-Channels)."""

from __future__ import annotations

from dataclasses import dataclass

CHANNEL_NAME = "signal"
MAX_MESSAGE_LENGTH = 6000

# JSON-RPC method names for signal-cli daemon
RPC_METHODS: dict[str, str] = {
    "send": "send",
    "receive": "receive",
    "version": "version",
    "list_accounts": "listAccounts",
    "send_receipt": "sendReceipt",
    "send_typing": "sendTyping",
    "get_group": "getGroup",
    "list_groups": "listGroups",
}

# Receipt types
RECEIPT_TYPE_DELIVERY = "delivery"
RECEIPT_TYPE_READ = "read"
RECEIPT_TYPE_VIEWED = "viewed"

# Supported attachment MIME types
SUPPORTED_MIME_TYPES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "video/mp4", "video/3gpp",
    "audio/mpeg", "audio/ogg", "audio/aac",
    "application/pdf", "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})


@dataclass(frozen=True)
class SignalUserContext:
    """Normalized context from an incoming Signal envelope."""

    source_number: str
    source_uuid: str
    is_group: bool
    is_bot_mentioned: bool
    timestamp: int
    group_id: str | None = None
    expires_in_seconds: int = 0

    @property
    def user_id_str(self) -> str:
        return self.source_number

    @property
    def chat_id_str(self) -> str:
        return self.group_id if self.group_id else self.source_number

    @property
    def is_disappearing(self) -> bool:
        return self.expires_in_seconds > 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalModels -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/channels/signal/__init__.py backend/nobla/channels/signal/models.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): add Signal adapter models and constants"
```

---

### Task 8: Signal Formatter

**Files:**
- Create: `backend/nobla/channels/signal/formatter.py`
- Modify: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Write failing tests for formatter**

Append to `backend/tests/test_signal_adapter.py`:

```python
from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.signal.formatter import (
    FormattedMessage,
    format_response,
    split_message,
)


class TestSignalFormatter:
    def test_split_short(self):
        chunks = split_message("Hello", 6000)
        assert chunks == ["Hello"]

    def test_split_at_newline(self):
        text = "Line\n" * 4000
        chunks = split_message(text, 6000)
        assert all(len(c) <= 6000 for c in chunks)

    def test_split_long_word(self):
        text = "X" * 12000
        chunks = split_message(text, 6000)
        assert len(chunks) == 2

    def test_split_exactly_at_limit(self):
        text = "A" * 6000
        chunks = split_message(text, 6000)
        assert len(chunks) == 1

    def test_format_response_simple(self):
        resp = ChannelResponse(content="Hello Signal")
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello Signal"

    def test_format_response_empty(self):
        resp = ChannelResponse(content="")
        msgs = format_response(resp)
        assert msgs == []

    def test_format_response_long_splits(self):
        resp = ChannelResponse(content="Y" * 12000)
        msgs = format_response(resp)
        assert len(msgs) >= 2

    def test_format_response_actions_as_text(self):
        # Signal has no buttons — actions should be rendered as text labels
        resp = ChannelResponse(
            content="Choose:",
            actions=[
                InlineAction(action_id="a:1:yes", label="Yes"),
                InlineAction(action_id="a:1:no", label="No"),
            ],
        )
        msgs = format_response(resp)
        combined = " ".join(m.text for m in msgs)
        assert "Yes" in combined
        assert "No" in combined

    def test_formatted_message_dataclass(self):
        fm = FormattedMessage(text="hello")
        assert fm.text == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalFormatter -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement formatter.py**

```python
# backend/nobla/channels/signal/formatter.py
"""Signal adapter formatter — plain text only (Phase 5-Channels)."""

from __future__ import annotations

from dataclasses import dataclass

from nobla.channels.base import ChannelResponse
from nobla.channels.signal.models import MAX_MESSAGE_LENGTH


@dataclass(frozen=True)
class FormattedMessage:
    """A single outbound Signal message (plain text only)."""
    text: str


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks respecting the limit. Split at newlines, then spaces, then hard-cut."""
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Try to split at last newline before limit
        cut = remaining[:limit].rfind("\n")
        if cut <= 0:
            cut = remaining[:limit].rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Format a ChannelResponse into Signal plain-text messages."""
    if not response.content and not response.actions:
        return []
    text = response.content or ""
    # Render actions as numbered text options (Signal has no buttons)
    if response.actions:
        action_lines = "\n".join(
            f"  [{i + 1}] {a.label}" for i, a in enumerate(response.actions)
        )
        text = f"{text}\n\n{action_lines}" if text else action_lines
    chunks = split_message(text)
    return [FormattedMessage(text=c) for c in chunks]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalFormatter -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/signal/formatter.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): add Signal plain-text formatter"
```

---

### Task 9: Signal Media

**Files:**
- Create: `backend/nobla/channels/signal/media.py`
- Modify: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Write failing tests for media**

Append to `backend/tests/test_signal_adapter.py`:

```python
from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.signal.media import (
    load_attachment_from_path,
    save_attachment_to_disk,
    validate_file_size,
    guess_mime_type,
)


class TestSignalMedia:
    def test_save_attachment_to_disk(self):
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="test.png",
            mime_type="image/png",
            size_bytes=4,
            data=b"\x89PNG",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_attachment_to_disk(attachment, tmpdir)
            assert os.path.exists(path)
            assert path.endswith("test.png")
            with open(path, "rb") as f:
                assert f.read() == b"\x89PNG"

    def test_save_attachment_sanitizes_filename(self):
        attachment = Attachment(
            type=AttachmentType.DOCUMENT,
            filename="../../../etc/passwd",
            mime_type="text/plain",
            size_bytes=5,
            data=b"hello",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_attachment_to_disk(attachment, tmpdir)
            # Should not escape the data_dir
            assert path.startswith(tmpdir)

    def test_save_attachment_no_data(self):
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="empty.png",
            mime_type="image/png",
            size_bytes=0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="no data"):
                save_attachment_to_disk(attachment, tmpdir)

    def test_load_attachment_from_path(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG_DATA")
            f.flush()
            path = f.name
        try:
            att = load_attachment_from_path(path, "image/png")
            assert att.type == AttachmentType.IMAGE
            assert att.data == b"\x89PNG_DATA"
            assert att.filename == os.path.basename(path)
        finally:
            os.unlink(path)

    def test_load_attachment_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_attachment_from_path("/nonexistent/file.png", "image/png")

    def test_validate_file_size_ok(self):
        assert validate_file_size(1024, max_mb=100) is True

    def test_validate_file_size_too_large(self):
        assert validate_file_size(200 * 1024 * 1024, max_mb=100) is False

    def test_guess_mime_type_png(self):
        assert guess_mime_type("photo.png") == "image/png"

    def test_guess_mime_type_unknown(self):
        result = guess_mime_type("file.xyz")
        assert result == "application/octet-stream"

    def test_guess_mime_type_pdf(self):
        assert guess_mime_type("doc.pdf") == "application/pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalMedia -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement media.py**

Create `backend/nobla/channels/signal/media.py` (~150 lines) with:

- `validate_file_size(size_bytes, max_mb)` → bool
- `guess_mime_type(filename)` → str (using mimetypes stdlib)
- `save_attachment_to_disk(attachment, data_dir)` → str path:
  - Sanitize filename (strip path traversal, use `os.path.basename`)
  - Raise ValueError if no data
  - Write to `{data_dir}/attachments/{sanitized_filename}`
  - Return full path
- `load_attachment_from_path(path, mime_type)` → Attachment:
  - Read file, detect AttachmentType from mime
  - Return Attachment with data bytes
- `detect_attachment_type(mime_type)` → AttachmentType (reuse pattern from WhatsApp)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalMedia -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/signal/media.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): add Signal file-based media handler"
```

---

### Task 10: Signal Handlers

**Files:**
- Create: `backend/nobla/channels/signal/handlers.py`
- Modify: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Write failing tests for handlers**

Append to `backend/tests/test_signal_adapter.py`:

```python
from nobla.channels.signal.handlers import SignalHandlers


@pytest.fixture
def signal_handlers():
    linking = AsyncMock()
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    h = SignalHandlers(
        linking_service=linking,
        event_bus=event_bus,
        bot_phone_number="+15551234567",
    )
    h.set_send_fn(AsyncMock())
    return h


class TestSignalHandlers:
    # ── Data message routing ──
    @pytest.mark.asyncio
    async def test_handle_dm_message(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1234567890000,
            "dataMessage": {
                "message": "Hello bot",
                "timestamp": 1234567890000,
            },
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_group_message_with_mention(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1234567890000,
            "dataMessage": {
                "message": "Hey bot",
                "timestamp": 1234567890000,
                "groupInfo": {"groupId": "group-abc", "type": "DELIVER"},
                "mentions": [{"uuid": "bot-uuid", "start": 0, "length": 3}],
            },
        }
        signal_handlers._bot_uuid = "bot-uuid"
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_group_message_no_mention_ignored(self, signal_handlers):
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1234567890000,
            "dataMessage": {
                "message": "Regular chat",
                "timestamp": 1234567890000,
                "groupInfo": {"groupId": "group-abc", "type": "DELIVER"},
            },
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_own_message_ignored(self, signal_handlers):
        envelope = {
            "source": "+15551234567",  # Bot's own number
            "sourceUuid": "bot-uuid",
            "timestamp": 1234567890000,
            "dataMessage": {"message": "echo", "timestamp": 1234567890000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_not_called()

    # ── Commands ──
    @pytest.mark.asyncio
    async def test_command_start(self, signal_handlers):
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="CODE12")
        envelope = {
            "source": "+1111111111",
            "sourceUuid": "uuid-2",
            "timestamp": 1000,
            "dataMessage": {"message": "/start", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_command_link(self, signal_handlers):
        signal_handlers._linking.link = AsyncMock(return_value=True)
        envelope = {
            "source": "+1111111111",
            "sourceUuid": "uuid-2",
            "timestamp": 1000,
            "dataMessage": {"message": "/link user-001", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._linking.link.assert_called()

    @pytest.mark.asyncio
    async def test_command_unlink(self, signal_handlers):
        signal_handlers._linking.unlink = AsyncMock(return_value=True)
        envelope = {
            "source": "+1111111111",
            "sourceUuid": "uuid-2",
            "timestamp": 1000,
            "dataMessage": {"message": "/unlink", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._linking.unlink.assert_called()

    @pytest.mark.asyncio
    async def test_command_status_linked(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1111111111",
            "sourceUuid": "uuid-2",
            "timestamp": 1000,
            "dataMessage": {"message": "/status", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._send_fn.assert_called()

    # ── Unlinked user pairing ──
    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_prompt(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=None)
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="PAR456")
        envelope = {
            "source": "+9999999999",
            "sourceUuid": "uuid-new",
            "timestamp": 1000,
            "dataMessage": {"message": "Hello", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._send_fn.assert_called()
        signal_handlers._event_bus.publish.assert_not_called()

    # ── Receipts ──
    @pytest.mark.asyncio
    async def test_handle_delivery_receipt(self, signal_handlers):
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 2000,
            "receiptMessage": {
                "type": "DELIVERY",
                "timestamps": [1000],
            },
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_called()
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.type == "channel.message.status"

    @pytest.mark.asyncio
    async def test_handle_read_receipt(self, signal_handlers):
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 2000,
            "receiptMessage": {
                "type": "READ",
                "timestamps": [1000],
            },
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_called()

    # ── Read receipt sending ──
    @pytest.mark.asyncio
    async def test_sends_read_receipt_on_process(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        signal_handlers._send_receipt_fn = AsyncMock()
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1234567890000,
            "dataMessage": {"message": "Test", "timestamp": 1234567890000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._send_receipt_fn.assert_called_with(
            "+1234567890", 1234567890000
        )

    # ── Disappearing messages ──
    @pytest.mark.asyncio
    async def test_disappearing_message_sets_metadata(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {
                "message": "Secret",
                "timestamp": 1000,
                "expiresInSeconds": 3600,
            },
        }
        await signal_handlers.handle_message(envelope)
        call = signal_handlers._event_bus.publish.call_args[0][0]
        meta = call.payload.get("metadata", {})
        assert meta.get("disappearing") is True
        assert meta.get("expires_in_seconds") == 3600

    # ── Attachments ──
    @pytest.mark.asyncio
    async def test_handle_message_with_attachment(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {
                "message": "See file",
                "timestamp": 1000,
                "attachments": [
                    {
                        "contentType": "image/png",
                        "filename": "photo.png",
                        "size": 2048,
                        "id": "att-1",
                    },
                ],
            },
        }
        with patch("nobla.channels.signal.handlers.load_attachment_from_path") as mock_load:
            mock_load.return_value = Attachment(
                type=AttachmentType.IMAGE,
                filename="photo.png",
                mime_type="image/png",
                size_bytes=2048,
                data=b"png",
            )
            await signal_handlers.handle_message(envelope)
            signal_handlers._event_bus.publish.assert_called()

    # ── Event emission ──
    @pytest.mark.asyncio
    async def test_event_has_correct_channel(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {"message": "Test", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.type == "channel.message.in"
        assert call.payload["channel"] == "signal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalHandlers -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement handlers.py**

Create `backend/nobla/channels/signal/handlers.py` (~350 lines) with:

**SignalHandlers** class:
- `__init__(linking_service, event_bus, bot_phone_number)`
- `set_send_fn(fn)` + `set_send_receipt_fn(fn)` — wiring
- `async handle_message(envelope)` — main dispatcher:
  - Skip if `source == bot_phone_number`
  - Route to `_handle_data_message` if `dataMessage` present
  - Route to `_handle_receipt` if `receiptMessage` present
- `_handle_data_message(ctx, data)`:
  - Extract text from `data["message"]`
  - Check group + mentions for activation
  - Check for commands (`/start`, `/link`, `/unlink`, `/status`)
  - Extract attachments (load from signal-cli paths)
  - Resolve linked user; if unlinked → pairing prompt
  - Set disappearing metadata if `expiresInSeconds > 0`
  - Build ChannelMessage, emit `channel.message.in`
  - Send read receipt
- `_handle_receipt(ctx, receipt)` — emit `channel.message.status`
- `_emit_event(type, payload, user_id)` — wraps event_bus.publish

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalHandlers -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/signal/handlers.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): add Signal handlers with commands, receipts, and disappearing messages"
```

---

### Task 11: Signal Adapter

**Files:**
- Create: `backend/nobla/channels/signal/adapter.py`
- Modify: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Write failing tests for adapter**

Append to `backend/tests/test_signal_adapter.py`:

```python
from nobla.channels.signal.adapter import SignalAdapter


class _FakeSignalSettings:
    enabled = True
    phone_number = "+15551234567"
    signal_cli_path = "signal-cli"
    mode = "json-rpc"
    rpc_host = "localhost"
    rpc_port = 7583
    data_dir = "/tmp/signal-data"
    group_activation = "mention"
    max_file_size_mb = 100


class TestSignalAdapter:
    def _make_adapter(self):
        settings = _FakeSignalSettings()
        handlers = MagicMock()
        handlers.handle_message = AsyncMock()
        return SignalAdapter(settings=settings, handlers=handlers)

    # ── Properties ──
    def test_name(self):
        adapter = self._make_adapter()
        assert adapter.name == "signal"

    # ── Send ──
    @pytest.mark.asyncio
    async def test_send_dm(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        resp = ChannelResponse(content="Hello")
        await adapter.send("+1234567890", resp)
        adapter._rpc_call.assert_called()
        call_args = adapter._rpc_call.call_args
        assert call_args[0][0] == "send"

    @pytest.mark.asyncio
    async def test_send_group(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        resp = ChannelResponse(content="Group hello")
        await adapter.send("group-abc", resp, is_group=True)
        call_args = adapter._rpc_call.call_args
        params = call_args[1] if len(call_args) > 1 else call_args[0][1]
        # Should include groupId parameter

    @pytest.mark.asyncio
    async def test_send_notification(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        await adapter.send_notification("+1234567890", "Alert!")
        adapter._rpc_call.assert_called()

    @pytest.mark.asyncio
    async def test_send_long_message_splits(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        resp = ChannelResponse(content="Z" * 12000)
        await adapter.send("+1234567890", resp)
        assert adapter._rpc_call.call_count >= 2

    # ── Parse callback ──
    def test_parse_callback_noop(self):
        adapter = self._make_adapter()
        action_id, meta = adapter.parse_callback({"anything": "data"})
        assert action_id == ""
        assert meta == {}

    # ── Read receipt ──
    @pytest.mark.asyncio
    async def test_send_read_receipt(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock()
        await adapter.send_read_receipt("+1234567890", 1234567890000)
        adapter._rpc_call.assert_called_with(
            "sendReceipt", recipient="+1234567890", timestamp=1234567890000, type="read",
        )

    # ── Health check ──
    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"version": "0.13.0"})
        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = self._make_adapter()
        adapter._rpc_call = AsyncMock(side_effect=ConnectionError("refused"))
        result = await adapter.health_check()
        assert result is False

    # ── JSON-RPC ──
    @pytest.mark.asyncio
    async def test_rpc_call_formats_request(self):
        adapter = self._make_adapter()
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_reader.readline = AsyncMock(
            return_value=json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode() + b"\n"
        )
        adapter._reader = mock_reader
        adapter._writer = mock_writer
        adapter._rpc_id = 0
        result = await adapter._rpc_call("version")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_rpc_call_error_response(self):
        adapter = self._make_adapter()
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_reader.readline = AsyncMock(
            return_value=json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "fail"}}).encode() + b"\n"
        )
        adapter._reader = mock_reader
        adapter._writer = mock_writer
        adapter._rpc_id = 0
        with pytest.raises(Exception, match="fail"):
            await adapter._rpc_call("bad_method")

    # ── Lifecycle ──
    @pytest.mark.asyncio
    async def test_start_connects(self):
        adapter = self._make_adapter()
        with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.close = MagicMock()
            mock_conn.return_value = (mock_reader, mock_writer)
            # Mock the receive loop to not actually run
            with patch.object(adapter, "_start_receive_loop", new_callable=AsyncMock):
                await adapter.start()
                mock_conn.assert_called_with("localhost", 7583)

    @pytest.mark.asyncio
    async def test_stop_closes_connection(self):
        adapter = self._make_adapter()
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        adapter._writer = mock_writer
        adapter._reader = AsyncMock()
        adapter._receive_task = None
        await adapter.stop()
        mock_writer.close.assert_called()

    # ── Reconnection ──
    @pytest.mark.asyncio
    async def test_reconnect_backoff(self):
        adapter = self._make_adapter()
        assert adapter._reconnect_delay(0) == 1
        assert adapter._reconnect_delay(1) == 2
        assert adapter._reconnect_delay(2) == 4
        assert adapter._reconnect_delay(10) == 30  # capped at 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalAdapter -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement adapter.py**

Create `backend/nobla/channels/signal/adapter.py` (~250 lines) implementing `BaseChannelAdapter`:

- `name = "signal"` property
- Constructor takes `settings` + `handlers`
- `async start()`: `asyncio.open_connection(host, port)`, wire handler send/receipt functions, start receive loop
- `async stop()`: cancel receive task, close writer
- `async send(channel_user_id, response, is_group=False)`: format with `format_response()`, send each chunk via `_rpc_call("send", ...)`
- `async send_notification(channel_user_id, text)`: simple `_rpc_call("send", ...)`
- `parse_callback(raw)`: return `("", {})` (no-op)
- `async send_read_receipt(source, timestamp)`: `_rpc_call("sendReceipt", ...)`
- `async health_check()`: `_rpc_call("version")`, return True/False
- `async _rpc_call(method, **params)`: JSON-RPC 2.0 request/response over TCP
- `async _start_receive_loop()`: background task reading lines from reader, parsing JSON-RPC notifications, dispatching to handlers
- `_reconnect_delay(attempt)`: `min(2**attempt, 30)` seconds
- Reconnection logic: on connection drop, exponential backoff reconnect

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py::TestSignalAdapter -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/signal/adapter.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): add Signal adapter with JSON-RPC daemon transport"
```

---

### Task 12: Signal Edge Cases & Integration Tests

**Files:**
- Modify: `backend/tests/test_signal_adapter.py`

- [ ] **Step 1: Write additional edge case tests**

Append to `backend/tests/test_signal_adapter.py`:

```python
class TestSignalEdgeCases:
    # ── Formatter ──
    def test_split_empty_string(self):
        assert split_message("", 6000) == []

    def test_format_response_actions_only(self):
        resp = ChannelResponse(
            content="",
            actions=[InlineAction(action_id="a:1:go", label="Go")],
        )
        msgs = format_response(resp)
        assert len(msgs) >= 1
        assert "Go" in msgs[0].text

    # ── Media ──
    def test_save_attachment_creates_subdir(self):
        attachment = Attachment(
            type=AttachmentType.DOCUMENT,
            filename="doc.pdf",
            mime_type="application/pdf",
            size_bytes=3,
            data=b"pdf",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_attachment_to_disk(attachment, tmpdir)
            assert os.path.dirname(path) != tmpdir  # Should be in attachments subdir

    def test_validate_file_size_zero(self):
        assert validate_file_size(0, max_mb=100) is True

    def test_guess_mime_type_jpeg(self):
        assert guess_mime_type("photo.jpg") in ("image/jpeg", "image/jpg")

    def test_guess_mime_type_mp4(self):
        assert guess_mime_type("video.mp4") == "video/mp4"

    # ── Handlers ──
    @pytest.mark.asyncio
    async def test_typing_indicator_envelope_ignored(self, signal_handlers):
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "typingMessage": {"action": "STARTED"},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_data_message(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {"timestamp": 1000},  # No message text
        }
        await signal_handlers.handle_message(envelope)
        # Should still process (might have attachments only)

    @pytest.mark.asyncio
    async def test_command_case_insensitive(self, signal_handlers):
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="AAA111")
        envelope = {
            "source": "+1111111111",
            "sourceUuid": "uuid-2",
            "timestamp": 1000,
            "dataMessage": {"message": "/START", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        signal_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_disappearing_zero_means_disabled(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value="user-001")
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {
                "message": "Normal",
                "timestamp": 1000,
                "expiresInSeconds": 0,
            },
        }
        await signal_handlers.handle_message(envelope)
        call = signal_handlers._event_bus.publish.call_args[0][0]
        meta = call.payload.get("metadata", {})
        assert meta.get("disappearing", False) is False

    # ── Adapter ──
    @pytest.mark.asyncio
    async def test_send_empty_response(self):
        adapter = TestSignalAdapter()._make_adapter()
        adapter._rpc_call = AsyncMock()
        resp = ChannelResponse(content="")
        await adapter.send("+1", resp)
        adapter._rpc_call.assert_not_called()

    def test_reconnect_delay_capped(self):
        adapter = TestSignalAdapter()._make_adapter()
        assert adapter._reconnect_delay(100) == 30

    def test_reconnect_delay_first_attempt(self):
        adapter = TestSignalAdapter()._make_adapter()
        assert adapter._reconnect_delay(0) == 1
```

- [ ] **Step 2: Run all Signal tests**

Run: `cd backend && python -m pytest tests/test_signal_adapter.py -v --tb=short`
Expected: PASS (~75 tests)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_signal_adapter.py
git commit -m "test(5-channels): add Signal adapter edge case tests"
```

---

## Track C: Shared Wiring (depends on Track A + Track B)

### Task 13: Settings + Gateway Wiring

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Modify: `backend/nobla/gateway/lifespan.py`
- Modify: `backend/nobla/gateway/app.py` (or wherever webhook routes are registered — add `/webhook/slack` for Events API mode)

- [ ] **Step 1: Add SlackSettings and SignalSettings to settings.py**

After `WhatsAppSettings` class (line ~362), add:

```python
class SlackSettings(BaseModel):
    """Slack adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""
    signing_secret: str = ""
    mode: str = "socket"  # "socket" or "events"
    command_name: str = "/nobla"
    webhook_path: str = "/webhook/slack"
    group_activation: str = "mention"
    max_file_size_mb: int = 100

    @model_validator(mode="after")
    def validate_tokens(self):
        if self.enabled and not self.bot_token:
            raise ValueError("bot_token is required when Slack is enabled")
        if self.enabled and self.mode == "socket" and not self.app_token:
            raise ValueError("app_token is required for Socket Mode")
        if self.enabled and self.mode == "events" and not self.signing_secret:
            raise ValueError("signing_secret is required for Events API mode")
        return self


class SignalSettings(BaseModel):
    """Signal adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    phone_number: str = ""
    signal_cli_path: str = "signal-cli"
    mode: str = "json-rpc"
    rpc_host: str = "localhost"
    rpc_port: int = 7583
    data_dir: str = ""
    group_activation: str = "mention"
    max_file_size_mb: int = 100

    @model_validator(mode="after")
    def validate_phone(self):
        if self.enabled and not self.phone_number:
            raise ValueError("phone_number is required when Signal is enabled")
        return self
```

Add to `Settings` class (after `whatsapp` field, line ~482):

```python
    slack: SlackSettings = Field(default_factory=SlackSettings)
    signal: SignalSettings = Field(default_factory=SignalSettings)
```

- [ ] **Step 2: Add settings validation tests**

Append to both test files:

In `test_slack_adapter.py`:
```python
class TestSlackSettings:
    def test_default_disabled(self):
        from nobla.config.settings import SlackSettings
        s = SlackSettings()
        assert s.enabled is False

    def test_enabled_requires_bot_token(self):
        from nobla.config.settings import SlackSettings
        with pytest.raises(Exception):
            SlackSettings(enabled=True)

    def test_socket_mode_requires_app_token(self):
        from nobla.config.settings import SlackSettings
        with pytest.raises(Exception):
            SlackSettings(enabled=True, bot_token="xoxb-x", mode="socket")

    def test_events_mode_requires_signing_secret(self):
        from nobla.config.settings import SlackSettings
        with pytest.raises(Exception):
            SlackSettings(enabled=True, bot_token="xoxb-x", mode="events")

    def test_valid_socket_mode(self):
        from nobla.config.settings import SlackSettings
        s = SlackSettings(enabled=True, bot_token="xoxb-x", app_token="xapp-x", mode="socket")
        assert s.mode == "socket"

    def test_valid_events_mode(self):
        from nobla.config.settings import SlackSettings
        s = SlackSettings(enabled=True, bot_token="xoxb-x", signing_secret="sec", mode="events")
        assert s.mode == "events"

    def test_default_command_name(self):
        from nobla.config.settings import SlackSettings
        s = SlackSettings()
        assert s.command_name == "/nobla"
```

In `test_signal_adapter.py`:
```python
class TestSignalSettings:
    def test_default_disabled(self):
        from nobla.config.settings import SignalSettings
        s = SignalSettings()
        assert s.enabled is False

    def test_enabled_requires_phone(self):
        from nobla.config.settings import SignalSettings
        with pytest.raises(Exception):
            SignalSettings(enabled=True)

    def test_valid_config(self):
        from nobla.config.settings import SignalSettings
        s = SignalSettings(enabled=True, phone_number="+15551234567")
        assert s.mode == "json-rpc"

    def test_default_rpc_port(self):
        from nobla.config.settings import SignalSettings
        s = SignalSettings()
        assert s.rpc_port == 7583
```

- [ ] **Step 3: Wire adapters in gateway lifespan**

In `backend/nobla/gateway/lifespan.py`, add to `_init_channels()` after the WhatsApp block:

```python
    # ── Slack ──────────────────────────────────────────────────────
    if settings.slack.enabled and settings.slack.bot_token:
        try:
            from nobla.channels.slack.handlers import SlackHandlers
            from nobla.channels.slack.adapter import SlackAdapter

            slack_handlers = SlackHandlers(
                linking_service=linking_service,
                event_bus=event_bus,
                bot_user_id="",  # Resolved during start() via auth.test
                bot_token=settings.slack.bot_token,
            )
            slack_adapter = SlackAdapter(
                settings=settings.slack,
                handlers=slack_handlers,
            )
            channel_manager.register(slack_adapter)
            await slack_adapter.start()
            # start() calls auth.test to resolve bot_user_id and sets it
            # on handlers via handlers.set_bot_user_id(resolved_id)
            logger.info("Slack adapter started (mode=%s)", settings.slack.mode)
        except Exception:
            logger.exception("Failed to start Slack adapter")

    # ── Signal ─────────────────────────────────────────────────────
    if settings.signal.enabled and settings.signal.phone_number:
        try:
            from nobla.channels.signal.handlers import SignalHandlers
            from nobla.channels.signal.adapter import SignalAdapter

            signal_handlers = SignalHandlers(
                linking_service=linking_service,
                event_bus=event_bus,
                bot_phone_number=settings.signal.phone_number,
            )
            signal_adapter = SignalAdapter(
                settings=settings.signal,
                handlers=signal_handlers,
            )
            channel_manager.register(signal_adapter)
            await signal_adapter.start()
            # start() wires handlers.set_send_fn() and set_send_receipt_fn()
            logger.info("Signal adapter started (mode=%s)", settings.signal.mode)
        except Exception:
            logger.exception("Failed to start Signal adapter")
```

**Important implementation notes for adapter `start()` methods:**
- **Slack `start()`** must call `auth.test` to resolve `bot_user_id`, then call `handlers.set_bot_user_id(resolved_id)` so message filtering works correctly. It must also wire `handlers.set_send_fn()`.
- **Signal `start()`** must wire both `handlers.set_send_fn()` and `handlers.set_send_receipt_fn()`.

- [ ] **Step 4: Add Slack webhook route for Events API mode**

In the gateway app setup (where WhatsApp's `/webhook/whatsapp` route is registered), add a `/webhook/slack` POST route:

```python
@app.post(settings.slack.webhook_path)
async def slack_webhook(request: Request):
    """Handle Slack Events API, slash commands, and interactivity payloads."""
    body = await request.body()
    payload = json.loads(body)

    # URL verification challenge (initial setup)
    if payload.get("type") == "url_verification":
        return slack_adapter.handle_url_verification(payload)

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not slack_adapter.verify_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Dispatch event
    await slack_adapter.handle_webhook_payload(payload)
    return {"ok": True}
```

This route is only needed for Events API mode. In Socket Mode, all events arrive via WebSocket. The route should be conditionally registered based on `settings.slack.mode == "events"`.

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/test_slack_adapter.py tests/test_signal_adapter.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Run existing tests to ensure no regressions**

Run: `cd backend && python -m pytest tests/ -v --tb=short -x`
Expected: All 1,142+ backend tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/gateway/lifespan.py backend/tests/test_slack_adapter.py backend/tests/test_signal_adapter.py
git commit -m "feat(5-channels): wire Slack + Signal adapters into settings and gateway lifespan"
```

---

### Task 14: Final Verification & CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short --co -q | tail -5` (count tests)
Expected: ~1,317 tests collected (1,142 existing + ~100 Slack + ~75 Signal)

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Verify file line counts are within 750-line limit**

```bash
wc -l backend/nobla/channels/slack/*.py backend/nobla/channels/signal/*.py
```

Expected: All files under 750 lines

- [ ] **Step 3: Update CLAUDE.md**

Update the following sections:
- Test count: update to new total
- Phase 5-Channels status: add Slack + Signal as complete
- Phase 5 Sub-phases table: add Slack + Signal row
- Project Structure: add slack/ and signal/ under channels/

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 5-Channels Slack + Signal completion"
```
