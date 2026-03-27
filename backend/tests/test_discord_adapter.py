"""Tests for the Discord channel adapter (Phase 5A).

Covers: DiscordSettings, models, formatter, media handler, handlers, adapter.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    ChannelResponse,
    InlineAction,
)
from nobla.channels.linking import UserLinkingService
from nobla.channels.discord.formatter import (
    ButtonSpec,
    FormattedMessage,
    build_button_specs,
    format_response,
    split_message,
)
from nobla.channels.discord.media import (
    attachment_to_file,
    detect_attachment_type,
    is_embeddable,
)
from nobla.channels.discord.models import (
    MAX_FILE_SIZE_BOOSTED_MB,
    MAX_FILE_SIZE_DEFAULT_MB,
    MAX_MESSAGE_LENGTH,
    MIME_TO_EMBED_TYPE,
    DiscordUserContext,
)
from nobla.config.settings import DiscordSettings
from nobla.events.bus import NoblaEventBus


# ══════════════════════════════════════════════════════════
# DiscordSettings
# ══════════════════════════════════════════════════════════


class TestDiscordSettings:
    """DiscordSettings validation."""

    def test_defaults(self):
        s = DiscordSettings()
        assert s.enabled is False
        assert s.bot_token == ""
        assert s.command_prefix == "!"
        assert s.group_activation == "mention"
        assert s.max_file_size_mb == 25
        assert s.sync_commands_on_start is True

    def test_custom_prefix(self):
        s = DiscordSettings(command_prefix="?")
        assert s.command_prefix == "?"

    def test_empty_prefix_rejected(self):
        with pytest.raises(ValueError, match="command_prefix must not be empty"):
            DiscordSettings(command_prefix="")

    def test_custom_file_size(self):
        s = DiscordSettings(max_file_size_mb=100)
        assert s.max_file_size_mb == 100

    def test_enabled_with_token(self):
        s = DiscordSettings(enabled=True, bot_token="my-token")
        assert s.enabled is True
        assert s.bot_token == "my-token"


# ══════════════════════════════════════════════════════════
# DiscordUserContext
# ══════════════════════════════════════════════════════════


class TestDiscordUserContext:
    """DiscordUserContext model."""

    def test_basic_fields(self):
        ctx = DiscordUserContext(channel_id=111, user_id=222)
        assert ctx.channel_id == 111
        assert ctx.user_id == 222
        assert ctx.username is None
        assert ctx.is_guild is False

    def test_str_properties(self):
        ctx = DiscordUserContext(channel_id=111, user_id=222)
        assert ctx.channel_id_str == "111"
        assert ctx.user_id_str == "222"

    def test_guild_flags(self):
        ctx = DiscordUserContext(
            channel_id=111, user_id=222,
            guild_id=333, is_guild=True, is_bot_mentioned=True,
        )
        assert ctx.is_guild is True
        assert ctx.guild_id == 333
        assert ctx.is_bot_mentioned is True
        assert ctx.is_reply_to_bot is False

    def test_raw_extras_default(self):
        ctx = DiscordUserContext(channel_id=1, user_id=2)
        assert ctx.raw_extras == {}

    def test_display_name(self):
        ctx = DiscordUserContext(
            channel_id=1, user_id=2,
            username="bob", display_name="Bob Smith",
        )
        assert ctx.display_name == "Bob Smith"


# ══════════════════════════════════════════════════════════
# Formatter — split_message
# ══════════════════════════════════════════════════════════


class TestSplitMessage:
    """Message splitting for Discord's 2000 char limit."""

    def test_short_message_single_chunk(self):
        result = split_message("hello", limit=2000)
        assert result == ["hello"]

    def test_exactly_at_limit(self):
        text = "a" * 2000
        result = split_message(text, limit=2000)
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
# Formatter — build_button_specs
# ══════════════════════════════════════════════════════════


class TestBuildButtonSpecs:
    """InlineAction → ButtonSpec conversion."""

    def test_none_actions_returns_none(self):
        assert build_button_specs(None) is None

    def test_empty_actions_returns_none(self):
        assert build_button_specs([]) is None

    def test_single_button(self):
        actions = [InlineAction(action_id="test:1:approve", label="Approve")]
        result = build_button_specs(actions)
        assert len(result) == 1
        assert result[0].label == "Approve"
        assert result[0].custom_id == "test:1:approve"

    def test_multiple_buttons(self):
        actions = [
            InlineAction(action_id=f"a:{i}:go", label=f"Btn{i}")
            for i in range(5)
        ]
        result = build_button_specs(actions)
        assert len(result) == 5

    def test_max_25_buttons(self):
        actions = [
            InlineAction(action_id=f"a:{i}:go", label=f"Btn{i}")
            for i in range(30)
        ]
        result = build_button_specs(actions)
        assert len(result) == 25

    def test_style_preserved(self):
        actions = [InlineAction(action_id="t:1:del", label="Delete", style="danger")]
        result = build_button_specs(actions)
        assert result[0].style == "danger"


