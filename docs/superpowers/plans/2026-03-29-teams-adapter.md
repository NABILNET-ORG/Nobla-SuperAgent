# Microsoft Teams Channel Adapter — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Microsoft Teams channel adapter using Azure Bot Framework REST API with JWT validation, Adaptive Cards formatting, and OAuth2 token management.

**Architecture:** Webhook-only inbound (JWT-validated), REST API outbound (Bearer token auto-refreshed). 6-file adapter pattern matching Slack/Signal/WhatsApp. Multi-tenant, mention-only in channels.

**Tech Stack:** Python 3.12+, FastAPI, httpx, PyJWT, cryptography

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/nobla/channels/teams/__init__.py` | Create | Lazy import wrapper |
| `backend/nobla/channels/teams/models.py` | Create | TeamsUserContext dataclass + API constants |
| `backend/nobla/channels/teams/formatter.py` | Create | Markdown → Adaptive Card conversion |
| `backend/nobla/channels/teams/media.py` | Create | Attachment upload/download |
| `backend/nobla/channels/teams/handlers.py` | Create | Activity dispatch, commands, linking, event bus |
| `backend/nobla/channels/teams/adapter.py` | Create | TeamsAdapter ABC impl, TokenManager, JWT validation |
| `backend/nobla/config/settings.py` | Modify | Add TeamsSettings (after line 406) + field (after line 528) |
| `backend/nobla/gateway/lifespan.py` | Modify | Add Teams init block (after line 255) |
| `backend/tests/test_teams_adapter.py` | Create | ~100 tests across all components |

---

### Task 1: Models & Constants

**Files:**
- Create: `backend/nobla/channels/teams/__init__.py`
- Create: `backend/nobla/channels/teams/models.py`
- Test: `backend/tests/test_teams_adapter.py`

- [ ] **Step 1: Create the teams directory**

```bash
mkdir -p backend/nobla/channels/teams
```

- [ ] **Step 2: Write model tests (~8 tests)**

Create `backend/tests/test_teams_adapter.py` with:

```python
"""Microsoft Teams channel adapter tests (Phase 5-Channels)."""

from __future__ import annotations

import pytest

# ── Models & Constants ──────────────────────────────────────


class TestTeamsUserContext:
    """TeamsUserContext dataclass tests."""

    def test_create_minimal(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123",
            display_name="Test User",
            tenant_id="tenant-abc",
            conversation_id="conv-456",
            service_url="https://smba.trafficmanager.net/teams/",
            message_id="msg-789",
        )
        assert ctx.user_id == "user-123"
        assert ctx.display_name == "Test User"
        assert ctx.tenant_id == "tenant-abc"
        assert ctx.conversation_id == "conv-456"
        assert ctx.service_url == "https://smba.trafficmanager.net/teams/"
        assert ctx.message_id == "msg-789"
        assert ctx.channel_id is None
        assert ctx.is_dm is False
        assert ctx.is_bot_mentioned is False
        assert ctx.raw_extras == {}

    def test_create_full(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123",
            display_name="Test User",
            tenant_id="tenant-abc",
            conversation_id="conv-456",
            service_url="https://smba.trafficmanager.net/teams/",
            message_id="msg-789",
            channel_id="19:abc@thread.tacv2",
            is_dm=True,
            is_bot_mentioned=True,
            raw_extras={"locale": "en-US"},
        )
        assert ctx.channel_id == "19:abc@thread.tacv2"
        assert ctx.is_dm is True
        assert ctx.is_bot_mentioned is True
        assert ctx.raw_extras == {"locale": "en-US"}

    def test_user_id_str_property(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123", display_name="U", tenant_id="t",
            conversation_id="c", service_url="http://x", message_id="m",
        )
        assert ctx.user_id_str == "user-123"

    def test_channel_id_str_property(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="u", display_name="U", tenant_id="t",
            conversation_id="conv-1", service_url="http://x",
            message_id="m", channel_id="ch-1",
        )
        assert ctx.channel_id_str == "ch-1"

    def test_channel_id_str_none_returns_conversation_id(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="u", display_name="U", tenant_id="t",
            conversation_id="conv-1", service_url="http://x", message_id="m",
        )
        assert ctx.channel_id_str == "conv-1"


class TestTeamsConstants:
    """Constants and MIME mapping tests."""

    def test_channel_name(self):
        from nobla.channels.teams.models import CHANNEL_NAME
        assert CHANNEL_NAME == "teams"

    def test_mime_to_media_type_image(self):
        from nobla.channels.teams.models import MIME_TO_MEDIA_TYPE
        assert MIME_TO_MEDIA_TYPE["image/png"] == "image"
        assert MIME_TO_MEDIA_TYPE["image/jpeg"] == "image"

    def test_supported_activity_types(self):
        from nobla.channels.teams.models import SUPPORTED_ACTIVITY_TYPES
        assert "message" in SUPPORTED_ACTIVITY_TYPES
        assert "invoke" in SUPPORTED_ACTIVITY_TYPES
        assert "conversationUpdate" in SUPPORTED_ACTIVITY_TYPES
        assert "typing" not in SUPPORTED_ACTIVITY_TYPES
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTeamsUserContext -v --no-header 2>&1 | head -20
cd backend && python -m pytest tests/test_teams_adapter.py::TestTeamsConstants -v --no-header 2>&1 | head -20
```

Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 4: Create `__init__.py`**

```python
"""Microsoft Teams channel adapter (Phase 5-Channels)."""

__all__ = ["TeamsAdapter"]


def __getattr__(name: str):
    if name == "TeamsAdapter":
        from nobla.channels.teams.adapter import TeamsAdapter

        return TeamsAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 5: Create `models.py`**

```python
"""Microsoft Teams channel adapter data models and API constants (Phase 5-Channels).

Spec reference: Azure Bot Framework REST API + Adaptive Cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# -- API constants ---------------------------------------------------

CHANNEL_NAME = "teams"

# Adaptive Card limits
MAX_CARD_SIZE_BYTES = 28_672  # 28 KB payload limit
MAX_CARD_ACTIONS = 5  # Max Action.Submit buttons per card
MAX_TEXT_BLOCK_LENGTH = 10_000  # TextBlock text limit

# Attachment limits
MAX_ATTACHMENT_INLINE_BYTES = 262_144  # 256 KB inline base64 threshold
MAX_FILE_SIZE_BYTES = 104_857_600  # 100 MB

# Bot Framework URLs
BOT_FRAMEWORK_TOKEN_URL = (
    "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
)
BOT_FRAMEWORK_OPENID_URL = (
    "https://login.botframework.com/v1/.well-known/openidconfiguration"
)
BOT_FRAMEWORK_TOKEN_SCOPE = "https://api.botframework.com/.default"

# MIME type -> media type mapping
MIME_TO_MEDIA_TYPE: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/ogg": "audio",
    "audio/wav": "audio",
    "video/mp4": "video",
    "video/quicktime": "video",
    "application/pdf": "document",
    "application/zip": "document",
    "text/plain": "document",
    "text/csv": "document",
    "application/json": "document",
}

# Activity types the adapter handles
SUPPORTED_ACTIVITY_TYPES = frozenset({
    "message",
    "invoke",
    "conversationUpdate",
    "messageReaction",
})

# Activity types to silently ignore
IGNORED_ACTIVITY_TYPES = frozenset({
    "typing",
    "endOfConversation",
    "event",
    "installationUpdate",
})


# -- Data models -----------------------------------------------------


@dataclass(slots=True)
class TeamsUserContext:
    """Normalized context extracted from an inbound Teams Activity.

    Attributes:
        user_id: Azure AD user ID (from Activity.from.id).
        display_name: User display name (from Activity.from.name).
        tenant_id: Azure AD tenant ID.
        conversation_id: Conversation ID.
        service_url: Bot Framework service URL for replies.
        message_id: Activity ID.
        channel_id: Teams channel ID (None for personal/DM chats).
        is_dm: Whether this is a personal (1:1) chat.
        is_bot_mentioned: Whether the bot was @mentioned.
        raw_extras: Catch-all for platform-specific fields.
    """

    user_id: str
    display_name: str
    tenant_id: str
    conversation_id: str
    service_url: str
    message_id: str
    channel_id: str | None = None
    is_dm: bool = False
    is_bot_mentioned: bool = False
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id_str(self) -> str:
        return self.user_id

    @property
    def channel_id_str(self) -> str:
        return self.channel_id or self.conversation_id
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTeamsUserContext tests/test_teams_adapter.py::TestTeamsConstants -v --no-header
```

Expected: 8 PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/channels/teams/__init__.py backend/nobla/channels/teams/models.py backend/tests/test_teams_adapter.py
git commit -m "feat(5-channels): add Teams adapter models and constants"
```

---

### Task 2: Adaptive Cards Formatter

**Files:**
- Create: `backend/nobla/channels/teams/formatter.py`
- Modify: `backend/tests/test_teams_adapter.py`

- [ ] **Step 1: Write formatter tests (~20 tests)**

Append to `backend/tests/test_teams_adapter.py`:

```python
# ── Formatter ───────────────────────────────────────────────


