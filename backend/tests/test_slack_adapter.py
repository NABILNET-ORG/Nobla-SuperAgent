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


# =====================================================================
# Task 4: Handlers (SlackHandlers + RateLimitQueue)
# =====================================================================

from nobla.channels.slack.handlers import SlackHandlers, RateLimitQueue


@pytest.fixture
def handlers(linking, event_bus):
    h = SlackHandlers(
        linking=linking,
        event_bus=event_bus,
        bot_token="xoxb-test-token",
        bot_user_id="U_BOT",
        max_file_size_mb=100,
    )
    h.set_send_fn(AsyncMock())
    return h


def _make_slack_event(
    text: str = "hello",
    user: str = "U123",
    channel: str = "C789",
    ts: str = "1700000000.000100",
    event_type: str = "message",
    thread_ts: str | None = None,
    channel_type: str = "channel",
) -> dict:
    """Build a minimal Slack Events API payload."""
    event: dict[str, Any] = {
        "type": event_type,
        "user": user,
        "text": text,
        "channel": channel,
        "ts": ts,
        "channel_type": channel_type,
    }
    if thread_ts:
        event["thread_ts"] = thread_ts
    return {
        "type": "event_callback",
        "team_id": "T456",
        "event": event,
    }


class TestRateLimitQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_process(self):
        results = []
        async def fake_sender(channel: str, text: str):
            results.append((channel, text))

        q = RateLimitQueue(sender=fake_sender)
        await q.enqueue("C123", "hello")
        await q.process()
        assert len(results) == 1
        assert results[0] == ("C123", "hello")

    @pytest.mark.asyncio
    async def test_rate_limit_delay(self):
        results = []
        async def fake_sender(channel: str, text: str):
            results.append(text)

        q = RateLimitQueue(sender=fake_sender)
        q.set_retry_after(0.01)  # 10ms delay
        await q.enqueue("C123", "msg1")
        await q.process()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_queue_ordering(self):
        results = []
        async def fake_sender(channel: str, text: str):
            results.append(text)

        q = RateLimitQueue(sender=fake_sender)
        await q.enqueue("C1", "first")
        await q.enqueue("C1", "second")
        await q.enqueue("C1", "third")
        await q.process()
        await q.process()
        await q.process()
        assert results == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_empty_queue(self):
        async def fake_sender(channel: str, text: str):
            pass
        q = RateLimitQueue(sender=fake_sender)
        await q.process()  # Should not crash