# ══════════════════════════════════════════════════════════
# Formatter — format_response
# ══════════════════════════════════════════════════════════


class TestFormatResponse:
    """Full response formatting pipeline."""

    def test_simple_text(self):
        resp = ChannelResponse(content="hello")
        result = format_response(resp)
        assert len(result) == 1
        assert result[0].content == "hello"

    def test_buttons_on_last_chunk_only(self):
        long_text = "a" * 3000
        actions = [InlineAction(action_id="t:1:ok", label="OK")]
        resp = ChannelResponse(content=long_text, actions=actions)
        result = format_response(resp)
        assert len(result) >= 2
        assert result[-1].buttons is not None
        for msg in result[:-1]:
            assert msg.buttons is None

    def test_no_actions_no_buttons(self):
        resp = ChannelResponse(content="hi")
        result = format_response(resp)
        assert result[0].buttons is None

    def test_markdown_not_escaped(self):
        resp = ChannelResponse(content="**bold** and _italic_")
        result = format_response(resp)
        assert result[0].content == "**bold** and _italic_"


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

    def test_video_mp4(self):
        assert detect_attachment_type("video/mp4") == AttachmentType.VIDEO

    def test_unknown_mime_is_document(self):
        assert detect_attachment_type("application/pdf") == AttachmentType.DOCUMENT


# ══════════════════════════════════════════════════════════
# Media — attachment_to_file
# ══════════════════════════════════════════════════════════


class TestAttachmentToFile:
    """Nobla Attachment → discord.File kwargs."""

    def test_with_data(self):
        att = Attachment(
            type=AttachmentType.IMAGE, filename="pic.jpg",
            mime_type="image/jpeg", size_bytes=100,
            data=b"fake-image-data",
        )
        result = attachment_to_file(att)
        assert result["filename"] == "pic.jpg"
        assert isinstance(result["fp"], BytesIO)
        assert result["fp"].read() == b"fake-image-data"

    def test_without_data_returns_empty(self):
        att = Attachment(
            type=AttachmentType.IMAGE, filename="pic.jpg",
            mime_type="image/jpeg", size_bytes=100,
            data=None,
        )
        result = attachment_to_file(att)
        assert result == {}


# ══════════════════════════════════════════════════════════
# Media — is_embeddable
# ══════════════════════════════════════════════════════════


class TestIsEmbeddable:
    """Check if MIME type is embeddable in Discord."""

    def test_jpeg_embeddable(self):
        assert is_embeddable("image/jpeg") is True

    def test_png_embeddable(self):
        assert is_embeddable("image/png") is True

    def test_mp4_embeddable(self):
        assert is_embeddable("video/mp4") is True

    def test_pdf_not_embeddable(self):
        assert is_embeddable("application/pdf") is False

    def test_octet_stream_not_embeddable(self):
        assert is_embeddable("application/octet-stream") is False


# ══════════════════════════════════════════════════════════
# Handlers — context extraction and guild logic
# ══════════════════════════════════════════════════════════


from nobla.channels.discord.handlers import (
    DiscordHandlers,
    extract_user_context,
    should_process_guild_message,
    strip_bot_mention,
)


def _make_discord_message(
    content: str = "hello",
    user_id: int = 100,
    username: str = "testuser",
    channel_id: int = 200,
    guild_id: int | None = None,
    is_bot: bool = False,
    bot_user: MagicMock | None = None,
    mentions: list | None = None,
    is_reply_to_bot: bool = False,
    message_id: int = 1,
) -> MagicMock:
    """Build a mock Discord Message."""
    msg = MagicMock()
    msg.content = content
    msg.id = message_id
    msg.author.id = user_id
    msg.author.name = username
    msg.author.display_name = username
    msg.author.bot = is_bot
    msg.channel.id = channel_id
    msg.reference = None
    msg.attachments = []
    msg.reply = AsyncMock()

    if guild_id:
        msg.guild = MagicMock()
        msg.guild.id = guild_id
    else:
        msg.guild = None

    msg.mentions = mentions or []

    if is_reply_to_bot and bot_user:
        ref = MagicMock()
        ref.resolved = MagicMock()
        ref.resolved.author = bot_user
        ref.message_id = 42
        msg.reference = ref

    return msg


def _make_bot_user(user_id: int = 999) -> MagicMock:
    """Build a mock Discord bot user."""
    bot = MagicMock()
    bot.id = user_id
    bot.name = "NoblaBot"
    return bot


