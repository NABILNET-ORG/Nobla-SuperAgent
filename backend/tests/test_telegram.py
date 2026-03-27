"""Tests for the Telegram channel adapter (Phase 5A).

Covers: TelegramSettings, models, formatter, media handler, handlers, adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    ChannelMessage,
    ChannelResponse,
    InlineAction,
)
from nobla.channels.linking import UserLinkingService
from nobla.channels.telegram.formatter import (
    FormattedMessage,
    build_inline_keyboard,
    escape_markdown_v2,
    format_response,
    split_message,
)
from nobla.channels.telegram.media import (
    detect_attachment_type,
    extract_file_info,
    select_send_method,
)
from nobla.channels.telegram.models import (
    MAX_CAPTION_LENGTH,
    MAX_MESSAGE_LENGTH,
    MIME_TO_SEND_METHOD,
    TelegramUserContext,
)
from nobla.config.settings import TelegramSettings
from nobla.events.bus import NoblaEventBus


# ══════════════════════════════════════════════════════════
# TelegramSettings
# ══════════════════════════════════════════════════════════


class TestTelegramSettings:
    """TelegramSettings validation."""

    def test_defaults(self):
        s = TelegramSettings()
        assert s.enabled is False
        assert s.bot_token == ""
        assert s.mode == "polling"
        assert s.webhook_url is None
        assert s.group_activation == "mention"
        assert s.max_file_size_mb == 50
        assert s.rate_limit_per_second == 30

    def test_polling_mode_no_webhook_url_ok(self):
        s = TelegramSettings(mode="polling", bot_token="tok")
        assert s.mode == "polling"

    def test_webhook_mode_requires_url(self):
        with pytest.raises(ValueError, match="webhook_url is required"):
            TelegramSettings(mode="webhook", bot_token="tok")

    def test_webhook_mode_with_url_ok(self):
        s = TelegramSettings(
            mode="webhook",
            bot_token="tok",
            webhook_url="https://example.com",
        )
        assert s.webhook_url == "https://example.com"

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError, match="must be 'polling' or 'webhook'"):
            TelegramSettings(mode="invalid", bot_token="tok")

    def test_allowed_updates_default(self):
        s = TelegramSettings()
        assert "message" in s.allowed_updates
        assert "callback_query" in s.allowed_updates

    def test_webhook_path_default(self):
        s = TelegramSettings()
        assert s.webhook_path == "/webhook/telegram"


# ══════════════════════════════════════════════════════════
# TelegramUserContext
# ══════════════════════════════════════════════════════════


class TestTelegramUserContext:
    """TelegramUserContext model."""

    def test_basic_fields(self):
        ctx = TelegramUserContext(chat_id=123, user_id=456)
        assert ctx.chat_id == 123
        assert ctx.user_id == 456
        assert ctx.username is None
        assert ctx.is_group is False

    def test_str_properties(self):
        ctx = TelegramUserContext(chat_id=123, user_id=456)
        assert ctx.chat_id_str == "123"
        assert ctx.user_id_str == "456"

    def test_group_flags(self):
        ctx = TelegramUserContext(
            chat_id=123, user_id=456,
            is_group=True, is_bot_mentioned=True,
        )
        assert ctx.is_group is True
        assert ctx.is_bot_mentioned is True
        assert ctx.is_reply_to_bot is False

    def test_raw_extras_default(self):
        ctx = TelegramUserContext(chat_id=1, user_id=2)
        assert ctx.raw_extras == {}


# ══════════════════════════════════════════════════════════
# Formatter — escape_markdown_v2
# ══════════════════════════════════════════════════════════


class TestEscapeMarkdownV2:
    """MarkdownV2 character escaping."""

    def test_plain_text_unchanged(self):
        assert escape_markdown_v2("hello world") == "hello world"

    def test_special_chars_escaped(self):
        result = escape_markdown_v2("price is $5.00!")
        assert "\\." in result
        assert "\\!" in result

    def test_underscores_escaped(self):
        result = escape_markdown_v2("hello_world")
        assert result == "hello\\_world"

    def test_brackets_escaped(self):
        result = escape_markdown_v2("[link](url)")
        assert "\\[" in result
        assert "\\]" in result

    def test_code_block_preserved(self):
        text = "text ```code_block``` more"
        result = escape_markdown_v2(text)
        assert "```code_block```" in result
        assert "text" in result

    def test_inline_code_preserved(self):
        text = "use `my_func()` here"
        result = escape_markdown_v2(text)
        assert "`my_func()`" in result

    def test_hash_escaped(self):
        result = escape_markdown_v2("# heading")
        assert "\\#" in result

    def test_plus_escaped(self):
        result = escape_markdown_v2("a+b")
        assert "\\+" in result

    def test_empty_string(self):
        assert escape_markdown_v2("") == ""

    def test_mixed_code_and_text(self):
        text = "hello_world ```code_here``` goodbye_world"
        result = escape_markdown_v2(text)
        assert "hello\\_world" in result
        assert "```code_here```" in result
        assert "goodbye\\_world" in result


# ══════════════════════════════════════════════════════════
# Formatter — split_message
# ══════════════════════════════════════════════════════════


class TestSplitMessage:
    """Message splitting for Telegram's 4096 char limit."""

    def test_short_message_single_chunk(self):
        result = split_message("hello", limit=4096)
        assert result == ["hello"]

    def test_exactly_at_limit(self):
        text = "a" * 4096
        result = split_message(text, limit=4096)
        assert len(result) == 1

    def test_splits_on_paragraph_boundary(self):
        text = "para one\n\npara two"
        result = split_message(text, limit=12)
        assert len(result) == 2
        assert result[0] == "para one"

    def test_splits_on_newline(self):
        text = "line one\nline two"
        result = split_message(text, limit=12)
        assert len(result) == 2

    def test_splits_on_sentence(self):
        text = "First sentence. Second sentence."
        result = split_message(text, limit=20)
        assert len(result) >= 2

    def test_hard_cut_when_no_boundary(self):
        text = "a" * 100
        result = split_message(text, limit=30)
        assert all(len(chunk) <= 30 for chunk in result)

    def test_empty_string(self):
        result = split_message("")
        assert result == [""]

    def test_multiple_paragraphs(self):
        text = "a" * 50 + "\n\n" + "b" * 50 + "\n\n" + "c" * 50
        result = split_message(text, limit=60)
        assert len(result) == 3