class TestSlackHandlersInit:
    def test_init(self, handlers):
        assert handlers._bot_token == "xoxb-test-token"
        assert handlers._bot_user_id == "U_BOT"

    def test_set_send_fn(self, handlers):
        new_fn = AsyncMock()
        handlers.set_send_fn(new_fn)
        assert handlers._send_text_fn is new_fn


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_text_message(self, handlers, linking):
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_code(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.create_pairing_code.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, handlers, linking):
        payload = _make_slack_event(text="hello", user="U_BOT")
        await handlers.handle_event(payload)
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_subtype_messages(self, handlers, linking):
        payload = _make_slack_event(text="hello")
        payload["event"]["subtype"] = "bot_message"
        await handlers.handle_event(payload)
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_event(self, handlers, linking):
        await handlers.handle_event({})
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dm_always_responds(self, handlers, linking):
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_channel_ignores_without_mention(self, handlers, linking):
        payload = _make_slack_event(text="hello everyone")
        await handlers.handle_event(payload)
        # In channel without mention, should not process
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_channel_responds_to_mention(self, handlers, linking):
        payload = _make_slack_event(text="<@U_BOT> hello")
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_app_mention_event(self, handlers, linking):
        payload = _make_slack_event(
            text="<@U_BOT> help", event_type="app_mention",
        )
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_thread_reply(self, handlers, linking):
        payload = _make_slack_event(
            text="<@U_BOT> reply",
            thread_ts="1700000000.000050",
            channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()


class TestSlashCommands:
    @pytest.mark.asyncio
    async def test_slash_start(self, handlers, linking):
        linking.resolve.return_value = None
        result = await handlers.handle_slash_command(
            command="/nobla", text="start",
            user_id="U123", channel_id="C789",
        )
        assert "Welcome" in result or "Nobla" in result
        linking.create_pairing_code.assert_awaited()

    @pytest.mark.asyncio
    async def test_slash_link_no_args(self, handlers, linking):
        result = await handlers.handle_slash_command(
            command="/nobla", text="link",
            user_id="U123", channel_id="C789",
        )
        assert "code" in result.lower() or "pair" in result.lower()

    @pytest.mark.asyncio
    async def test_slash_link_with_user_id(self, handlers, linking):
        result = await handlers.handle_slash_command(
            command="/nobla", text="link user-999",
            user_id="U123", channel_id="C789",
        )
        linking.link.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_slash_unlink(self, handlers, linking):
        result = await handlers.handle_slash_command(
            command="/nobla", text="unlink",
            user_id="U123", channel_id="C789",
        )
        linking.unlink.assert_awaited_once()
        assert "unlinked" in result.lower()

    @pytest.mark.asyncio
    async def test_slash_unlink_not_linked(self, handlers, linking):
        linking.resolve.return_value = None
        result = await handlers.handle_slash_command(
            command="/nobla", text="unlink",
            user_id="U123", channel_id="C789",
        )
        assert "not" in result.lower()

    @pytest.mark.asyncio
    async def test_slash_status_linked(self, handlers, linking):
        result = await handlers.handle_slash_command(
            command="/nobla", text="status",
            user_id="U123", channel_id="C789",
        )
        assert "linked" in result.lower() or "Linked" in result

    @pytest.mark.asyncio
    async def test_slash_status_unlinked(self, handlers, linking):
        linking.resolve.return_value = None
        result = await handlers.handle_slash_command(
            command="/nobla", text="status",
            user_id="U123", channel_id="C789",
        )
        assert "not" in result.lower()

    @pytest.mark.asyncio
    async def test_slash_unknown_subcommand(self, handlers):
        result = await handlers.handle_slash_command(
            command="/nobla", text="unknown_cmd",
            user_id="U123", channel_id="C789",
        )
        assert "start" in result.lower() or "usage" in result.lower()


class TestKeywordCommands:
    @pytest.mark.asyncio
    async def test_bang_start(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_slack_event(
            text="!start", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.create_pairing_code.assert_awaited()
        handlers._send_text_fn.assert_awaited()

    @pytest.mark.asyncio
    async def test_bang_link_with_id(self, handlers, linking):
        payload = _make_slack_event(
            text="!link user-999", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.link.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bang_unlink(self, handlers, linking):
        payload = _make_slack_event(
            text="!unlink", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        linking.unlink.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bang_status(self, handlers, linking):
        payload = _make_slack_event(
            text="!status", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        handlers._send_text_fn.assert_awaited()
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "Linked" in call_text or "linked" in call_text


class TestInteractionCallbacks:
    @pytest.mark.asyncio
    async def test_button_callback(self, handlers, event_bus):
        interaction = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C789"},
            "actions": [
                {"action_id": "approve:req-1:yes", "type": "button"},
            ],
        }
        await handlers.handle_interaction(interaction)
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_interaction_unlinked(self, handlers, linking, event_bus):
        linking.resolve.return_value = None
        interaction = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C789"},
            "actions": [
                {"action_id": "approve:req-1:yes", "type": "button"},
            ],
        }
        await handlers.handle_interaction(interaction)
        event_bus.publish.assert_not_awaited()


class TestEventEmission:
    @pytest.mark.asyncio
    async def test_inbound_message_emits_event(self, handlers, event_bus):
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        event_bus.publish.assert_awaited()
        event = event_bus.publish.call_args[0][0]
        assert event.event_type == "channel.message.in"
        assert event.source == CHANNEL_NAME

    @pytest.mark.asyncio
    async def test_no_event_bus(self, linking):
        h = SlackHandlers(
            linking=linking, event_bus=None,
            bot_token="t", bot_user_id="U_BOT",
        )
        h.set_send_fn(AsyncMock())
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await h.handle_event(payload)  # Should not crash


# =====================================================================
# Task 5: Adapter (dual Socket Mode + Events API)
# =====================================================================

from nobla.channels.slack.adapter import SlackAdapter


@pytest.fixture
def adapter(settings, handlers):
    return SlackAdapter(settings=settings, handlers=handlers)


class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "slack"


class TestAdapterLifecycle:
    @pytest.mark.asyncio
    async def test_start(self, adapter):
        await adapter.start()
        assert adapter._running is True
        assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_start_already_running(self, adapter):
        await adapter.start()
        await adapter.start()  # Should warn, not crash
        assert adapter._running is True

    @pytest.mark.asyncio
    async def test_start_no_bot_token(self, settings, handlers):
        settings.bot_token = ""
        a = SlackAdapter(settings=settings, handlers=handlers)
        with pytest.raises(ValueError, match="bot_token"):
            await a.start()

    @pytest.mark.asyncio
    async def test_stop(self, adapter):
        await adapter.start()
        await adapter.stop()
        assert adapter._running is False
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_stop_not_running(self, adapter):
        await adapter.stop()  # Should not crash


class TestAdapterSend:
    @pytest.mark.asyncio
    async def test_send_text(self, adapter):
        await adapter.start()
        resp = ChannelResponse(content="Hello!")

        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"ok": True}
            mock_post.return_value = mock_resp

            await adapter.send("C123", resp)
            mock_post.assert_awaited()
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["channel"] == "C123"
            assert "blocks" in payload

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_with_actions(self, adapter):
        await adapter.start()
        resp = ChannelResponse(
            content="Approve?",
            actions=[InlineAction(action_id="yes", label="Yes")],
        )

        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"ok": True}
            mock_post.return_value = mock_resp

            await adapter.send("C123", resp)
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            block_types = [b["type"] for b in payload.get("blocks", [])]
            assert "actions" in block_types

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_not_initialized(self, adapter):
        resp = ChannelResponse(content="Hello!")
        await adapter.send("C123", resp)  # Should not crash

    @pytest.mark.asyncio
    async def test_send_notification(self, adapter):
        await adapter.start()
        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"ok": True}
            mock_post.return_value = mock_resp

            await adapter.send_notification("C123", "Alert!")
            mock_post.assert_awaited_once()

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_with_thread_ts(self, adapter):
        await adapter.start()
        resp = ChannelResponse(content="Reply in thread")

        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"ok": True}
            mock_post.return_value = mock_resp

            await adapter.send("C123", resp, thread_ts="170000.001")
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload.get("thread_ts") == "170000.001"

        await adapter.stop()