class TestExtractUserContext:
    """extract_user_context from Discord message."""

    def test_dm_message(self):
        msg = _make_discord_message()
        ctx = extract_user_context(msg)
        assert ctx is not None
        assert ctx.channel_id == 200
        assert ctx.user_id == 100
        assert ctx.is_guild is False

    def test_guild_message(self):
        msg = _make_discord_message(guild_id=333)
        ctx = extract_user_context(msg)
        assert ctx.is_guild is True
        assert ctx.guild_id == 333

    def test_bot_author_returns_none(self):
        msg = _make_discord_message(is_bot=True)
        ctx = extract_user_context(msg)
        assert ctx is None

    def test_mention_detected(self):
        bot = _make_bot_user()
        msg = _make_discord_message(
            content="hey bot", guild_id=333, mentions=[bot],
        )
        ctx = extract_user_context(msg, bot_user=bot)
        assert ctx.is_bot_mentioned is True

    def test_no_mention_in_dm(self):
        bot = _make_bot_user()
        msg = _make_discord_message(content="hello", mentions=[bot])
        ctx = extract_user_context(msg, bot_user=bot)
        # DM → is_guild is False, no mention check
        assert ctx.is_bot_mentioned is False

    def test_reply_to_bot_detected(self):
        bot = _make_bot_user()
        msg = _make_discord_message(
            guild_id=333, is_reply_to_bot=True, bot_user=bot,
        )
        ctx = extract_user_context(msg, bot_user=bot)
        assert ctx.is_reply_to_bot is True

    def test_username_captured(self):
        msg = _make_discord_message(username="alice")
        ctx = extract_user_context(msg)
        assert ctx.username == "alice"


class TestShouldProcessGuildMessage:
    """Guild message filtering (mention-only mode)."""

    def test_dm_always_processed(self):
        ctx = DiscordUserContext(channel_id=1, user_id=2, is_guild=False)
        assert should_process_guild_message(ctx) is True

    def test_guild_mentioned_processed(self):
        ctx = DiscordUserContext(
            channel_id=1, user_id=2,
            is_guild=True, is_bot_mentioned=True,
        )
        assert should_process_guild_message(ctx) is True

    def test_guild_reply_processed(self):
        ctx = DiscordUserContext(
            channel_id=1, user_id=2,
            is_guild=True, is_reply_to_bot=True,
        )
        assert should_process_guild_message(ctx) is True

    def test_guild_no_mention_ignored(self):
        ctx = DiscordUserContext(channel_id=1, user_id=2, is_guild=True)
        assert should_process_guild_message(ctx) is False


class TestStripBotMention:
    """Remove <@bot_id> mention from content."""

    def test_strips_mention(self):
        assert strip_bot_mention("<@999> hello", 999) == "hello"

    def test_strips_nick_mention(self):
        assert strip_bot_mention("<@!999> hello", 999) == "hello"

    def test_no_mention_unchanged(self):
        assert strip_bot_mention("hello world", 999) == "hello world"

    def test_none_bot_id(self):
        assert strip_bot_mention("<@999> hi", None) == "<@999> hi"


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
    return DiscordHandlers(
        linking=linking_service,
        event_bus=event_bus,
        command_prefix="!",
    )