# ══════════════════════════════════════════════════════════
# Formatter — build_inline_keyboard
# ══════════════════════════════════════════════════════════


class TestBuildInlineKeyboard:
    """InlineAction → Telegram keyboard conversion."""

    def test_none_actions_returns_none(self):
        assert build_inline_keyboard(None) is None

    def test_empty_actions_returns_none(self):
        assert build_inline_keyboard([]) is None

    def test_single_button(self):
        actions = [InlineAction(action_id="test:1:approve", label="Approve")]
        result = build_inline_keyboard(actions)
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0]["text"] == "Approve"
        assert result[0][0]["callback_data"] == "test:1:approve"

    def test_three_buttons_one_row(self):
        actions = [
            InlineAction(action_id=f"a:{i}:go", label=f"Btn{i}")
            for i in range(3)
        ]
        result = build_inline_keyboard(actions)
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_four_buttons_two_rows(self):
        actions = [
            InlineAction(action_id=f"a:{i}:go", label=f"Btn{i}")
            for i in range(4)
        ]
        result = build_inline_keyboard(actions)
        assert len(result) == 2
        assert len(result[0]) == 3
        assert len(result[1]) == 1

    def test_six_buttons_two_full_rows(self):
        actions = [
            InlineAction(action_id=f"a:{i}:go", label=f"Btn{i}")
            for i in range(6)
        ]
        result = build_inline_keyboard(actions)
        assert len(result) == 2
        assert all(len(row) == 3 for row in result)


# ══════════════════════════════════════════════════════════
# Formatter — format_response
# ══════════════════════════════════════════════════════════


class TestFormatResponse:
    """Full response formatting pipeline."""

    def test_simple_text(self):
        resp = ChannelResponse(content="hello")
        result = format_response(resp)
        assert len(result) == 1
        assert result[0].parse_mode == "MarkdownV2"

    def test_keyboard_on_last_chunk_only(self):
        long_text = "a" * 5000
        actions = [InlineAction(action_id="t:1:ok", label="OK")]
        resp = ChannelResponse(content=long_text, actions=actions)
        result = format_response(resp)
        assert len(result) >= 2
        assert result[-1].reply_markup is not None
        for msg in result[:-1]:
            assert msg.reply_markup is None

    def test_no_actions_no_keyboard(self):
        resp = ChannelResponse(content="hi")
        result = format_response(resp)
        assert result[0].reply_markup is None

    def test_special_chars_escaped(self):
        resp = ChannelResponse(content="price: $5.00!")
        result = format_response(resp)
        assert "\\." in result[0].text