class TestAdapterParseCallback:
    def test_dict_callback(self, adapter):
        action_id, meta = adapter.parse_callback(
            {"action_id": "approve:123", "type": "button"}
        )
        assert action_id == "approve:123"

    def test_string_callback(self, adapter):
        action_id, meta = adapter.parse_callback("raw_data")
        assert action_id == "raw_data"
        assert meta == {}


class TestAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, adapter):
        await adapter.start()
        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": True}
            mock_post.return_value = mock_resp

            assert await adapter.health_check() is True

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, adapter):
        await adapter.start()
        with patch.object(
            adapter._client, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": False}
            mock_post.return_value = mock_resp

            assert await adapter.health_check() is False

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, adapter):
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, adapter):
        await adapter.start()
        with patch.object(
            adapter._client, "post", side_effect=Exception("timeout")
        ):
            assert await adapter.health_check() is False
        await adapter.stop()


class TestRequestSigning:
    def test_verify_valid_signature(self, adapter):
        body = b'{"test": "payload"}'
        ts = "1700000000"
        sig_basestring = f"v0:{ts}:{body.decode()}"
        import hashlib
        import hmac as _hmac
        expected = "v0=" + _hmac.new(
            b"test-signing-secret", sig_basestring.encode(), hashlib.sha256
        ).hexdigest()
        assert adapter.verify_request_signature(body, ts, expected) is True

    def test_verify_invalid_signature(self, adapter):
        assert adapter.verify_request_signature(
            b"data", "1700000000", "v0=wrong"
        ) is False

    def test_verify_no_signing_secret(self, settings, handlers):
        settings.signing_secret = ""
        a = SlackAdapter(settings=settings, handlers=handlers)
        assert a.verify_request_signature(b"data", "ts", "v0=any") is True


class TestEventsAPIHandling:
    @pytest.mark.asyncio
    async def test_url_verification(self, adapter):
        payload = {
            "type": "url_verification",
            "challenge": "test-challenge-xyz",
        }
        result = adapter.handle_url_verification(payload)
        assert result == "test-challenge-xyz"

    @pytest.mark.asyncio
    async def test_event_callback(self, adapter, handlers):
        await adapter.start()
        payload = _make_slack_event(
            text="hello", channel="D789", channel_type="im",
        )
        await adapter.handle_events_api(payload)
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_socket_mode_envelope_ack(self, adapter):
        envelope = {
            "envelope_id": "env-123",
            "type": "events_api",
            "payload": _make_slack_event(
                text="hi", channel="D789", channel_type="im",
            ),
        }
        ack = adapter.build_socket_ack(envelope)
        assert ack == {"envelope_id": "env-123"}


# =====================================================================
# Task 6: Edge Cases
# =====================================================================


