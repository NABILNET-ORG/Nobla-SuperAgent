"""Tests for the Slack channel adapter (Phase 5-Channels).

Covers: models/constants, Block Kit formatter, media (v2 upload),
handlers (rate-limit queue, slash/keyword commands, threads, channel policy),
adapter (dual Socket Mode + Events API), and edge cases.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    ChannelResponse,
    InlineAction,
)
from nobla.channels.slack.models import (
    CHANNEL_NAME,
    MAX_ACTIONS,
    MAX_BLOCKS,
    MAX_MESSAGE_LENGTH,
    SLACK_API_BASE,
    SlackUserContext,
    SUPPORTED_EVENT_TYPES,
)


# -- Fixtures --------------------------------------------------------


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


@dataclass
class FakeSlackSettings:
    enabled: bool = True
    bot_token: str = "xoxb-test-token"
    app_token: str = "xapp-test-app-token"
    signing_secret: str = "test-signing-secret"
    bot_user_id: str = "U_BOT"
    webhook_path: str = "/webhook/slack"
    socket_mode: bool = True
    max_file_size_mb: int = 100
    download_timeout: int = 30


@pytest.fixture
def settings():
    return FakeSlackSettings()


@pytest.fixture
def linking():
    svc = AsyncMock()
    svc.resolve = AsyncMock(return_value=FakeLinkedUser())
    svc.create_pairing_code = AsyncMock(return_value="ABC123")
    svc.link = AsyncMock()
    svc.unlink = AsyncMock()
    return svc


@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


# =====================================================================
# Task 1: Models
# =====================================================================


class TestSlackUserContext:
    def test_basic_properties(self):
        ctx = SlackUserContext(
            user_id="U123", display_name="Alice",
            team_id="T456", channel_id="C789",
            message_ts="1700000000.000100",
        )
        assert ctx.user_id_str == "U123"
        assert ctx.channel_id_str == "C789"
        assert ctx.display_name == "Alice"
        assert ctx.is_dm is False
        assert ctx.is_thread is False

    def test_dm_context(self):
        ctx = SlackUserContext(
            user_id="U123", display_name="Bob",
            team_id="T456", channel_id="D789",
            message_ts="1700000000.000100",
            is_dm=True,
        )
        assert ctx.is_dm is True

    def test_thread_context(self):
        ctx = SlackUserContext(
            user_id="U123", display_name="Eve",
            team_id="T456", channel_id="C789",
            message_ts="1700000000.000100",
            thread_ts="1700000000.000050",
            is_thread=True,
        )
        assert ctx.is_thread is True
        assert ctx.thread_ts == "1700000000.000050"

    def test_raw_extras(self):
        ctx = SlackUserContext(
            user_id="U123", display_name="Dan",
            team_id="T456", channel_id="C789",
            message_ts="1700000000.000100",
            raw_extras={"key": "value"},
        )
        assert ctx.raw_extras == {"key": "value"}

    def test_bot_mentioned(self):
        ctx = SlackUserContext(
            user_id="U123", display_name="Fay",
            team_id="T456", channel_id="C789",
            message_ts="1700000000.000100",
            is_bot_mentioned=True,
        )
        assert ctx.is_bot_mentioned is True


class TestConstants:
    def test_channel_name(self):
        assert CHANNEL_NAME == "slack"

    def test_supported_event_types(self):
        assert "message" in SUPPORTED_EVENT_TYPES
        assert "app_mention" in SUPPORTED_EVENT_TYPES
        assert "message.channels" not in SUPPORTED_EVENT_TYPES

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 4000

    def test_max_blocks(self):
        assert MAX_BLOCKS == 50

    def test_max_actions(self):
        assert MAX_ACTIONS == 5

    def test_slack_api_base(self):
        assert SLACK_API_BASE == "https://slack.com/api"


# =====================================================================
# Task 2: Formatter (Block Kit)
# =====================================================================

from nobla.channels.slack.formatter import (
    markdown_to_blocks,
    split_message,
    build_actions_block,
    format_response,
)


class TestSplitMessage:
    def test_short_message(self):
        assert split_message("hello") == ["hello"]

    def test_exact_limit(self):
        msg = "x" * MAX_MESSAGE_LENGTH
        assert split_message(msg) == [msg]

    def test_splits_at_newline(self):
        msg = "a" * 2000 + "\n" + "b" * 2000 + "\n" + "c" * 200
        chunks = split_message(msg, limit=2500)
        assert len(chunks) >= 2
        assert all(len(c) <= 2500 for c in chunks)

    def test_splits_at_space(self):
        msg = "word " * 1000
        chunks = split_message(msg, limit=100)
        assert all(len(c) <= 100 for c in chunks)

    def test_hard_cut(self):
        msg = "a" * 5000
        chunks = split_message(msg, limit=2000)
        assert len(chunks) == 3
        assert chunks[0] == "a" * 2000

    def test_empty_string(self):
        assert split_message("") == [""]


class TestMarkdownToBlocks:
    def test_plain_text(self):
        blocks = markdown_to_blocks("Hello world")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "section"
        assert "Hello world" in blocks[0]["text"]["text"]

    def test_header_conversion(self):
        blocks = markdown_to_blocks("# My Header\nSome text")
        types = [b["type"] for b in blocks]
        assert "header" in types

    def test_h2_header(self):
        blocks = markdown_to_blocks("## Sub Header\nMore text")
        types = [b["type"] for b in blocks]
        assert "header" in types

    def test_code_block(self):
        blocks = markdown_to_blocks("```python\nprint('hi')\n```")
        # Code blocks become section blocks with code formatting
        found = False
        for b in blocks:
            if b["type"] == "section":
                text = b["text"]["text"]
                if "```" in text:
                    found = True
        assert found

    def test_divider(self):
        blocks = markdown_to_blocks("above\n---\nbelow")
        types = [b["type"] for b in blocks]
        assert "divider" in types

    def test_mixed_content(self):
        md = "# Title\nSome *bold* text\n---\n## Section\nMore text"
        blocks = markdown_to_blocks(md)
        assert len(blocks) >= 3

    def test_empty_text(self):
        blocks = markdown_to_blocks("")
        assert blocks == []

    def test_block_limit(self):
        # Create content that would produce many blocks
        md = "\n".join(f"# Header {i}" for i in range(60))
        blocks = markdown_to_blocks(md)
        assert len(blocks) <= MAX_BLOCKS

    def test_bullet_list(self):
        md = "Items:\n- First\n- Second\n- Third"
        blocks = markdown_to_blocks(md)
        assert len(blocks) >= 1


class TestBuildActionsBlock:
    def test_basic_buttons(self):
        actions = [
            InlineAction(action_id="approve", label="Approve", style="primary"),
            InlineAction(action_id="deny", label="Deny", style="danger"),
        ]
        block = build_actions_block(actions)
        assert block["type"] == "actions"
        assert len(block["elements"]) == 2
        assert block["elements"][0]["action_id"] == "approve"
        assert block["elements"][0]["text"]["text"] == "Approve"

    def test_max_actions_capped(self):
        actions = [
            InlineAction(action_id=f"btn{i}", label=f"Btn {i}")
            for i in range(8)
        ]
        block = build_actions_block(actions)
        assert len(block["elements"]) == MAX_ACTIONS

    def test_style_mapping(self):
        actions = [
            InlineAction(action_id="ok", label="OK", style="primary"),
            InlineAction(action_id="rm", label="Delete", style="danger"),
            InlineAction(action_id="skip", label="Skip", style="secondary"),
        ]
        block = build_actions_block(actions)
        assert block["elements"][0].get("style") == "primary"
        assert block["elements"][1].get("style") == "danger"
        # secondary has no style in Slack Block Kit
        assert "style" not in block["elements"][2]

    def test_empty_actions(self):
        block = build_actions_block([])
        assert block["type"] == "actions"
        assert block["elements"] == []

    def test_long_label_truncated(self):
        actions = [InlineAction(action_id="x", label="A" * 100)]
        block = build_actions_block(actions)
        assert len(block["elements"][0]["text"]["text"]) <= 75


class TestFormatResponse:
    def test_simple_text(self):
        resp = ChannelResponse(content="Hello!")
        result = format_response(resp)
        assert result["text"] == "Hello!"
        assert "blocks" in result
        assert len(result["blocks"]) >= 1

    def test_empty_content(self):
        resp = ChannelResponse(content="")
        result = format_response(resp)
        assert result["text"] == ""
        assert result["blocks"] == []

    def test_with_actions(self):
        resp = ChannelResponse(
            content="Approve?",
            actions=[
                InlineAction(action_id="yes", label="Yes"),
                InlineAction(action_id="no", label="No"),
            ],
        )
        result = format_response(resp)
        types = [b["type"] for b in result["blocks"]]
        assert "actions" in types

    def test_long_text_split(self):
        resp = ChannelResponse(content="x" * 5000)
        result = format_response(resp)
        # Should have fallback text truncated
        assert len(result["text"]) <= MAX_MESSAGE_LENGTH

    def test_markdown_headers_in_blocks(self):
        resp = ChannelResponse(content="# Title\nBody text")
        result = format_response(resp)
        types = [b["type"] for b in result["blocks"]]
        assert "header" in types


# =====================================================================
# Task 3: Media (v2 upload pipeline)
# =====================================================================

from nobla.channels.slack.media import (
    detect_attachment_type,
    guess_mime_type,
    upload_file_v2,
    download_file,
    send_attachment,
)


class TestSlackDetectAttachmentType:
    def test_image_types(self):
        assert detect_attachment_type("image/jpeg") == AttachmentType.IMAGE
        assert detect_attachment_type("image/png") == AttachmentType.IMAGE

    def test_audio_types(self):
        assert detect_attachment_type("audio/ogg") == AttachmentType.AUDIO
        assert detect_attachment_type("audio/mpeg") == AttachmentType.AUDIO

    def test_video_types(self):
        assert detect_attachment_type("video/mp4") == AttachmentType.VIDEO

    def test_document_types(self):
        assert detect_attachment_type("application/pdf") == AttachmentType.DOCUMENT
        assert detect_attachment_type("text/plain") == AttachmentType.DOCUMENT

    def test_unknown_defaults_to_document(self):
        assert detect_attachment_type("application/x-unknown") == AttachmentType.DOCUMENT


class TestSlackGuessMimeType:
    def test_known_extension(self):
        assert guess_mime_type("photo.jpg") in ("image/jpeg",)
        assert guess_mime_type("doc.pdf") == "application/pdf"

    def test_unknown_extension(self):
        assert guess_mime_type("file.xyz123") == "application/octet-stream"


class TestUploadFileV2:
    @pytest.mark.asyncio
    async def test_upload_success(self):
        mock_client = AsyncMock()
        # Step 1: get upload URL
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.raise_for_status = MagicMock()
        mock_resp1.json.return_value = {
            "ok": True,
            "upload_url": "https://files.slack.com/upload/v2/abc",
            "file_id": "F_TEST",
        }
        # Step 2: upload file content
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.raise_for_status = MagicMock()
        # Step 3: complete upload
        mock_resp3 = MagicMock()
        mock_resp3.status_code = 200
        mock_resp3.raise_for_status = MagicMock()
        mock_resp3.json.return_value = {"ok": True}

        mock_client.post = AsyncMock(side_effect=[mock_resp1, mock_resp2, mock_resp3])

        file_id = await upload_file_v2(
            bot_token="xoxb-test",
            data=b"file-content",
            filename="test.txt",
            channel_id="C123",
            client=mock_client,
        )
        assert file_id == "F_TEST"
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_upload_get_url_fails(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "not_authed"}
        mock_client.post = AsyncMock(return_value=mock_resp)

        file_id = await upload_file_v2(
            bot_token="xoxb-bad",
            data=b"data",
            filename="f.txt",
            channel_id="C123",
            client=mock_client,
        )
        assert file_id is None

    @pytest.mark.asyncio
    async def test_upload_exception(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        file_id = await upload_file_v2(
            bot_token="xoxb-test",
            data=b"data",
            filename="f.txt",
            channel_id="C123",
            client=mock_client,
        )
        assert file_id is None


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_download_success(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"file-bytes"
        mock_client.get = AsyncMock(return_value=mock_resp)

        data = await download_file(
            url="https://files.slack.com/file.jpg",
            bot_token="xoxb-test",
            client=mock_client,
        )
        assert data == b"file-bytes"

    @pytest.mark.asyncio
    async def test_download_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        data = await download_file(
            url="https://files.slack.com/file.jpg",
            bot_token="xoxb-test",
            client=mock_client,
        )
        assert data is None

    @pytest.mark.asyncio
    async def test_download_too_large(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"x" * 200
        mock_client.get = AsyncMock(return_value=mock_resp)

        data = await download_file(
            url="https://files.slack.com/file.jpg",
            bot_token="xoxb-test",
            client=mock_client,
            max_size_bytes=100,
        )
        assert data is None


class TestSendAttachment:
    @pytest.mark.asyncio
    async def test_send_success(self):
        mock_client = AsyncMock()
        # upload_file_v2 responses (3 calls)
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.raise_for_status = MagicMock()
        mock_resp1.json.return_value = {
            "ok": True,
            "upload_url": "https://files.slack.com/upload/v2/abc",
            "file_id": "F_TEST",
        }
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.raise_for_status = MagicMock()
        mock_resp3 = MagicMock()
        mock_resp3.status_code = 200
        mock_resp3.raise_for_status = MagicMock()
        mock_resp3.json.return_value = {"ok": True}
        mock_client.post = AsyncMock(side_effect=[mock_resp1, mock_resp2, mock_resp3])

        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="photo.jpg",
            mime_type="image/jpeg",
            size_bytes=1024,
            data=b"fake-image",
        )
        result = await send_attachment(
            bot_token="xoxb-test",
            channel_id="C123",
            attachment=attachment,
            client=mock_client,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_no_data(self):
        attachment = Attachment(
            type=AttachmentType.IMAGE,
            filename="photo.jpg",
            mime_type="image/jpeg",
            size_bytes=0,
            data=None,
        )
        result = await send_attachment(
            bot_token="xoxb-test",
            channel_id="C123",
            attachment=attachment,
        )
        assert result is False