# ══════════════════════════════════════════════════════════
# Media — detect_attachment_type
# ══════════════════════════════════════════════════════════


class TestDetectAttachmentType:
    """MIME → AttachmentType mapping."""

    def test_image_jpeg(self):
        assert detect_attachment_type("image/jpeg") == AttachmentType.IMAGE

    def test_image_png(self):
        assert detect_attachment_type("image/png") == AttachmentType.IMAGE

    def test_audio_mpeg(self):
        assert detect_attachment_type("audio/mpeg") == AttachmentType.AUDIO

    def test_audio_ogg(self):
        assert detect_attachment_type("audio/ogg") == AttachmentType.AUDIO

    def test_video_mp4(self):
        assert detect_attachment_type("video/mp4") == AttachmentType.VIDEO

    def test_unknown_mime_is_document(self):
        assert detect_attachment_type("application/pdf") == AttachmentType.DOCUMENT

    def test_octet_stream_is_document(self):
        assert detect_attachment_type("application/octet-stream") == AttachmentType.DOCUMENT


# ══════════════════════════════════════════════════════════
# Media — select_send_method
# ══════════════════════════════════════════════════════════


class TestSelectSendMethod:
    """send_* method selection for outbound attachments."""

    def test_jpeg_sends_photo(self):
        att = Attachment(
            type=AttachmentType.IMAGE, filename="x.jpg",
            mime_type="image/jpeg", size_bytes=100,
        )
        assert select_send_method(att) == "send_photo"

    def test_mp3_sends_audio(self):
        att = Attachment(
            type=AttachmentType.AUDIO, filename="x.mp3",
            mime_type="audio/mpeg", size_bytes=100,
        )
        assert select_send_method(att) == "send_audio"

    def test_ogg_sends_voice(self):
        att = Attachment(
            type=AttachmentType.AUDIO, filename="x.ogg",
            mime_type="audio/ogg", size_bytes=100,
        )
        assert select_send_method(att) == "send_voice"

    def test_mp4_sends_video(self):
        att = Attachment(
            type=AttachmentType.VIDEO, filename="x.mp4",
            mime_type="video/mp4", size_bytes=100,
        )
        assert select_send_method(att) == "send_video"

    def test_gif_sends_animation(self):
        att = Attachment(
            type=AttachmentType.IMAGE, filename="x.gif",
            mime_type="image/gif", size_bytes=100,
        )
        assert select_send_method(att) == "send_animation"

    def test_pdf_sends_document(self):
        att = Attachment(
            type=AttachmentType.DOCUMENT, filename="x.pdf",
            mime_type="application/pdf", size_bytes=100,
        )
        assert select_send_method(att) == "send_document"

    def test_unknown_mime_falls_back_to_type(self):
        att = Attachment(
            type=AttachmentType.IMAGE, filename="x.tiff",
            mime_type="image/tiff", size_bytes=100,
        )
        # image/tiff not in MIME_TO_SEND_METHOD, falls back to type → send_photo
        assert select_send_method(att) == "send_photo"


# ══════════════════════════════════════════════════════════
# Media — extract_file_info
# ══════════════════════════════════════════════════════════


def _make_mock_message(**kwargs) -> MagicMock:
    """Build a mock Telegram Message with specified media."""
    msg = MagicMock()
    msg.photo = kwargs.get("photo", None)
    msg.audio = kwargs.get("audio", None)
    msg.voice = kwargs.get("voice", None)
    msg.video = kwargs.get("video", None)
    msg.video_note = kwargs.get("video_note", None)
    msg.animation = kwargs.get("animation", None)
    msg.document = kwargs.get("document", None)
    return msg