class TestCmdStart:
    """Test !start command handler."""

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_code(self, handlers):
        msg = _make_discord_message(content="!start")
        await handlers.handle_message(msg)
        reply = msg.reply
        reply.assert_called_once()
        text = reply.call_args[0][0]
        assert "Pairing code" in text

    @pytest.mark.asyncio
    async def test_linked_user_gets_welcome_back(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        msg = _make_discord_message(content="!start")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "Welcome back" in text


class TestCmdLink:
    """Test !link command handler."""

    @pytest.mark.asyncio
    async def test_link_success(self, handlers, linking_service):
        msg = _make_discord_message(content="!link user-1")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "linked" in text.lower()

        linked = await linking_service.resolve("discord", "100")
        assert linked is not None
        assert linked.nobla_user_id == "user-1"

    @pytest.mark.asyncio
    async def test_link_no_args(self, handlers):
        msg = _make_discord_message(content="!link")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_link_already_linked(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        msg = _make_discord_message(content="!link user-2")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "Already linked" in text


class TestCmdUnlink:
    """Test !unlink command handler."""

    @pytest.mark.asyncio
    async def test_unlink_success(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        msg = _make_discord_message(content="!unlink")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "unlinked" in text.lower()

    @pytest.mark.asyncio
    async def test_unlink_not_linked(self, handlers):
        msg = _make_discord_message(content="!unlink")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "No account linked" in text


class TestCmdStatus:
    """Test !status command handler."""

    @pytest.mark.asyncio
    async def test_status_linked(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        msg = _make_discord_message(content="!status")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "user-1" in text
        assert "SAFE" in text

    @pytest.mark.asyncio
    async def test_status_not_linked(self, handlers):
        msg = _make_discord_message(content="!status")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "Not linked" in text


# ══════════════════════════════════════════════════════════
# Handlers — message handling
# ══════════════════════════════════════════════════════════


class TestHandleMessage:
    """Test general message handler."""

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing(self, handlers):
        msg = _make_discord_message(content="hello")
        await handlers.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "link your account" in text.lower()

    @pytest.mark.asyncio
    async def test_linked_user_emits_event(self, handlers, linking_service, event_bus):
        await linking_service.link("discord", "100", "user-1")
        captured_events = []
        event_bus.subscribe(
            "channel.message.in",
            lambda e: captured_events.append(e),
        )
        await event_bus.start()

        msg = _make_discord_message(content="hello Nobla")
        await handlers.handle_message(msg)

        import asyncio
        await asyncio.sleep(0.05)

        assert len(captured_events) == 1
        assert captured_events[0].payload["message"]["content"] == "hello Nobla"
        assert captured_events[0].payload["message"]["nobla_user_id"] == "user-1"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_guild_message_ignored_without_mention(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        msg = _make_discord_message(content="hello", guild_id=333)
        await handlers.handle_message(msg)
        msg.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_guild_message_processed_with_mention(self, handlers, linking_service):
        await linking_service.link("discord", "100", "user-1")
        bot = _make_bot_user()
        handlers.set_bot_user(bot)
        msg = _make_discord_message(
            content="<@999> what time is it",
            guild_id=333,
            mentions=[bot],
        )
        await handlers.handle_message(msg)
        # Should process — no reply_text pairing error means it routed


# ══════════════════════════════════════════════════════════
# Handlers — interaction handler
# ══════════════════════════════════════════════════════════


class TestHandleInteraction:
    """Test button interaction handling."""

    @pytest.mark.asyncio
    async def test_interaction_deferred(self, handlers, linking_service, event_bus):
        await linking_service.link("discord", "100", "user-1")
        await event_bus.start()

        interaction = MagicMock()
        interaction.data = {"custom_id": "approval:req-123:approve"}
        interaction.user.id = 100
        interaction.message.id = 42
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await handlers.handle_interaction(interaction)
        interaction.response.defer.assert_called_once()

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_interaction_no_data_ignored(self, handlers):
        interaction = MagicMock()
        interaction.data = None
        await handlers.handle_interaction(interaction)

    @pytest.mark.asyncio
    async def test_interaction_unlinked_user(self, handlers):
        interaction = MagicMock()
        interaction.data = {"custom_id": "test:1:click"}
        interaction.user.id = 100
        interaction.response.send_message = AsyncMock()
        await handlers.handle_interaction(interaction)
        interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_interaction_empty_custom_id_ignored(self, handlers):
        interaction = MagicMock()
        interaction.data = {"custom_id": ""}
        await handlers.handle_interaction(interaction)


# ══════════════════════════════════════════════════════════
# Handlers — custom prefix
# ══════════════════════════════════════════════════════════


class TestCustomPrefix:
    """Test handlers with non-default command prefix."""

    @pytest.mark.asyncio
    async def test_custom_prefix_start(self, linking_service, event_bus):
        h = DiscordHandlers(
            linking=linking_service, event_bus=event_bus,
            command_prefix="?",
        )
        msg = _make_discord_message(content="?start")
        await h.handle_message(msg)
        text = msg.reply.call_args[0][0]
        assert "Pairing code" in text

    @pytest.mark.asyncio
    async def test_wrong_prefix_ignored_as_regular(self, handlers, linking_service):
        # "!" is the prefix, "?" should be treated as regular text
        msg = _make_discord_message(content="?start")
        await handlers.handle_message(msg)
        # Unlinked → pairing prompt (not a command response)
        text = msg.reply.call_args[0][0]
        assert "link your account" in text.lower()


# ══════════════════════════════════════════════════════════
# Models — constants
# ══════════════════════════════════════════════════════════


class TestModelConstants:
    """Discord API constants."""

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 2000

    def test_max_file_size_default(self):
        assert MAX_FILE_SIZE_DEFAULT_MB == 25

    def test_max_file_size_boosted(self):
        assert MAX_FILE_SIZE_BOOSTED_MB == 100

    def test_mime_map_has_common_types(self):
        assert "image/jpeg" in MIME_TO_EMBED_TYPE
        assert "video/mp4" in MIME_TO_EMBED_TYPE
        assert "audio/mpeg" in MIME_TO_EMBED_TYPE