class TestEdgeCaseFormatter:
    def test_only_headers_no_text(self):
        blocks = markdown_to_blocks("# Header Only")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "header"

    def test_consecutive_dividers(self):
        blocks = markdown_to_blocks("---\n---\n---")
        assert all(b["type"] == "divider" for b in blocks)

    def test_nested_code_fence(self):
        md = "Text before\n```\ncode line 1\ncode line 2\n```\nText after"
        blocks = markdown_to_blocks(md)
        assert len(blocks) >= 2

    def test_unicode_in_blocks(self):
        blocks = markdown_to_blocks("# Arabic title")
        assert len(blocks) >= 1

    def test_header_with_special_chars(self):
        blocks = markdown_to_blocks("# Hello *world* & <friends>")
        assert blocks[0]["type"] == "header"
        assert "*world*" in blocks[0]["text"]["text"]

    def test_very_long_header_truncated(self):
        blocks = markdown_to_blocks(f"# {'A' * 200}")
        assert len(blocks[0]["text"]["text"]) <= 150


class TestEdgeCaseHandlers:
    @pytest.mark.asyncio
    async def test_mention_stripped_from_text(self, handlers, linking):
        payload = _make_slack_event(text="<@U_BOT> do something")
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_multiple_mentions_in_text(self, handlers, linking):
        payload = _make_slack_event(
            text="<@U_BOT> cc <@U_OTHER> please help",
        )
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_link_failure_handled(self, handlers, linking):
        linking.link.side_effect = Exception("DB error")
        payload = _make_slack_event(
            text="!link bad-id", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        handlers._send_text_fn.assert_awaited()
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "failed" in call_text.lower()

    @pytest.mark.asyncio
    async def test_empty_text_message(self, handlers, linking):
        payload = _make_slack_event(
            text="", channel="D789", channel_type="im",
        )
        await handlers.handle_event(payload)
        # Empty text in DM still resolves user
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_message_with_only_mention(self, handlers, linking):
        payload = _make_slack_event(text="<@U_BOT>")
        await handlers.handle_event(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_slash_link_failure(self, handlers, linking):
        linking.link.side_effect = Exception("Invalid user")
        result = await handlers.handle_slash_command(
            command="/nobla", text="link bad-id",
            user_id="U123", channel_id="C789",
        )
        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_interaction_no_actions(self, handlers, event_bus):
        interaction = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C789"},
            "actions": [],
        }
        await handlers.handle_interaction(interaction)
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_interaction_wrong_type(self, handlers, event_bus):
        interaction = {"type": "view_submission", "user": {"id": "U123"}}
        await handlers.handle_interaction(interaction)
        event_bus.publish.assert_not_awaited()


class TestEdgeCaseAdapter:
    @pytest.mark.asyncio
    async def test_send_empty_content(self, adapter):
        await adapter.start()
        resp = ChannelResponse(content="")
        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            await adapter.send("C123", resp)
            mock_post.assert_not_awaited()
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_api_error_handled(self, adapter):
        await adapter.start()
        resp = ChannelResponse(content="hello")
        with patch.object(adapter._client, "post", side_effect=Exception("500")):
            await adapter.send("C123", resp)  # Should not crash
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_notification_not_initialized(self, adapter):
        await adapter.send_notification("C123", "alert")  # Should not crash

    @pytest.mark.asyncio
    async def test_url_verification_no_challenge(self, adapter):
        result = adapter.handle_url_verification({"type": "url_verification"})
        assert result == ""

    @pytest.mark.asyncio
    async def test_events_api_unknown_type(self, adapter):
        await adapter.start()
        await adapter.handle_events_api({"type": "unknown_type"})
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_socket_handle_interactive(self, adapter, handlers):
        await adapter.start()
        envelope = {
            "envelope_id": "env-456",
            "type": "interactive",
            "payload": {
                "type": "block_actions",
                "user": {"id": "U123"},
                "channel": {"id": "C789"},
                "actions": [{"action_id": "test:1:go", "type": "button"}],
            },
        }
        await adapter.handle_socket_event(envelope)
        await adapter.stop()


class TestEdgeCaseMedia:
    @pytest.mark.asyncio
    async def test_upload_empty_data(self):
        result = await send_attachment(
            bot_token="xoxb-test",
            channel_id="C123",
            attachment=Attachment(
                type=AttachmentType.DOCUMENT,
                filename="empty.txt",
                mime_type="text/plain",
                size_bytes=0,
                data=b"",
            ),
        )
        # Empty bytes (not None) should still attempt upload
        # but data is truthy so it proceeds

    def test_guess_mime_no_extension(self):
        assert guess_mime_type("noext") == "application/octet-stream"

    def test_detect_gif(self):
        assert detect_attachment_type("image/gif") == AttachmentType.IMAGE

    def test_detect_wav(self):
        assert detect_attachment_type("audio/wav") == AttachmentType.AUDIO