class TestExtractFileInfo:
    """Extract downloadable file metadata from Telegram messages."""

    def test_no_media_returns_empty(self):
        msg = _make_mock_message()
        assert extract_file_info(msg) == []

    def test_photo_extracts_largest(self):
        small = MagicMock(file_id="s1", file_unique_id="u1", file_size=100)
        large = MagicMock(file_id="s2", file_unique_id="u2", file_size=5000)
        msg = _make_mock_message(photo=[small, large])
        result = extract_file_info(msg)
        assert len(result) == 1
        assert result[0]["file_id"] == "s2"
        assert result[0]["mime_type"] == "image/jpeg"

    def test_audio_extraction(self):
        audio = MagicMock(
            file_id="a1", file_name="song.mp3",
            mime_type="audio/mpeg", file_size=3000,
        )
        msg = _make_mock_message(audio=audio)
        result = extract_file_info(msg)
        assert len(result) == 1
        assert result[0]["filename"] == "song.mp3"

    def test_voice_extraction(self):
        voice = MagicMock(
            file_id="v1", mime_type="audio/ogg", file_size=800,
        )
        msg = _make_mock_message(voice=voice)
        result = extract_file_info(msg)
        assert result[0]["filename"] == "voice.ogg"

    def test_video_extraction(self):
        video = MagicMock(
            file_id="vid1", file_name="clip.mp4",
            mime_type="video/mp4", file_size=10000,
        )
        msg = _make_mock_message(video=video)
        result = extract_file_info(msg)
        assert result[0]["mime_type"] == "video/mp4"

    def test_document_extraction(self):
        doc = MagicMock(
            file_id="d1", file_name="report.pdf",
            mime_type="application/pdf", file_size=2000,
        )
        msg = _make_mock_message(document=doc)
        result = extract_file_info(msg)
        assert result[0]["filename"] == "report.pdf"

    def test_multiple_media_types(self):
        photo = [MagicMock(file_id="p", file_unique_id="u", file_size=100)]
        doc = MagicMock(
            file_id="d", file_name="f.txt",
            mime_type="text/plain", file_size=50,
        )
        msg = _make_mock_message(photo=photo, document=doc)
        result = extract_file_info(msg)
        assert len(result) == 2

    def test_audio_defaults(self):
        audio = MagicMock(
            file_id="a1", file_name=None,
            mime_type=None, file_size=100,
        )
        msg = _make_mock_message(audio=audio)
        result = extract_file_info(msg)
        assert result[0]["filename"] == "audio.mp3"
        assert result[0]["mime_type"] == "audio/mpeg"


# ══════════════════════════════════════════════════════════
# Handlers — context extraction and group logic
# ══════════════════════════════════════════════════════════


from nobla.channels.telegram.handlers import (
    TelegramHandlers,
    extract_user_context,
    should_process_group_message,
    strip_bot_mention,
)