class TestSplitMessage:
    """Text splitting for oversized content."""

    def test_short_text_no_split(self):
        from nobla.channels.teams.formatter import split_message
        result = split_message("Hello world", 100)
        assert result == ["Hello world"]

    def test_split_at_newline(self):
        from nobla.channels.teams.formatter import split_message
        text = "line1\nline2\nline3"
        result = split_message(text, 10)
        assert len(result) >= 2
        assert result[0] == "line1"

    def test_split_at_space(self):
        from nobla.channels.teams.formatter import split_message
        text = "word1 word2 word3"
        result = split_message(text, 10)
        assert len(result) >= 2

    def test_hard_cut(self):
        from nobla.channels.teams.formatter import split_message
        text = "abcdefghijklmnop"
        result = split_message(text, 8)
        assert result[0] == "abcdefgh"


class TestMarkdownToCardBody:
    """Markdown → Adaptive Card body element conversion."""

    def test_empty_text(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        assert markdown_to_card_body("") == []

    def test_plain_text(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("Hello world")
        assert len(body) == 1
        assert body[0]["type"] == "TextBlock"
        assert body[0]["text"] == "Hello world"
        assert body[0]["wrap"] is True

    def test_h1_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("# Big Title")
        assert body[0]["type"] == "TextBlock"
        assert body[0]["size"] == "Large"
        assert body[0]["weight"] == "Bolder"
        assert body[0]["text"] == "Big Title"

    def test_h2_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("## Medium Title")
        assert body[0]["size"] == "Medium"
        assert body[0]["weight"] == "Bolder"

    def test_h3_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("### Small Title")
        assert body[0]["size"] == "Default"
        assert body[0]["weight"] == "Bolder"

    def test_code_block(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("```\nprint('hi')\n```")
        code_block = [b for b in body if b.get("fontType") == "Monospace"]
        assert len(code_block) == 1
        assert "print('hi')" in code_block[0]["text"]

    def test_divider(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("above\n---\nbelow")
        separators = [b for b in body if b.get("type") == "ColumnSet"]
        assert len(separators) == 1

    def test_blockquote(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("> This is a quote")
        containers = [b for b in body if b.get("type") == "Container"]
        assert len(containers) == 1
        assert containers[0]["style"] == "accent"

    def test_mixed_content(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        text = "# Title\nSome text\n---\n```\ncode\n```\n> quote"
        body = markdown_to_card_body(text)
        assert len(body) >= 4  # heading + text + divider + code + quote


class TestBuildCardActions:
    """InlineAction → Action.Submit conversion."""

    def test_single_action(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="test:1:approve", label="Approve")]
        result = build_card_actions(actions)
        assert len(result) == 1
        assert result[0]["type"] == "Action.Submit"
        assert result[0]["title"] == "Approve"
        assert result[0]["data"]["action_id"] == "test:1:approve"

    def test_primary_style(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="a:1:go", label="Go", style="primary")]
        result = build_card_actions(actions)
        assert result[0]["style"] == "positive"

    def test_danger_style(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="a:1:del", label="Delete", style="danger")]
        result = build_card_actions(actions)
        assert result[0]["style"] == "destructive"

    def test_max_actions_cap(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id=f"a:{i}:x", label=f"Btn{i}") for i in range(10)]
        result = build_card_actions(actions)
        assert len(result) == 5  # MAX_CARD_ACTIONS


class TestFormatResponse:
    """Full format_response() integration."""

    def test_empty_content(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content=""))
        assert result["type"] == "message"
        assert result["attachments"] == []

    def test_text_produces_adaptive_card(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content="Hello"))
        assert len(result["attachments"]) == 1
        card = result["attachments"][0]
        assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
        assert card["content"]["type"] == "AdaptiveCard"
        assert card["content"]["version"] == "1.4"

    def test_actions_included_in_card(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse, InlineAction
        actions = [InlineAction(action_id="a:1:ok", label="OK")]
        result = format_response(ChannelResponse(content="Choose:", actions=actions))
        card = result["attachments"][0]["content"]
        assert len(card["actions"]) == 1

    def test_text_only_no_actions(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content="Just text"))
        card = result["attachments"][0]["content"]
        assert card["actions"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestSplitMessage tests/test_teams_adapter.py::TestMarkdownToCardBody tests/test_teams_adapter.py::TestBuildCardActions tests/test_teams_adapter.py::TestFormatResponse -v --no-header 2>&1 | head -20
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `formatter.py`**

```python
"""Microsoft Teams Adaptive Card message formatting (Phase 5-Channels).

Converts markdown-style text into Adaptive Card body elements:
  - ``# heading`` -> TextBlock Large/Bolder
  - ``## heading`` -> TextBlock Medium/Bolder
  - ``### heading`` -> TextBlock Default/Bolder
  - code fences -> TextBlock Monospace
  - ``---`` -> ColumnSet separator
  - ``> quote`` -> Container accent style
  - plain text -> TextBlock wrap
  - InlineActions -> Action.Submit buttons
"""

from __future__ import annotations

import re
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.teams.models import MAX_CARD_ACTIONS, MAX_TEXT_BLOCK_LENGTH


# -- Text splitting --------------------------------------------------


def split_message(text: str, limit: int = MAX_TEXT_BLOCK_LENGTH) -> list[str]:
    """Split long text into chunks that fit within the limit.

    Prefers splitting at newlines, then at spaces, then hard-cuts.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_pos = remaining.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = remaining.rfind(" ", 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


# -- Adaptive Card element builders ----------------------------------


def _text_block(
    text: str,
    *,
    size: str | None = None,
    weight: str | None = None,
    font_type: str | None = None,
    color: str | None = None,
    wrap: bool = True,
) -> dict[str, Any]:
    """Build an Adaptive Card TextBlock element."""
    block: dict[str, Any] = {"type": "TextBlock", "text": text[:MAX_TEXT_BLOCK_LENGTH], "wrap": wrap}
    if size:
        block["size"] = size
    if weight:
        block["weight"] = weight
    if font_type:
        block["fontType"] = font_type
    if color:
        block["color"] = color
    return block


def _separator() -> dict[str, Any]:
    """Build a visual separator (ColumnSet with separator property)."""
    return {
        "type": "ColumnSet",
        "separator": True,
        "spacing": "Medium",
        "columns": [],
    }


def _quote_container(text: str) -> dict[str, Any]:
    """Build a quote block as an accent-styled Container."""
    return {
        "type": "Container",
        "style": "accent",
        "items": [_text_block(text, color="Default")],
    }


# -- Markdown to card body conversion --------------------------------

_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_DIVIDER_RE = re.compile(r"^---+\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_QUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)

_HEADING_SIZES = {1: "Large", 2: "Medium", 3: "Default"}


def markdown_to_card_body(text: str) -> list[dict[str, Any]]:
    """Convert markdown text into Adaptive Card body elements."""
    if not text:
        return []

    body: list[dict[str, Any]] = []

    # Extract code fences and replace with placeholders
    code_blocks: list[str] = []

    def _replace_code(match: re.Match) -> str:
        code = match.group(2).rstrip("\n")
        idx = len(code_blocks)
        code_blocks.append(code)
        return f"\x00CODE{idx}\x00"

    processed = _CODE_FENCE_RE.sub(_replace_code, text)

    lines = processed.split("\n")
    current_text: list[str] = []

    def _flush_text() -> None:
        joined = "\n".join(current_text).strip()
        if joined:
            body.append(_text_block(joined))
        current_text.clear()

    for line in lines:
        stripped = line.strip()

        # Code placeholder
        if stripped.startswith("\x00CODE") and stripped.endswith("\x00"):
            _flush_text()
            try:
                idx = int(stripped[5:-1])
                body.append(_text_block(code_blocks[idx], font_type="Monospace"))
            except (ValueError, IndexError):
                current_text.append(line)
            continue

        # Divider
        if _DIVIDER_RE.match(line):
            _flush_text()
            body.append(_separator())
            continue

        # Header
        header_match = _HEADER_RE.match(line)
        if header_match:
            _flush_text()
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            size = _HEADING_SIZES.get(level, "Default")
            body.append(_text_block(header_text, size=size, weight="Bolder"))
            continue

        # Blockquote
        quote_match = _QUOTE_RE.match(line)
        if quote_match:
            _flush_text()
            body.append(_quote_container(quote_match.group(1)))
            continue

        # Regular text
        current_text.append(line)

    _flush_text()
    return body


# -- Actions conversion ----------------------------------------------

# Map our style names to Adaptive Card Action styles
_STYLE_MAP = {
    "primary": "positive",
    "danger": "destructive",
    "secondary": "default",
}


def build_card_actions(actions: list[InlineAction]) -> list[dict[str, Any]]:
    """Convert InlineActions to Adaptive Card Action.Submit list."""
    result: list[dict[str, Any]] = []

    for action in actions[:MAX_CARD_ACTIONS]:
        entry: dict[str, Any] = {
            "type": "Action.Submit",
            "title": action.label,
            "data": {"action_id": action.action_id},
        }
        style = _STYLE_MAP.get(action.style)
        if style and style != "default":
            entry["style"] = style
        result.append(entry)

    return result


# -- Main formatting entry point -------------------------------------


def format_response(response: ChannelResponse) -> dict[str, Any]:
    """Format a ChannelResponse into a Teams Activity payload with Adaptive Card.

    Returns a dict with ``type`` and ``attachments`` ready for the Bot Framework API.
    """
    if not response.content:
        return {"type": "message", "attachments": []}

    body = markdown_to_card_body(response.content)
    actions = build_card_actions(response.actions) if response.actions else []

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestSplitMessage tests/test_teams_adapter.py::TestMarkdownToCardBody tests/test_teams_adapter.py::TestBuildCardActions tests/test_teams_adapter.py::TestFormatResponse -v --no-header
```

Expected: 20 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/teams/formatter.py backend/tests/test_teams_adapter.py
git commit -m "feat(5-channels): add Teams Adaptive Card formatter"
```

---

### Task 3: Media Handling

**Files:**
- Create: `backend/nobla/channels/teams/media.py`
- Modify: `backend/tests/test_teams_adapter.py`

- [ ] **Step 1: Write media tests (~12 tests)**

Append to `backend/tests/test_teams_adapter.py`:

```python
# ── Media ───────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock, patch


class TestDetectAttachmentType:
    """MIME → AttachmentType mapping."""

    def test_image_png(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("image/png") == AttachmentType.IMAGE

    def test_audio_mpeg(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("audio/mpeg") == AttachmentType.AUDIO

    def test_video_mp4(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("video/mp4") == AttachmentType.VIDEO

    def test_unknown_defaults_document(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("application/x-unknown") == AttachmentType.DOCUMENT


@pytest.mark.asyncio
class TestDownloadAttachment:
    """Attachment download tests."""

    async def test_download_content_url(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"filedata"
        mock_resp.headers = {"Content-Length": "8", "Content-Type": "image/png"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        attachment_data = {
            "contentType": "image/png",
            "contentUrl": "https://teams.cdn/file.png",
            "name": "file.png",
        }
        result = await download_attachment(attachment_data, "token-123", mock_client)
        assert result is not None
        assert result.data == b"filedata"
        assert result.mime_type == "image/png"

    async def test_download_direct_url(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"filedata"
        mock_resp.headers = {"Content-Length": "8", "Content-Type": "application/pdf"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        attachment_data = {
            "contentType": "application/vnd.microsoft.teams.file.download.info",
            "content": {"downloadUrl": "https://direct/file.pdf"},
            "name": "file.pdf",
        }
        result = await download_attachment(attachment_data, "token-123", mock_client)
        assert result is not None

    async def test_download_size_exceeded(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "999999999", "Content-Type": "video/mp4"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        attachment_data = {
            "contentType": "video/mp4",
            "contentUrl": "https://teams.cdn/big.mp4",
            "name": "big.mp4",
        }
        result = await download_attachment(
            attachment_data, "token", mock_client, max_size_bytes=1000
        )
        assert result is None

    async def test_download_error_returns_none(self):
        from nobla.channels.teams.media import download_attachment
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        attachment_data = {
            "contentType": "image/png",
            "contentUrl": "https://teams.cdn/file.png",
            "name": "file.png",
        }
        result = await download_attachment(attachment_data, "token", mock_client)
        assert result is None


@pytest.mark.asyncio
class TestSendAttachment:
    """Attachment send tests."""

    async def test_send_small_inline_base64(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(
            type=AttachmentType.IMAGE,
            filename="small.png",
            mime_type="image/png",
            size_bytes=100,
            data=b"\x89PNG" + b"\x00" * 96,
        )
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/",
            "conv-1", att, "token", mock_client,
        )
        assert result is True

    async def test_send_large_with_url_as_hero_card(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(
            type=AttachmentType.DOCUMENT,
            filename="big.zip",
            mime_type="application/zip",
            size_bytes=500_000,
            url="https://example.com/big.zip",
        )
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/",
            "conv-1", att, "token", mock_client,
        )
        assert result is True

    async def test_send_large_no_url_returns_false(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(
            type=AttachmentType.VIDEO,
            filename="big.mp4",
            mime_type="video/mp4",
            size_bytes=500_000,
            data=b"\x00" * 500_000,
        )
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/",
            "conv-1", att, "token", AsyncMock(),
        )
        assert result is False

    async def test_send_no_data_no_url_returns_false(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(
            type=AttachmentType.DOCUMENT,
            filename="empty.txt",
            mime_type="text/plain",
            size_bytes=0,
        )
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/",
            "conv-1", att, "token", AsyncMock(),
        )
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestDetectAttachmentType tests/test_teams_adapter.py::TestDownloadAttachment tests/test_teams_adapter.py::TestSendAttachment -v --no-header 2>&1 | head -20
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `media.py`**

```python
"""Microsoft Teams media upload/download (Phase 5-Channels).

Download:
  - contentUrl: GET with Bearer token auth
  - downloadUrl (file download info): direct GET, no auth

Upload:
  - ≤256KB: inline base64 data URI in Activity attachments
  - >256KB with URL: hero card with download link
  - >256KB without URL: unsupported (log warning)
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from typing import Any

import httpx

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.teams.models import (
    MAX_ATTACHMENT_INLINE_BYTES,
    MIME_TO_MEDIA_TYPE,
)

logger = logging.getLogger(__name__)


# -- Type detection --------------------------------------------------


def detect_attachment_type(mime_type: str) -> AttachmentType:
    """Map a MIME type to the unified AttachmentType enum."""
    media_type = MIME_TO_MEDIA_TYPE.get(mime_type, "document")
    mapping = {
        "image": AttachmentType.IMAGE,
        "audio": AttachmentType.AUDIO,
        "video": AttachmentType.VIDEO,
        "document": AttachmentType.DOCUMENT,
    }
    return mapping.get(media_type, AttachmentType.DOCUMENT)


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to application/octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


# -- Download --------------------------------------------------------


async def download_attachment(
    attachment_data: dict[str, Any],
    bot_token: str,
    client: httpx.AsyncClient,
    max_size_bytes: int = 100 * 1024 * 1024,
) -> Attachment | None:
    """Download a Teams attachment from its contentUrl or downloadUrl.

    Returns an Attachment on success, None on failure.
    """
    content_type = attachment_data.get("contentType", "")
    name = attachment_data.get("name", "attachment")

    # Determine URL and whether auth is needed
    url: str | None = None
    needs_auth = True

    if content_type == "application/vnd.microsoft.teams.file.download.info":
        # File download info card — use direct download URL
        content = attachment_data.get("content", {})
        url = content.get("downloadUrl")
        needs_auth = False
        # Use the actual file MIME type, not the card content type
        content_type = guess_mime_type(name)
    else:
        url = attachment_data.get("contentUrl")

    if not url:
        logger.warning("No download URL found in attachment: %s", name)
        return None

    try:
        headers = {}
        if needs_auth:
            headers["Authorization"] = f"Bearer {bot_token}"

        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

        # Size check
        content_length = int(resp.headers.get("Content-Length", len(resp.content)))
        if content_length > max_size_bytes:
            logger.warning(
                "Attachment %s exceeds size limit (%d > %d)",
                name, content_length, max_size_bytes,
            )
            return None

        att_type = detect_attachment_type(content_type)
        return Attachment(
            type=att_type,
            filename=name,
            mime_type=content_type,
            size_bytes=len(resp.content),
            data=resp.content,
        )
    except Exception:
        logger.exception("Failed to download Teams attachment: %s", name)
        return None


# -- Send ------------------------------------------------------------


async def send_attachment(
    service_url: str,
    conversation_id: str,
    attachment: Attachment,
    bot_token: str,
    client: httpx.AsyncClient,
) -> bool:
    """Send an Attachment via Teams. Returns True on success.

    Strategy:
      - ≤256KB with data: inline as base64 data URI
      - >256KB with URL: send as hero card with download link
      - Otherwise: cannot send, return False
    """
    has_data = attachment.data and len(attachment.data) > 0
    has_url = bool(attachment.url)

    # Small file with data: inline base64
    if has_data and len(attachment.data) <= MAX_ATTACHMENT_INLINE_BYTES:
        b64 = base64.b64encode(attachment.data).decode()
        activity = {
            "type": "message",
            "attachments": [
                {
                    "contentType": attachment.mime_type,
                    "contentUrl": f"data:{attachment.mime_type};base64,{b64}",
                    "name": attachment.filename,
                }
            ],
        }
        return await _post_activity(service_url, conversation_id, activity, bot_token, client)

    # Large file with URL: hero card with download link
    if has_url:
        activity = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.hero",
                    "content": {
                        "title": attachment.filename,
                        "subtitle": f"{attachment.mime_type} ({attachment.size_bytes} bytes)",
                        "buttons": [
                            {
                                "type": "openUrl",
                                "title": "Download",
                                "value": attachment.url,
                            }
                        ],
                    },
                }
            ],
        }
        return await _post_activity(service_url, conversation_id, activity, bot_token, client)

    logger.warning(
        "Cannot send attachment %s: too large for inline (%d bytes) and no URL",
        attachment.filename, attachment.size_bytes,
    )
    return False


async def _post_activity(
    service_url: str,
    conversation_id: str,
    activity: dict[str, Any],
    bot_token: str,
    client: httpx.AsyncClient,
) -> bool:
    """POST an activity to the Bot Framework conversation endpoint."""
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    try:
        resp = await client.post(
            url,
            json=activity,
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to post activity to %s", conversation_id)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestDetectAttachmentType tests/test_teams_adapter.py::TestDownloadAttachment tests/test_teams_adapter.py::TestSendAttachment -v --no-header
```

Expected: 12 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/teams/media.py backend/tests/test_teams_adapter.py
git commit -m "feat(5-channels): add Teams media upload/download"
```

---

### Task 4: Handlers (Commands, Linking, Event Bus)

**Files:**
- Create: `backend/nobla/channels/teams/handlers.py`
- Modify: `backend/tests/test_teams_adapter.py`

- [ ] **Step 1: Write handler tests (~25 tests)**

Append to `backend/tests/test_teams_adapter.py`:

```python
# ── Handlers ────────────────────────────────────────────────


def _make_linking_mock(linked_user=None):
    """Create a mock linking service."""
    mock = AsyncMock()
    mock.resolve = AsyncMock(return_value=linked_user)
    mock.create_pairing_code = AsyncMock(return_value="ABC123")
    mock.link = AsyncMock()
    mock.unlink = AsyncMock()
    return mock


def _make_event_bus_mock():
    """Create a mock event bus."""
    mock = AsyncMock()
    mock.publish = AsyncMock()
    return mock


def _make_linked_user(nobla_user_id="nobla-user-1"):
    """Create a mock linked user object."""
    user = MagicMock()
    user.nobla_user_id = nobla_user_id
    user.conversation_id = "conv-1"
    return user


def _make_message_activity(
    text="hello",
    user_id="user-123",
    user_name="Test User",
    conversation_id="conv-456",
    service_url="https://smba.trafficmanager.net/teams/",
    channel_id=None,
    entities=None,
    tenant_id="tenant-abc",
):
    """Build a minimal Teams message Activity dict."""
    activity = {
        "type": "message",
        "id": "msg-789",
        "text": text,
        "from": {"id": user_id, "name": user_name},
        "conversation": {"id": conversation_id, "conversationType": "personal" if not channel_id else "channel"},
        "channelId": "msteams",
        "serviceUrl": service_url,
        "channelData": {"tenant": {"id": tenant_id}},
    }
    if channel_id:
        activity["channelData"]["channel"] = {"id": channel_id}
    if entities:
        activity["entities"] = entities
    return activity


@pytest.mark.asyncio
class TestTeamsHandlers:
    """TeamsHandlers activity dispatch tests."""

    async def test_set_send_fn(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        fn = AsyncMock()
        h.set_send_fn(fn)
        assert h._send_fn is fn

    async def test_handle_message_dm_always_responds(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())

        activity = _make_message_activity(text="hi there")
        await h.handle_activity(activity)

        # Should have emitted channel.message.in
        assert h._event_bus.publish.called

    async def test_handle_message_channel_no_mention_ignored(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())

        activity = _make_message_activity(text="hello", channel_id="ch-1")
        await h.handle_activity(activity)

        # No mention -> should not process
        assert not h._event_bus.publish.called

    async def test_handle_message_channel_with_mention(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())

        entities = [{"type": "mention", "mentioned": {"id": "app-id", "name": "Nobla"}}]
        activity = _make_message_activity(
            text="<at>Nobla</at> what time is it",
            channel_id="ch-1",
            entities=entities,
        )
        await h.handle_activity(activity)
        assert h._event_bus.publish.called

    async def test_mention_stripped_from_text(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())

        entities = [{"type": "mention", "mentioned": {"id": "app-id", "name": "Nobla"}}]
        activity = _make_message_activity(
            text="<at>Nobla</at> do something",
            entities=entities,
        )
        await h.handle_activity(activity)

        # Verify the emitted event has cleaned text
        call_args = bus.publish.call_args
        event = call_args[0][0]
        assert "<at>" not in event.payload.get("content", "")

    async def test_unlinked_user_gets_pairing_code(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linking = _make_linking_mock(linked_user=None)
        h = TeamsHandlers(linking, _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="hello")
        await h.handle_activity(activity)

        linking.create_pairing_code.assert_called_once()
        assert send_fn.called

    async def test_conversation_ref_captured(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())

        activity = _make_message_activity(
            user_id="user-123",
            service_url="https://smba.trafficmanager.net/teams/",
            conversation_id="conv-456",
        )
        await h.handle_activity(activity)

        ref = h.get_conversation_ref("user-123")
        assert ref is not None
        assert ref["service_url"] == "https://smba.trafficmanager.net/teams/"
        assert ref["conversation_id"] == "conv-456"


@pytest.mark.asyncio
class TestTeamsKeywordCommands:
    """Keyword command (!start, !link, !unlink, !status) tests."""

    async def test_cmd_start_unlinked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!start")
        await h.handle_activity(activity)
        assert send_fn.called
        msg = send_fn.call_args[0][1]
        assert "ABC123" in msg

    async def test_cmd_start_already_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!start")
        await h.handle_activity(activity)
        msg = send_fn.call_args[0][1]
        assert "Welcome back" in msg

    async def test_cmd_link_no_args_gives_pairing_code(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!link")
        await h.handle_activity(activity)
        msg = send_fn.call_args[0][1]
        assert "ABC123" in msg

    async def test_cmd_link_with_user_id(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linking = _make_linking_mock()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(linking, bus, "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!link my-nobla-id")
        await h.handle_activity(activity)

        linking.link.assert_called_once_with("teams", "user-123", "my-nobla-id")
        assert bus.publish.called

    async def test_cmd_unlink_when_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        linking = _make_linking_mock(linked)
        bus = _make_event_bus_mock()
        h = TeamsHandlers(linking, bus, "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!unlink")
        await h.handle_activity(activity)

        linking.unlink.assert_called_once()
        msg = send_fn.call_args[0][1]
        assert "unlinked" in msg.lower()

    async def test_cmd_unlink_when_not_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!unlink")
        await h.handle_activity(activity)
        msg = send_fn.call_args[0][1]
        assert "not" in msg.lower()

    async def test_cmd_status_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!status")
        await h.handle_activity(activity)
        msg = send_fn.call_args[0][1]
        assert "Linked" in msg

    async def test_cmd_status_not_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = _make_message_activity(text="!status")
        await h.handle_activity(activity)
        msg = send_fn.call_args[0][1]
        assert "Not linked" in msg


@pytest.mark.asyncio
class TestTeamsActivityDispatch:
    """Non-message activity dispatch tests."""

    async def test_invoke_activity_emits_callback(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())

        activity = {
            "type": "invoke",
            "name": "adaptiveCard/action",
            "from": {"id": "user-123", "name": "Test"},
            "conversation": {"id": "conv-1", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelData": {"tenant": {"id": "t1"}},
            "value": {"action": {"data": {"action_id": "approval:req-1:approve"}}},
        }
        await h.handle_activity(activity)
        assert bus.publish.called

    async def test_conversation_update_bot_added(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)

        activity = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "app-id", "name": "Nobla"}],
            "from": {"id": "user-1", "name": "U"},
            "conversation": {"id": "conv-1", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelData": {"tenant": {"id": "t1"}},
        }
        await h.handle_activity(activity)
        assert send_fn.called
        msg = send_fn.call_args[0][1]
        assert "Nobla" in msg

    async def test_ignored_activity_type(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(), bus, "app-id")

        activity = {
            "type": "typing",
            "from": {"id": "u1", "name": "U"},
            "conversation": {"id": "c1"},
            "serviceUrl": "http://x",
            "channelData": {"tenant": {"id": "t1"}},
        }
        await h.handle_activity(activity)
        assert not bus.publish.called

    async def test_event_bus_emission_content(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())

        activity = _make_message_activity(text="test message")
        await h.handle_activity(activity)

        event = bus.publish.call_args[0][0]
        assert event.event_type == "channel.message.in"
        assert event.source == "teams"
        assert event.payload["content"] == "test message"

    async def test_send_fn_not_set_logs_warning(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        # Don't set send_fn

        activity = _make_message_activity(text="!start")
        # Should not raise, just log warning
        await h.handle_activity(activity)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTeamsHandlers tests/test_teams_adapter.py::TestTeamsKeywordCommands tests/test_teams_adapter.py::TestTeamsActivityDispatch -v --no-header 2>&1 | head -20
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `handlers.py`**

```python
"""Microsoft Teams event handlers (Phase 5-Channels).

Parses inbound Bot Framework Activity objects, extracts user context,
routes messages through the linking + executor pipeline, and emits
events on the bus.

Keyword commands: !start !link !unlink !status
Channel policy:
  - DMs (personal): always respond
  - Channels: respond only when bot is @mentioned
"""

from __future__ import annotations

import logging
import re
from typing import Any

from nobla.channels.base import ChannelMessage
from nobla.channels.teams.models import (
    CHANNEL_NAME,
    IGNORED_ACTIVITY_TYPES,
    SUPPORTED_ACTIVITY_TYPES,
    TeamsUserContext,
)

logger = logging.getLogger(__name__)

# Type aliases to avoid hard import cycles.
LinkingService = Any
EventBus = Any

# Regex to strip <at>...</at> mention tags from message text
_AT_TAG_RE = re.compile(r"<at>.*?</at>\s*", re.IGNORECASE)


class TeamsHandlers:
    """Inbound activity handlers for Microsoft Teams.

    Args:
        linking: UserLinkingService for resolving/creating links.
        event_bus: NoblaEventBus for emitting channel events.
        app_id: Azure Bot registration App ID (for mention detection).
        max_file_size_mb: Max attachment size to download.
    """

    def __init__(
        self,
        linking: LinkingService,
        event_bus: EventBus,
        app_id: str,
        max_file_size_mb: int = 100,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._app_id = app_id
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._send_fn: Any = None
        self._conversation_refs: dict[str, dict[str, str]] = {}

    def set_send_fn(self, fn: Any) -> None:
        """Register the adapter's raw send function for handler replies."""
        self._send_fn = fn

    def get_conversation_ref(self, channel_user_id: str) -> dict[str, str] | None:
        """Get stored conversation reference for proactive messaging."""
        return self._conversation_refs.get(channel_user_id)

    # -- Activity entry point ----------------------------------------

    async def handle_activity(self, activity: dict[str, Any]) -> None:
        """Dispatch an inbound Bot Framework Activity by type."""
        activity_type = activity.get("type", "")

        if activity_type in IGNORED_ACTIVITY_TYPES:
            return
        if activity_type not in SUPPORTED_ACTIVITY_TYPES:
            return

        if activity_type == "message":
            await self._handle_message(activity)
        elif activity_type == "invoke":
            await self._handle_invoke(activity)
        elif activity_type == "conversationUpdate":
            await self._handle_conversation_update(activity)
        elif activity_type == "messageReaction":
            await self._handle_reaction(activity)

    # -- Message handling --------------------------------------------

    async def _handle_message(self, activity: dict[str, Any]) -> None:
        """Process an inbound message Activity."""
        ctx = self._extract_user_context(activity)
        text = activity.get("text", "")

        # Store conversation reference for proactive messaging
        self._store_conversation_ref(ctx)

        # Channel policy: DMs always respond, channels only on mention
        if not ctx.is_dm and not ctx.is_bot_mentioned:
            return

        # Strip <at>BotName</at> tags from text
        text = _AT_TAG_RE.sub("", text).strip()

        # Check for keyword commands
        stripped = text.strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_keyword_command(ctx, stripped, text)
            return

        # Resolve linked user
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_pairing_prompt(ctx, code)
            return

        # Emit channel.message.in event
        await self._emit_event(
            "channel.message.in",
            {
                "channel": CHANNEL_NAME,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
                "content": text,
                "has_attachments": bool(activity.get("attachments")),
            },
            user_id=linked.nobla_user_id,
        )

    # -- Keyword commands (! prefix) ---------------------------------

    async def _dispatch_keyword_command(
        self, ctx: TeamsUserContext, stripped: str, raw_text: str,
    ) -> None:
        """Route keyword commands (!start, !link, !unlink, !status)."""
        parts = stripped.split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "!start": self._cmd_start,
            "!link": self._cmd_link,
            "!unlink": self._cmd_unlink,
            "!status": self._cmd_status,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(ctx, args)

    async def _cmd_start(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.channel_id_str,
                "Welcome back! You're linked to Nobla. Send any message to chat.",
            )
            return

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        await self._send_text(
            ctx.channel_id_str,
            f"Welcome to **Nobla Agent**!\n\n"
            f"To link your account, use code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n\n"
            f"Code expires in 5 minutes.",
        )

    async def _cmd_link(self, ctx: TeamsUserContext, args: str) -> None:
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_text(
                ctx.channel_id_str,
                f"Your pairing code: `{code}`\n"
                f"Enter this in the Nobla app, or type: `!link <user_id>`",
            )
            return

        nobla_user_id = args.strip()
        try:
            await self._linking.link(
                CHANNEL_NAME, ctx.user_id_str, nobla_user_id
            )
            await self._send_text(
                ctx.channel_id_str,
                f"Linked to Nobla account `{nobla_user_id}`.",
            )
            await self._emit_event(
                "channel.user.linked",
                {
                    "channel": CHANNEL_NAME,
                    "channel_user_id": ctx.user_id_str,
                    "nobla_user_id": nobla_user_id,
                },
                user_id=nobla_user_id,
            )
        except Exception:
            logger.exception("Link failed for %s", ctx.user_id_str)
            await self._send_text(
                ctx.channel_id_str, "Link failed. Check your user ID."
            )

    async def _cmd_unlink(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await self._send_text(ctx.channel_id_str, "Not currently linked.")
            return

        nobla_user_id = linked.nobla_user_id
        await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
        await self._send_text(ctx.channel_id_str, "Account unlinked.")
        await self._emit_event(
            "channel.user.unlinked",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            },
            user_id=nobla_user_id,
        )

    async def _cmd_status(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.channel_id_str,
                f"**Status:** Linked\n"
                f"**Nobla ID:** `{linked.nobla_user_id}`\n"
                f"**Channel:** Teams ({ctx.user_id_str})",
            )
        else:
            await self._send_text(
                ctx.channel_id_str,
                "**Status:** Not linked\nUse `!link` to connect your account.",
            )

    # -- Invoke (button callbacks) -----------------------------------

    async def _handle_invoke(self, activity: dict[str, Any]) -> None:
        """Handle Action.Submit callbacks from Adaptive Cards."""
        user_id = activity.get("from", {}).get("id", "")
        linked = await self._linking.resolve(CHANNEL_NAME, user_id)
        if not linked:
            return

        value = activity.get("value", {})
        # Action.Submit puts data in value.action.data or directly in value
        action_data = value
        if "action" in value and isinstance(value["action"], dict):
            action_data = value["action"].get("data", value)

        action_id = action_data.get("action_id", "")
        if action_id:
            await self._emit_event(
                "channel.callback",
                {
                    "channel": CHANNEL_NAME,
                    "action_id": action_id,
                    "user_id": linked.nobla_user_id,
                    "channel_user_id": user_id,
                },
                user_id=linked.nobla_user_id,
            )

    # -- Conversation update -----------------------------------------

    async def _handle_conversation_update(self, activity: dict[str, Any]) -> None:
        """Handle bot added/removed from conversations."""
        members_added = activity.get("membersAdded", [])
        for member in members_added:
            if member.get("id") == self._app_id:
                conv_id = activity.get("conversation", {}).get("id", "")
                await self._send_text(
                    conv_id,
                    "Hi! I'm **Nobla Agent**. Type `!start` to get started.",
                )
                return

    # -- Message reactions -------------------------------------------

    async def _handle_reaction(self, activity: dict[str, Any]) -> None:
        """Handle message reactions (low priority, emit event only)."""
        user_id = activity.get("from", {}).get("id", "")
        linked = await self._linking.resolve(CHANNEL_NAME, user_id)
        if not linked:
            return

        reactions = activity.get("reactionsAdded", [])
        for reaction in reactions:
            await self._emit_event(
                "channel.reaction",
                {
                    "channel": CHANNEL_NAME,
                    "user_id": linked.nobla_user_id,
                    "reaction": reaction.get("type", ""),
                },
                user_id=linked.nobla_user_id,
            )

    # -- Helpers -----------------------------------------------------

    def _extract_user_context(self, activity: dict[str, Any]) -> TeamsUserContext:
        """Extract TeamsUserContext from a Bot Framework Activity."""
        from_obj = activity.get("from", {})
        conv = activity.get("conversation", {})
        channel_data = activity.get("channelData", {})
        tenant_id = channel_data.get("tenant", {}).get("id", "")
        channel_id = channel_data.get("channel", {}).get("id") if "channel" in channel_data else None

        is_dm = conv.get("conversationType") == "personal"
        is_mentioned = self._check_mention(activity.get("entities", []))

        return TeamsUserContext(
            user_id=from_obj.get("id", ""),
            display_name=from_obj.get("name", ""),
            tenant_id=tenant_id,
            conversation_id=conv.get("id", ""),
            service_url=activity.get("serviceUrl", ""),
            message_id=activity.get("id", ""),
            channel_id=channel_id,
            is_dm=is_dm,
            is_bot_mentioned=is_mentioned,
        )

    def _check_mention(self, entities: list[dict[str, Any]]) -> bool:
        """Check if the bot was @mentioned in the Activity entities."""
        for entity in entities:
            if entity.get("type") == "mention":
                mentioned = entity.get("mentioned", {})
                if mentioned.get("id") == self._app_id:
                    return True
        return False

    def _store_conversation_ref(self, ctx: TeamsUserContext) -> None:
        """Cache conversation reference for proactive messaging."""
        self._conversation_refs[ctx.user_id] = {
            "service_url": ctx.service_url,
            "conversation_id": ctx.conversation_id,
            "tenant_id": ctx.tenant_id,
            "channel_id": ctx.channel_id or "",
        }

    async def _send_text(self, conversation_id: str, text: str) -> None:
        """Send a plain text message via the registered send function."""
        if self._send_fn:
            await self._send_fn(conversation_id, text)
        else:
            logger.warning(
                "No send function registered - cannot reply to %s",
                conversation_id,
            )

    async def _send_pairing_prompt(
        self, ctx: TeamsUserContext, code: str,
    ) -> None:
        await self._send_text(
            ctx.channel_id_str,
            f"Hi! To use Nobla, link your account.\n\n"
            f"Pairing code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n"
            f"Code expires in 5 minutes.",
        )

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit an event on the bus if available."""
        if not self._event_bus:
            return
        try:
            from nobla.events.models import NoblaEvent

            event = NoblaEvent(
                event_type=event_type,
                source=CHANNEL_NAME,
                payload=payload,
                user_id=user_id,
            )
            await self._event_bus.publish(event)
        except Exception:
            logger.exception("Failed to emit %s event", event_type)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTeamsHandlers tests/test_teams_adapter.py::TestTeamsKeywordCommands tests/test_teams_adapter.py::TestTeamsActivityDispatch -v --no-header
```

Expected: 25 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/teams/handlers.py backend/tests/test_teams_adapter.py
git commit -m "feat(5-channels): add Teams handlers with commands and event bus"
```

---

### Task 5: Adapter (TokenManager, JWT Validation, Lifecycle)

**Files:**
- Create: `backend/nobla/channels/teams/adapter.py`
- Modify: `backend/tests/test_teams_adapter.py`

- [ ] **Step 1: Write JWT + TokenManager tests (~23 tests)**

Append to `backend/tests/test_teams_adapter.py`:

```python
# ── Token Manager ───────────────────────────────────────────

import time
import json


@pytest.mark.asyncio
class TestTokenManager:
    """OAuth2 client_credentials token management tests."""

    async def test_initial_token_fetch(self):
        from nobla.channels.teams.adapter import TokenManager
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        tm = TokenManager("app-id", "app-pass", mock_client)
        token = await tm.get_token()
        assert token == "tok-1"

    async def test_cache_hit_no_refetch(self):
        from nobla.channels.teams.adapter import TokenManager
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        tm = TokenManager("app-id", "app-pass", mock_client)
        await tm.get_token()
        await tm.get_token()
        # Should only have fetched once
        assert mock_client.post.call_count == 1

    async def test_refresh_near_expiry(self):
        from nobla.channels.teams.adapter import TokenManager
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok-new", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        tm = TokenManager("app-id", "app-pass", mock_client, refresh_margin=300)
        # Manually set token as near-expired
        tm._token = "tok-old"
        tm._expires_at = time.time() + 100  # Within 300s margin
        token = await tm.get_token()
        assert token == "tok-new"
        assert mock_client.post.call_count == 1

    async def test_refresh_on_expired(self):
        from nobla.channels.teams.adapter import TokenManager
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok-new", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        tm = TokenManager("app-id", "app-pass", mock_client)
        tm._token = "tok-old"
        tm._expires_at = time.time() - 100  # Already expired
        token = await tm.get_token()
        assert token == "tok-new"

    async def test_token_endpoint_error(self):
        from nobla.channels.teams.adapter import TokenManager
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        tm = TokenManager("app-id", "app-pass", mock_client)
        with pytest.raises(Exception, match="network error"):
            await tm.get_token()

    async def test_concurrent_refresh_single_request(self):
        import asyncio
        from nobla.channels.teams.adapter import TokenManager

        call_count = 0

        async def slow_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"access_token": "tok-1", "expires_in": 3600}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.post = slow_post

        tm = TokenManager("app-id", "app-pass", mock_client)
        results = await asyncio.gather(tm.get_token(), tm.get_token(), tm.get_token())
        assert all(t == "tok-1" for t in results)
        assert call_count == 1  # Only one actual request


# ── JWT Validation ──────────────────────────────────────────


@pytest.mark.asyncio
class TestJWTValidation:
    """JWT validation for inbound Teams webhooks."""

    async def test_missing_auth_header_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")
        result = validator.validate_token("")
        assert result is None

    async def test_malformed_token_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")
        result = validator.validate_token("Bearer not.a.jwt")
        assert result is None

    async def test_no_bearer_prefix_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")
        result = validator.validate_token("Basic abc123")
        assert result is None

    async def test_jwks_unavailable_rejects_all(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")
        validator._jwks_available = False
        result = validator.validate_token("Bearer eyJ.eyJ.sig")
        assert result is None

    async def test_valid_token_accepted(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        # Mock the internal decode to return valid claims
        claims = {
            "iss": "https://api.botframework.com",
            "aud": "app-id",
            "exp": time.time() + 3600,
            "tid": "tenant-1",
        }
        with patch.object(validator, "_decode_and_verify", return_value=claims):
            result = validator.validate_token("Bearer eyJ.eyJ.sig")
        assert result is not None
        assert result["aud"] == "app-id"

    async def test_expired_token_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        claims = {
            "iss": "https://api.botframework.com",
            "aud": "app-id",
            "exp": time.time() - 100,
            "tid": "tenant-1",
        }
        with patch.object(validator, "_decode_and_verify", return_value=claims):
            result = validator.validate_token("Bearer eyJ.eyJ.sig")
        assert result is None

    async def test_wrong_audience_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        claims = {
            "iss": "https://api.botframework.com",
            "aud": "wrong-app-id",
            "exp": time.time() + 3600,
        }
        with patch.object(validator, "_decode_and_verify", return_value=claims):
            result = validator.validate_token("Bearer eyJ.eyJ.sig")
        assert result is None

    async def test_wrong_issuer_rejected(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        claims = {
            "iss": "https://evil.example.com",
            "aud": "app-id",
            "exp": time.time() + 3600,
        }
        with patch.object(validator, "_decode_and_verify", return_value=claims):
            result = validator.validate_token("Bearer eyJ.eyJ.sig")
        assert result is None

    async def test_jwks_fetch_success(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        mock_client = AsyncMock()
        # OpenID config response
        openid_resp = MagicMock()
        openid_resp.status_code = 200
        openid_resp.json.return_value = {"jwks_uri": "https://login.botframework.com/v1/.well-known/keys"}
        openid_resp.raise_for_status = MagicMock()

        # JWKS response
        jwks_resp = MagicMock()
        jwks_resp.status_code = 200
        jwks_resp.json.return_value = {"keys": [{"kid": "key-1", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
        jwks_resp.raise_for_status = MagicMock()

        mock_client.get = AsyncMock(side_effect=[openid_resp, jwks_resp])

        await validator.fetch_jwks(mock_client)
        assert validator._jwks_available is True

    async def test_jwks_fetch_failure_marks_unavailable(self):
        from nobla.channels.teams.adapter import JWTValidator
        validator = JWTValidator("app-id")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        await validator.fetch_jwks(mock_client)
        assert validator._jwks_available is False


# ── Adapter Lifecycle ───────────────────────────────────────


@pytest.mark.asyncio
class TestTeamsAdapter:
    """TeamsAdapter lifecycle and ABC method tests."""

    def _make_settings(self, **overrides):
        settings = MagicMock()
        settings.app_id = overrides.get("app_id", "app-id")
        settings.app_password = overrides.get("app_password", "app-pass")
        settings.tenant_id = overrides.get("tenant_id", "")
        settings.webhook_path = overrides.get("webhook_path", "/webhook/teams")
        settings.group_activation = overrides.get("group_activation", "mention")
        settings.max_file_size_mb = overrides.get("max_file_size_mb", 100)
        settings.token_refresh_margin_seconds = overrides.get("token_refresh_margin_seconds", 300)
        return settings

    def _make_handlers(self):
        h = MagicMock()
        h.set_send_fn = MagicMock()
        h.handle_activity = AsyncMock()
        h.get_conversation_ref = MagicMock(return_value={
            "service_url": "https://smba.trafficmanager.net/teams/",
            "conversation_id": "conv-1",
        })
        return h

    async def test_name_property(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        assert adapter.name == "teams"

    async def test_start_initializes_client(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        with patch.object(adapter, "_fetch_jwks_background"):
            await adapter.start()
        assert adapter._client is not None
        assert adapter._running is True
        await adapter.stop()

    async def test_double_start_ignored(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        with patch.object(adapter, "_fetch_jwks_background"):
            await adapter.start()
            await adapter.start()  # Should not raise
        await adapter.stop()

    async def test_stop_cleanup(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        with patch.object(adapter, "_fetch_jwks_background"):
            await adapter.start()
        await adapter.stop()
        assert adapter._client is None
        assert adapter._running is False

    async def test_send_before_start(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        from nobla.channels.base import ChannelResponse
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        # Should not raise, just log error
        await adapter.send("user-1", ChannelResponse(content="hello"))

    async def test_parse_callback(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        action_id, meta = adapter.parse_callback({"action_id": "test:1:approve", "extra": "data"})
        assert action_id == "test:1:approve"

    async def test_parse_callback_string(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        action_id, meta = adapter.parse_callback("raw-string")
        assert action_id == "raw-string"

    async def test_health_check_no_client(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        result = await adapter.health_check()
        assert result is False

    async def test_health_check_with_token_and_jwks(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        adapter._running = True
        adapter._client = AsyncMock()
        adapter._token_manager = MagicMock()
        adapter._token_manager.has_valid_token = True
        adapter._jwt_validator = MagicMock()
        adapter._jwt_validator._jwks_available = True
        result = await adapter.health_check()
        assert result is True

    async def test_send_notification_uses_conversation_ref(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        handlers = self._make_handlers()
        adapter = TeamsAdapter(self._make_settings(), handlers)
        adapter._running = True
        adapter._client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        adapter._client.post = AsyncMock(return_value=mock_resp)
        adapter._token_manager = MagicMock()
        adapter._token_manager.get_token = AsyncMock(return_value="tok-1")

        await adapter.send_notification("user-1", "Hello!")
        handlers.get_conversation_ref.assert_called_with("user-1")

    async def test_handle_webhook_end_to_end(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        handlers = self._make_handlers()
        adapter = TeamsAdapter(self._make_settings(), handlers)
        adapter._running = True
        adapter._jwt_validator = MagicMock()
        adapter._jwt_validator.validate_token = MagicMock(return_value={"aud": "app-id"})

        body = json.dumps({"type": "message", "text": "hi"}).encode()
        result = await adapter.handle_webhook(body, "Bearer tok")
        assert result is not None
        handlers.handle_activity.assert_called_once()

    async def test_handle_webhook_invalid_jwt_rejected(self):
        from nobla.channels.teams.adapter import TeamsAdapter
        adapter = TeamsAdapter(self._make_settings(), self._make_handlers())
        adapter._running = True
        adapter._jwt_validator = MagicMock()
        adapter._jwt_validator.validate_token = MagicMock(return_value=None)

        body = json.dumps({"type": "message"}).encode()
        result = await adapter.handle_webhook(body, "Bearer bad")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTokenManager tests/test_teams_adapter.py::TestJWTValidation tests/test_teams_adapter.py::TestTeamsAdapter -v --no-header 2>&1 | head -20
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `adapter.py`**

```python
"""Microsoft Teams channel adapter with Bot Framework REST API (Phase 5-Channels).

Implements ``BaseChannelAdapter`` for Microsoft Teams.
  - Inbound: Webhook with JWT validation (OpenID Connect)
  - Outbound: REST API with OAuth2 client_credentials token

Authentication:
  - Inbound JWT validated against Microsoft's JWKS (RS256)
  - Outbound Bearer token from client_credentials grant (auto-refreshed)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.teams.formatter import format_response
from nobla.channels.teams.handlers import TeamsHandlers
from nobla.channels.teams.media import send_attachment
from nobla.channels.teams.models import (
    BOT_FRAMEWORK_OPENID_URL,
    BOT_FRAMEWORK_TOKEN_SCOPE,
    BOT_FRAMEWORK_TOKEN_URL,
)

logger = logging.getLogger(__name__)


# -- Token management ------------------------------------------------


class TokenManager:
    """OAuth2 client_credentials token manager for Bot Framework API.

    Caches token in memory and refreshes before expiry.
    Uses asyncio.Lock to prevent concurrent refresh storms.
    """

    def __init__(
        self,
        app_id: str,
        app_password: str,
        client: httpx.AsyncClient | Any,
        refresh_margin: int = 300,
    ) -> None:
        self._app_id = app_id
        self._app_password = app_password
        self._client = client
        self._refresh_margin = refresh_margin
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def has_valid_token(self) -> bool:
        return (
            self._token is not None
            and time.time() < self._expires_at - self._refresh_margin
        )

    async def get_token(self) -> str:
        """Return a valid token, refreshing if needed."""
        if self.has_valid_token:
            return self._token  # type: ignore[return-value]

        async with self._lock:
            # Double-check after acquiring lock
            if self.has_valid_token:
                return self._token  # type: ignore[return-value]
            return await self._refresh()

    async def _refresh(self) -> str:
        """Fetch a new token from the Microsoft token endpoint."""
        resp = await self._client.post(
            BOT_FRAMEWORK_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._app_id,
                "client_secret": self._app_password,
                "scope": BOT_FRAMEWORK_TOKEN_SCOPE,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._token


# -- JWT validation --------------------------------------------------


class JWTValidator:
    """Validates inbound JWT tokens from Bot Framework.

    Security-first: rejects ALL requests when JWKS is unavailable.
    """

    def __init__(self, app_id: str, tenant_id: str = "") -> None:
        self._app_id = app_id
        self._tenant_id = tenant_id
        self._jwks: dict[str, Any] = {}
        self._jwks_available = False
        self._jwks_fetched_at: float = 0.0

    async def fetch_jwks(self, client: httpx.AsyncClient) -> None:
        """Fetch JWKS from Microsoft's OpenID configuration."""
        try:
            # Step 1: Get OpenID config
            resp = await client.get(BOT_FRAMEWORK_OPENID_URL)
            resp.raise_for_status()
            config = resp.json()

            jwks_uri = config.get("jwks_uri", "")
            if not jwks_uri:
                logger.error("No jwks_uri in OpenID config")
                self._jwks_available = False
                return

            # Step 2: Fetch JWKS
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            self._jwks = resp.json()
            self._jwks_available = True
            self._jwks_fetched_at = time.time()
            logger.info(
                "JWKS fetched: %d keys", len(self._jwks.get("keys", []))
            )
        except Exception:
            logger.exception("Failed to fetch JWKS")
            self._jwks_available = False

    def validate_token(self, auth_header: str) -> dict[str, Any] | None:
        """Validate a JWT Bearer token. Returns claims dict or None."""
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        if not self._jwks_available:
            logger.warning("JWKS unavailable — rejecting request (503)")
            return None

        token = auth_header[7:]  # Strip "Bearer "

        try:
            claims = self._decode_and_verify(token)
        except Exception:
            logger.warning("JWT decode/verify failed")
            return None

        if not claims:
            return None

        # Validate standard claims
        now = time.time()

        # Check expiry
        if claims.get("exp", 0) < now:
            logger.warning("JWT expired")
            return None

        # Check audience
        if claims.get("aud") != self._app_id:
            logger.warning(
                "JWT audience mismatch: %s != %s",
                claims.get("aud"), self._app_id,
            )
            return None

        # Check issuer
        iss = claims.get("iss", "")
        if not iss.startswith("https://api.botframework.com"):
            logger.warning("JWT issuer invalid: %s", iss)
            return None

        # Tenant check (if configured)
        if self._tenant_id and claims.get("tid") != self._tenant_id:
            logger.warning(
                "JWT tenant mismatch: %s != %s",
                claims.get("tid"), self._tenant_id,
            )
            return None

        return claims

    def _decode_and_verify(self, token: str) -> dict[str, Any] | None:
        """Decode and verify a JWT against the cached JWKS.

        Uses PyJWT with RS256. Returns claims dict or None.
        """
        try:
            import jwt
            from jwt import PyJWKClient

            # Build a local JWKS client from cached keys
            jwk_client = PyJWKClient("")
            jwk_client.fetch_data = lambda: self._jwks  # type: ignore[assignment]

            # Get signing key from token header
            signing_key = jwk_client.get_signing_key_from_jwt(token)

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
                # We verify aud/iss manually for more control
            )
            return claims
        except Exception:
            logger.debug("JWT decode failed", exc_info=True)
            return None


# -- Teams adapter ---------------------------------------------------


class TeamsAdapter(BaseChannelAdapter):
    """Microsoft Teams adapter using Bot Framework REST API.

    Args:
        settings: Teams configuration (app_id, app_password, etc.).
        handlers: Pre-built ``TeamsHandlers`` with linking + event bus.
    """

    def __init__(
        self,
        settings: Any,
        handlers: TeamsHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._token_manager: TokenManager | None = None
        self._jwt_validator: JWTValidator | None = None
        self._jwks_task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return "teams"

    # -- Lifecycle ---------------------------------------------------

    async def start(self) -> None:
        """Initialize HTTP client, token manager, and JWKS cache."""
        if self._running:
            logger.warning("Teams adapter already running")
            return

        self._client = httpx.AsyncClient(timeout=30.0)

        # Initialize token manager
        self._token_manager = TokenManager(
            app_id=self._settings.app_id,
            app_password=self._settings.app_password,
            client=self._client,
            refresh_margin=self._settings.token_refresh_margin_seconds,
        )

        # Initialize JWT validator
        self._jwt_validator = JWTValidator(
            app_id=self._settings.app_id,
            tenant_id=self._settings.tenant_id,
        )

        # Wire handler's outbound send function
        self._handlers.set_send_fn(self._send_raw_text)

        self._running = True

        # Fetch JWKS in background (security-first: rejects until available)
        self._fetch_jwks_background()

        logger.info(
            "Teams adapter started (app_id=%s, tenant=%s)",
            self._settings.app_id,
            self._settings.tenant_id or "multi-tenant",
        )

    def _fetch_jwks_background(self) -> None:
        """Launch background task to fetch JWKS."""
        self._jwks_task = asyncio.create_task(self._jwks_fetch_loop())

    async def _jwks_fetch_loop(self) -> None:
        """Fetch JWKS with exponential backoff, then refresh periodically."""
        backoff = 1.0
        max_backoff = 60.0

        while self._running:
            try:
                if self._client and self._jwt_validator:
                    await self._jwt_validator.fetch_jwks(self._client)
                    if self._jwt_validator._jwks_available:
                        # Success — refresh every 24h
                        await asyncio.sleep(86400)
                        backoff = 1.0
                        continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("JWKS fetch loop error")

            # Backoff on failure
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def stop(self) -> None:
        """Gracefully shut down HTTP client and background tasks."""
        if not self._running:
            return

        if self._jwks_task and not self._jwks_task.done():
            self._jwks_task.cancel()
            try:
                await self._jwks_task
            except asyncio.CancelledError:
                pass
            self._jwks_task = None

        if self._client:
            await self._client.aclose()
            self._client = None

        self._token_manager = None
        self._jwt_validator = None
        self._running = False
        logger.info("Teams adapter stopped")

    # -- Webhook entry point -----------------------------------------

    async def handle_webhook(
        self, body: bytes, auth_header: str,
    ) -> dict[str, Any] | None:
        """Process an inbound webhook from Teams.

        Validates JWT, parses Activity, dispatches to handlers.
        Returns the parsed activity on success, None on auth failure.
        """
        if not self._jwt_validator:
            return None

        claims = self._jwt_validator.validate_token(auth_header)
        if not claims:
            return None

        try:
            activity = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid JSON in Teams webhook body")
            return None

        await self._handlers.handle_activity(activity)
        return activity

    # -- Outbound messaging ------------------------------------------

    async def send(
        self, channel_user_id: str, response: ChannelResponse,
    ) -> None:
        """Send a formatted response to a Teams conversation."""
        if not self._client or not self._token_manager:
            logger.error("Cannot send - client not initialized")
            return

        ref = self._handlers.get_conversation_ref(channel_user_id)
        if not ref:
            logger.warning("No conversation ref for %s", channel_user_id)
            return

        token = await self._token_manager.get_token()
        service_url = ref["service_url"]
        conversation_id = ref["conversation_id"]

        # Send attachments first
        for attachment in response.attachments:
            await send_attachment(
                service_url=service_url,
                conversation_id=conversation_id,
                attachment=attachment,
                bot_token=token,
                client=self._client,
            )

        # Format and send text + Adaptive Card
        if response.content:
            activity = format_response(response)
            await self._post_to_conversation(
                service_url, conversation_id, activity, token,
            )

    async def send_notification(
        self, channel_user_id: str, text: str,
    ) -> None:
        """Send a plain-text notification via proactive messaging."""
        await self._send_raw_text(channel_user_id, text)

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a Teams invoke Activity into (action_id, metadata)."""
        if isinstance(raw_callback, dict):
            action_id = raw_callback.get("action_id", "")
            return action_id, raw_callback
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check that token manager and JWKS are operational."""
        if not self._running or not self._client:
            return False

        token_ok = (
            self._token_manager is not None and self._token_manager.has_valid_token
        )
        jwks_ok = (
            self._jwt_validator is not None and self._jwt_validator._jwks_available
        )
        return token_ok and jwks_ok

    # -- Private helpers ---------------------------------------------

    async def _send_raw_text(
        self, channel_user_id: str, text: str,
    ) -> None:
        """Send a plain text message to a conversation."""
        if not self._client or not self._token_manager:
            logger.error("Cannot send - client not initialized")
            return

        ref = self._handlers.get_conversation_ref(channel_user_id)
        if not ref:
            logger.warning("No conversation ref for %s — cannot send", channel_user_id)
            return

        token = await self._token_manager.get_token()
        activity = {"type": "message", "text": text}
        await self._post_to_conversation(
            ref["service_url"], ref["conversation_id"], activity, token,
        )

    async def _post_to_conversation(
        self,
        service_url: str,
        conversation_id: str,
        activity: dict[str, Any],
        token: str,
    ) -> None:
        """POST an activity to the Bot Framework conversation endpoint."""
        if not self._client:
            return

        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        try:
            resp = await self._client.post(
                url,
                json=activity,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

            # Handle rate limiting
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                logger.warning(
                    "Teams rate limited, retry after %ds", retry_after,
                )
                await asyncio.sleep(retry_after)
                # Retry once
                resp = await self._client.post(
                    url,
                    json=activity,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

            resp.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to post activity to %s", conversation_id,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py::TestTokenManager tests/test_teams_adapter.py::TestJWTValidation tests/test_teams_adapter.py::TestTeamsAdapter -v --no-header
```

Expected: 35 PASSED (8 token + 15 JWT + 12 adapter)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/channels/teams/adapter.py backend/tests/test_teams_adapter.py
git commit -m "feat(5-channels): add Teams adapter with TokenManager and JWT validation"
```

---

### Task 6: Configuration & Lifespan Wiring

**Files:**
- Modify: `backend/nobla/config/settings.py` (lines 407 and 528)
- Modify: `backend/nobla/gateway/lifespan.py` (after line 255)

- [ ] **Step 1: Add TeamsSettings to settings.py**

Insert after `SignalSettings` (after line 406), before `SchedulerSettings`:

```python
class TeamsSettings(BaseModel):
    """Microsoft Teams adapter configuration (Phase 5-Channels)."""

    enabled: bool = False
    app_id: str = ""
    app_password: str = ""
    tenant_id: str = ""  # Empty = multi-tenant
    webhook_path: str = "/webhook/teams"
    group_activation: str = "mention"
    max_file_size_mb: int = 100
    token_refresh_margin_seconds: int = 300

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.enabled and not self.app_id:
            raise ValueError("app_id is required when Teams is enabled")
        if self.enabled and not self.app_password:
            raise ValueError("app_password is required when Teams is enabled")
        return self
```

Add field to `Settings` class after `signal` (line 528):

```python
    teams: TeamsSettings = Field(default_factory=TeamsSettings)
```

- [ ] **Step 2: Add Teams init block to lifespan.py**

Insert after the Signal adapter block (after line 255):

```python
    # --- Teams Adapter (Phase 5-Channels) ---
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
            logger.info("teams_adapter_started app_id=%s", settings.teams.app_id)
        except Exception:
            logger.exception("teams_adapter_start_failed")
    else:
        logger.info("teams_adapter_disabled")
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py -v --no-header
```

Expected: ~100 PASSED

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
cd backend && python -m pytest tests/ -v --no-header -q 2>&1 | tail -5
```

Expected: All existing tests still passing

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/gateway/lifespan.py
git commit -m "feat(5-channels): wire Teams adapter into settings and gateway lifespan"
```

---

### Task 7: Final Verification & Documentation

**Files:**
- Modify: `CLAUDE.md` (update phase status, test counts)

- [ ] **Step 1: Run full test suite one final time**

```bash
cd backend && python -m pytest tests/test_teams_adapter.py -v --tb=short 2>&1 | tail -10
```

Expected: ~100 PASSED, 0 FAILED

- [ ] **Step 2: Verify line counts (750-line limit)**

```bash
wc -l backend/nobla/channels/teams/*.py
```

Expected: All files under 750 lines

- [ ] **Step 3: Update CLAUDE.md**

Update test counts, phase status, and structure documentation to reflect the Teams adapter completion.

- [ ] **Step 4: Commit documentation update**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 5-Channels Teams adapter completion"
```