def _make_update(
    text: str = "hello",
    user_id: int = 100,
    chat_id: int = 200,
    chat_type: str = "private",
    username: str = "testuser",
    bot_username: str | None = None,
    is_reply_to_bot: bool = False,
    message_id: int = 1,
) -> MagicMock:
    """Build a mock Telegram Update."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = "Test"
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.effective_message.text = text
    update.effective_message.caption = None
    update.effective_message.message_id = message_id
    update.effective_message.reply_to_message = None
    update.effective_message.reply_text = AsyncMock()

    if is_reply_to_bot and bot_username:
        reply_msg = MagicMock()
        reply_msg.from_user.username = bot_username
        update.effective_message.reply_to_message = reply_msg

    return update


class TestExtractUserContext:
    """extract_user_context from Telegram Update."""

    def test_private_chat(self):
        update = _make_update()
        ctx = extract_user_context(update)
        assert ctx is not None
        assert ctx.chat_id == 200
        assert ctx.user_id == 100
        assert ctx.is_group is False

    def test_group_chat(self):
        update = _make_update(chat_type="supergroup")
        ctx = extract_user_context(update)
        assert ctx.is_group is True

    def test_mention_detected(self):
        update = _make_update(
            text="@NoblaBot hello",
            chat_type="group",
        )
        ctx = extract_user_context(update, bot_username="NoblaBot")
        assert ctx.is_bot_mentioned is True

    def test_no_mention_in_dm(self):
        update = _make_update(text="@NoblaBot hello")
        ctx = extract_user_context(update, bot_username="NoblaBot")
        # DM → is_group is False, so mention detection skipped
        assert ctx.is_bot_mentioned is False

    def test_reply_to_bot_detected(self):
        update = _make_update(
            chat_type="group",
            is_reply_to_bot=True,
            bot_username="NoblaBot",
        )
        ctx = extract_user_context(update, bot_username="NoblaBot")
        assert ctx.is_reply_to_bot is True

    def test_none_when_no_message(self):
        update = MagicMock()
        update.effective_message = None
        assert extract_user_context(update) is None

    def test_none_when_no_user(self):
        update = MagicMock()
        update.effective_message = MagicMock()
        update.effective_user = None
        update.effective_chat = MagicMock()
        assert extract_user_context(update) is None


class TestShouldProcessGroupMessage:
    """Group message filtering (mention-only mode)."""

    def test_dm_always_processed(self):
        ctx = TelegramUserContext(chat_id=1, user_id=2, is_group=False)
        assert should_process_group_message(ctx) is True

    def test_group_mentioned_processed(self):
        ctx = TelegramUserContext(
            chat_id=1, user_id=2,
            is_group=True, is_bot_mentioned=True,
        )
        assert should_process_group_message(ctx) is True

    def test_group_reply_processed(self):
        ctx = TelegramUserContext(
            chat_id=1, user_id=2,
            is_group=True, is_reply_to_bot=True,
        )
        assert should_process_group_message(ctx) is True

    def test_group_no_mention_ignored(self):
        ctx = TelegramUserContext(chat_id=1, user_id=2, is_group=True)
        assert should_process_group_message(ctx) is False


class TestStripBotMention:
    """Remove @bot mention from text."""

    def test_strips_mention(self):
        assert strip_bot_mention("@NoblaBot hello", "NoblaBot") == "hello"

    def test_no_mention_unchanged(self):
        assert strip_bot_mention("hello world", "NoblaBot") == "hello world"

    def test_none_username(self):
        assert strip_bot_mention("@NoblaBot hi", None) == "@NoblaBot hi"

    def test_strips_in_middle(self):
        result = strip_bot_mention("hey @NoblaBot do this", "NoblaBot")
        assert "@NoblaBot" not in result
        assert "hey" in result


# ══════════════════════════════════════════════════════════
# Handlers — command handlers
# ══════════════════════════════════════════════════════════


@pytest.fixture
def linking_service():
    return UserLinkingService()


@pytest.fixture
def event_bus():
    return NoblaEventBus()


@pytest.fixture
def handlers(linking_service, event_bus):
    return TelegramHandlers(
        linking=linking_service,
        event_bus=event_bus,
        bot_username="NoblaBot",
    )


class TestCmdStart:
    """Test /start command handler."""

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_code(self, handlers):
        update = _make_update(text="/start")
        context = MagicMock()
        await handlers.cmd_start(update, context)
        reply = update.effective_message.reply_text
        reply.assert_called_once()
        msg = reply.call_args[0][0]
        assert "Pairing code" in msg

    @pytest.mark.asyncio
    async def test_linked_user_gets_welcome_back(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(text="/start")
        context = MagicMock()
        await handlers.cmd_start(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "Welcome back" in msg


class TestCmdLink:
    """Test /link command handler."""

    @pytest.mark.asyncio
    async def test_link_success(self, handlers, linking_service):
        update = _make_update(text="/link user-1")
        context = MagicMock()
        context.args = ["user-1"]
        await handlers.cmd_link(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "linked" in msg.lower()

        # Verify actually linked
        linked = await linking_service.resolve("telegram", "100")
        assert linked is not None
        assert linked.nobla_user_id == "user-1"

    @pytest.mark.asyncio
    async def test_link_no_args(self, handlers):
        update = _make_update(text="/link")
        context = MagicMock()
        context.args = []
        await handlers.cmd_link(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "Usage" in msg

    @pytest.mark.asyncio
    async def test_link_already_linked(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(text="/link user-2")
        context = MagicMock()
        context.args = ["user-2"]
        await handlers.cmd_link(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "Already linked" in msg


class TestCmdUnlink:
    """Test /unlink command handler."""

    @pytest.mark.asyncio
    async def test_unlink_success(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(text="/unlink")
        context = MagicMock()
        await handlers.cmd_unlink(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "unlinked" in msg.lower()

    @pytest.mark.asyncio
    async def test_unlink_not_linked(self, handlers):
        update = _make_update(text="/unlink")
        context = MagicMock()
        await handlers.cmd_unlink(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "No account linked" in msg


class TestCmdStatus:
    """Test /status command handler."""

    @pytest.mark.asyncio
    async def test_status_linked(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(text="/status")
        context = MagicMock()
        await handlers.cmd_status(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "user-1" in msg
        assert "SAFE" in msg

    @pytest.mark.asyncio
    async def test_status_not_linked(self, handlers):
        update = _make_update(text="/status")
        context = MagicMock()
        await handlers.cmd_status(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "Not linked" in msg


# ══════════════════════════════════════════════════════════
# Handlers — message handling
# ══════════════════════════════════════════════════════════


class TestHandleMessage:
    """Test general message handler."""

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing(self, handlers):
        update = _make_update(text="hello")
        update.effective_message.reply_to_message = None
        # Mock photo/audio/etc as None
        update.effective_message.photo = None
        update.effective_message.audio = None
        update.effective_message.voice = None
        update.effective_message.video = None
        update.effective_message.video_note = None
        update.effective_message.animation = None
        update.effective_message.document = None
        context = MagicMock()
        context.bot = MagicMock()
        await handlers.handle_message(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "link your account" in msg.lower()

    @pytest.mark.asyncio
    async def test_linked_user_emits_event(self, handlers, linking_service, event_bus):
        await linking_service.link("telegram", "100", "user-1")
        captured_events = []
        event_bus.subscribe(
            "channel.message.in",
            lambda e: captured_events.append(e),
        )
        await event_bus.start()

        update = _make_update(text="hello Nobla")
        update.effective_message.reply_to_message = None
        update.effective_message.photo = None
        update.effective_message.audio = None
        update.effective_message.voice = None
        update.effective_message.video = None
        update.effective_message.video_note = None
        update.effective_message.animation = None
        update.effective_message.document = None
        context = MagicMock()
        context.bot = MagicMock()

        await handlers.handle_message(update, context)

        # Give event bus a tick to dispatch
        import asyncio
        await asyncio.sleep(0.05)

        assert len(captured_events) == 1
        assert captured_events[0].payload["message"]["content"] == "hello Nobla"
        assert captured_events[0].payload["message"]["nobla_user_id"] == "user-1"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_group_message_ignored_without_mention(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(text="hello", chat_type="group")
        context = MagicMock()
        await handlers.handle_message(update, context)
        # Should not reply (ignored)
        update.effective_message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_message_processed_with_mention(self, handlers, linking_service):
        await linking_service.link("telegram", "100", "user-1")
        update = _make_update(
            text="@NoblaBot what time is it",
            chat_type="group",
        )
        update.effective_message.reply_to_message = None
        update.effective_message.photo = None
        update.effective_message.audio = None
        update.effective_message.voice = None
        update.effective_message.video = None
        update.effective_message.video_note = None
        update.effective_message.animation = None
        update.effective_message.document = None
        context = MagicMock()
        context.bot = MagicMock()
        # Should process — bot is mentioned
        await handlers.handle_message(update, context)
        # No reply_text since linked users don't get a pairing message
        # Instead, an event should be emitted (we just verify no error)


# ══════════════════════════════════════════════════════════
# Handlers — callback queries
# ══════════════════════════════════════════════════════════


class TestHandleCallback:
    """Test inline button callback handling."""

    @pytest.mark.asyncio
    async def test_callback_acknowledged(self, handlers, linking_service, event_bus):
        await linking_service.link("telegram", "100", "user-1")
        await event_bus.start()

        update = _make_update()
        update.callback_query = MagicMock()
        update.callback_query.data = "approval:req-123:approve"
        update.callback_query.answer = AsyncMock()
        update.callback_query.message.message_id = 42

        context = MagicMock()
        await handlers.handle_callback(update, context)
        update.callback_query.answer.assert_called_once()

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_callback_no_data_ignored(self, handlers):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = None
        context = MagicMock()
        await handlers.handle_callback(update, context)

    @pytest.mark.asyncio
    async def test_callback_unlinked_user(self, handlers):
        update = _make_update()
        update.callback_query = MagicMock()
        update.callback_query.data = "test:1:click"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        await handlers.handle_callback(update, context)
        update.callback_query.edit_message_text.assert_called_once()


# ══════════════════════════════════════════════════════════
# Models — constants
# ══════════════════════════════════════════════════════════


class TestModelConstants:
    """Telegram API constants."""

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 4096

    def test_max_caption_length(self):
        assert MAX_CAPTION_LENGTH == 1024

    def test_mime_map_has_common_types(self):
        assert "image/jpeg" in MIME_TO_SEND_METHOD
        assert "audio/mpeg" in MIME_TO_SEND_METHOD
        assert "video/mp4" in MIME_TO_SEND_METHOD
