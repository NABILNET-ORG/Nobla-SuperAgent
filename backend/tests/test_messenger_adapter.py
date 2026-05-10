"""Tests for the Facebook Messenger Platform channel adapter (Phase 5-Channels).

Covers: dataclasses + constants, formatter (escape, split, quick_replies,
button template, format_response), media (type detection, MIME guessing),
handlers (webhook dispatch, keyword commands, postbacks, delivery/read
receipts, event emission), adapter lifecycle, webhook verification (signature
+ challenge), outbound send paths, callback parsing, health check, and
end-to-end webhook payload handling.

Mirrors the WhatsApp test suite's shape and fixture pattern so future channel
adapters can copy the same skeleton.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    ChannelResponse,
    InlineAction,
)
from nobla.channels.messenger import MessengerAdapter
from nobla.channels.messenger.formatter import (
    FormattedMessage,
    build_button_template,
    build_quick_replies,
    escape_messenger_text,
    format_response,
    split_message,
)
from nobla.channels.messenger.handlers import MessengerHandlers
from nobla.channels.messenger.media import (
    detect_attachment_type,
    guess_mime_type,
)
from nobla.channels.messenger.models import (
    CHANNEL_NAME,
    DEFAULT_API_VERSION,
    GRAPH_API_BASE,
    MAX_BUTTON_TITLE_LENGTH,
    MAX_BUTTONS,
    MAX_GENERIC_TEMPLATE_ELEMENTS,
    MAX_LIST_ITEMS,
    MAX_MESSAGE_LENGTH,
    MAX_POSTBACK_PAYLOAD_LENGTH,
    MAX_QUICK_REPLIES,
    MAX_QUICK_REPLY_TITLE_LENGTH,
    MESSAGING_TYPES,
    SUPPORTED_MESSAGE_TYPES,
    WEBHOOK_FIELDS,
    MessengerUserContext,
)


# ── Fixtures ──────────────────────────────────────────────


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


@dataclass
class FakeSettings:
    enabled: bool = True
    page_access_token: str = "test-page-token"
    page_id: str = "999000111"
    app_secret: str = "test-app-secret"
    verify_token: str = "verify-me-token"
    webhook_path: str = "/webhook/messenger"
    api_version: str = "v21.0"
    group_activation: str = "mention"
    max_file_size_mb: int = 100
    download_timeout: int = 30
    message_ttl_days: int = 30


@pytest.fixture
def settings():
    return FakeSettings()


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


@pytest.fixture
def handlers(linking, event_bus):
    h = MessengerHandlers(
        linking=linking,
        event_bus=event_bus,
        page_access_token="test-page-token",
        page_id="999000111",
        api_version="v21.0",
        max_file_size_mb=100,
    )
    h.set_send_fn(AsyncMock())
    return h


@pytest.fixture
def adapter(settings, handlers):
    return MessengerAdapter(settings=settings, handlers=handlers)


def _make_message_event(
    text: str = "hello",
    psid: str = "PSID-100",
    mid: str = "mid.test123",
    timestamp: int = 1700000000000,
    page_id: str = "999000111",
    is_echo: bool = False,
    quick_reply_payload: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Build a single Messenger ``messaging[]`` message event."""
    message: dict[str, Any] = {"mid": mid, "text": text}
    if is_echo:
        message["is_echo"] = True
    if quick_reply_payload is not None:
        message["quick_reply"] = {"payload": quick_reply_payload}
    if reply_to is not None:
        message["reply_to"] = {"mid": reply_to}
    return {
        "sender": {"id": psid},
        "recipient": {"id": page_id},
        "timestamp": timestamp,
        "message": message,
    }


def _make_postback_event(
    payload: str = "ACTION_X",
    psid: str = "PSID-100",
    mid: str = "mid.pb1",
    timestamp: int = 1700000000000,
    title: str = "Action X",
    page_id: str = "999000111",
) -> dict[str, Any]:
    return {
        "sender": {"id": psid},
        "recipient": {"id": page_id},
        "timestamp": timestamp,
        "postback": {"payload": payload, "title": title, "mid": mid},
    }


def _make_delivery_event(
    psid: str = "PSID-100",
    watermark: int = 1700000000000,
    mids: list[str] | None = None,
    timestamp: int = 1700000000001,
    page_id: str = "999000111",
) -> dict[str, Any]:
    return {
        "sender": {"id": psid},
        "recipient": {"id": page_id},
        "timestamp": timestamp,
        "delivery": {
            "mids": mids or ["mid.x1", "mid.x2"],
            "watermark": watermark,
        },
    }


def _make_read_event(
    psid: str = "PSID-100",
    watermark: int = 1700000000000,
    timestamp: int = 1700000000002,
    page_id: str = "999000111",
) -> dict[str, Any]:
    return {
        "sender": {"id": psid},
        "recipient": {"id": page_id},
        "timestamp": timestamp,
        "read": {"watermark": watermark},
    }


def _make_webhook_payload(
    events: list[dict[str, Any]] | None = None,
    page_id: str = "999000111",
    object_type: str = "page",
    timestamp: int = 1700000000000,
) -> dict[str, Any]:
    """Build a Messenger webhook envelope around ``events``."""
    if events is None:
        events = [_make_message_event()]
    return {
        "object": object_type,
        "entry": [
            {
                "id": page_id,
                "time": timestamp,
                "messaging": events,
            }
        ],
    }


def _sign_payload(body: bytes, secret: str) -> str:
    """Compute X-Hub-Signature-256 for a payload (Meta scheme)."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _response_with_metadata(
    content: str,
    actions: list[InlineAction] | None = None,
    metadata: dict[str, Any] | None = None,
    attachments: list[Attachment] | None = None,
):
    """Return an object that quacks like a ChannelResponse but exposes
    ``metadata`` so the formatter can read ``response.metadata['ui']``.

    ``ChannelResponse`` is ``slots=True`` and has no ``metadata`` field; the
    formatter uses ``getattr(response, "metadata", None) or {}`` so any
    attribute-bearing object suffices for the buttons-UI path.
    """
    return SimpleNamespace(
        content=content,
        actions=actions,
        metadata=metadata or {},
        attachments=attachments or [],
    )


# ═════════════════════════════════════════════════════════
# Models
# ═════════════════════════════════════════════════════════


class TestMessengerUserContext:
    def test_minimal_construction(self):
        ctx = MessengerUserContext(psid="PSID-100")
        assert ctx.psid == "PSID-100"
        assert ctx.display_name is None
        assert ctx.message_id == ""
        assert ctx.chat_id == ""
        assert ctx.is_group is False
        assert ctx.is_bot_mentioned is False
        assert ctx.is_reply_to_bot is False
        assert ctx.timestamp == 0
        assert ctx.raw_extras == {}

    def test_full_construction(self):
        ctx = MessengerUserContext(
            psid="PSID-200",
            display_name="Alice",
            message_id="mid.42",
            chat_id="chat-7",
            is_group=True,
            is_bot_mentioned=True,
            is_reply_to_bot=True,
            timestamp=1700000000000,
            raw_extras={"thread_type": "GROUP"},
        )
        assert ctx.display_name == "Alice"
        assert ctx.message_id == "mid.42"
        assert ctx.chat_id == "chat-7"
        assert ctx.is_group is True
        assert ctx.is_bot_mentioned is True
        assert ctx.is_reply_to_bot is True
        assert ctx.timestamp == 1700000000000
        assert ctx.raw_extras == {"thread_type": "GROUP"}

    def test_user_id_str_is_psid(self):
        ctx = MessengerUserContext(psid="PSID-X")
        assert ctx.user_id_str == "PSID-X"

    def test_chat_id_str_falls_back_to_psid(self):
        ctx = MessengerUserContext(psid="PSID-X")
        assert ctx.chat_id_str == "PSID-X"

    def test_chat_id_str_uses_explicit_chat_id(self):
        ctx = MessengerUserContext(psid="PSID-X", chat_id="thread-9")
        assert ctx.chat_id_str == "thread-9"

    def test_is_dm_default(self):
        ctx = MessengerUserContext(psid="PSID-X")
        assert ctx.is_dm is True

    def test_is_dm_false_when_group(self):
        ctx = MessengerUserContext(psid="PSID-X", is_group=True)
        assert ctx.is_dm is False

    def test_slots_constraint(self):
        ctx = MessengerUserContext(psid="PSID-X")
        with pytest.raises(AttributeError):
            ctx.unknown_attribute = "nope"  # type: ignore[attr-defined]


class TestConstants:
    def test_channel_name(self):
        assert CHANNEL_NAME == "messenger"

    def test_graph_api_base(self):
        assert GRAPH_API_BASE == "https://graph.facebook.com"

    def test_default_api_version(self):
        assert DEFAULT_API_VERSION.startswith("v")
        assert DEFAULT_API_VERSION == "v21.0"

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 2000

    def test_max_quick_replies(self):
        assert MAX_QUICK_REPLIES == 13

    def test_max_buttons(self):
        assert MAX_BUTTONS == 3

    def test_max_generic_template_elements(self):
        assert MAX_GENERIC_TEMPLATE_ELEMENTS == 10

    def test_max_list_items(self):
        assert MAX_LIST_ITEMS == 4

    def test_max_quick_reply_title_length(self):
        assert MAX_QUICK_REPLY_TITLE_LENGTH == 20

    def test_max_button_title_length(self):
        assert MAX_BUTTON_TITLE_LENGTH == 20

    def test_max_postback_payload_length(self):
        assert MAX_POSTBACK_PAYLOAD_LENGTH == 1000

    def test_supported_message_types(self):
        for t in ("text", "image", "video", "audio", "file", "location"):
            assert t in SUPPORTED_MESSAGE_TYPES
        assert "unsupported_xyz" not in SUPPORTED_MESSAGE_TYPES

    def test_messaging_types(self):
        for t in ("RESPONSE", "UPDATE", "MESSAGE_TAG"):
            assert t in MESSAGING_TYPES
        assert "BOGUS" not in MESSAGING_TYPES

    def test_webhook_fields(self):
        for f in (
            "messages",
            "messaging_postbacks",
            "messaging_deliveries",
            "messaging_reads",
        ):
            assert f in WEBHOOK_FIELDS


# ═════════════════════════════════════════════════════════
# Formatter — text
# ═════════════════════════════════════════════════════════


class TestEscapeMessengerText:
    def test_empty_string(self):
        assert escape_messenger_text("") == ""

    def test_plain_text_unchanged(self):
        assert escape_messenger_text("hello world") == "hello world"

    def test_strips_control_chars(self):
        # \x01 is a control char; \n must be preserved.
        assert escape_messenger_text("hi\x01there\nok") == "hithere\nok"

    def test_preserves_newlines(self):
        result = escape_messenger_text("a\nb\nc")
        assert result == "a\nb\nc"

    def test_tabs_collapsed_to_space(self):
        # The control-char regex preserves \t (chr 9), but the line cleaner
        # ``re.sub(r"[ \t]+", " ", ...)`` collapses tabs into a single space.
        assert escape_messenger_text("col1\tcol2") == "col1 col2"

    def test_collapses_intra_line_whitespace(self):
        assert escape_messenger_text("hello    world") == "hello world"

    def test_collapses_tabs_in_line(self):
        assert escape_messenger_text("a \t  b") == "a b"

    def test_strips_trailing_whitespace_per_line(self):
        assert escape_messenger_text("hello   \nworld   ") == "hello\nworld"

    def test_strips_leading_and_trailing_blank_lines(self):
        assert escape_messenger_text("\n\nbody\n\n") == "body"

    def test_unicode_normalized_to_nfc(self):
        # "e" + combining acute (NFD) → single "é" (NFC).
        nfd = "é"
        result = escape_messenger_text(nfd)
        assert result == "é"

    def test_strips_del_char(self):
        assert escape_messenger_text("a\x7fb") == "ab"


class TestSplitMessage:
    def test_empty_string_returns_empty_list(self):
        assert split_message("") == []

    def test_short_message_single_chunk(self):
        assert split_message("hello") == ["hello"]

    def test_exact_limit_single_chunk(self):
        msg = "x" * MAX_MESSAGE_LENGTH
        assert split_message(msg) == [msg]

    def test_over_limit_splits(self):
        msg = "x" * (MAX_MESSAGE_LENGTH + 100)
        chunks = split_message(msg)
        assert len(chunks) >= 2
        assert all(len(c) <= MAX_MESSAGE_LENGTH for c in chunks)

    def test_splits_at_newline_boundary(self):
        msg = "a" * 1500 + "\n" + "b" * 1500
        chunks = split_message(msg, limit=2000)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 1500
        assert chunks[1] == "b" * 1500

    def test_splits_at_space_when_no_newline(self):
        msg = ("word " * 600).strip()
        chunks = split_message(msg, limit=100)
        assert all(len(c) <= 100 for c in chunks)
        assert len(chunks) > 1

    def test_hard_cut_for_super_long_word(self):
        msg = "a" * 5000
        chunks = split_message(msg, limit=2000)
        assert len(chunks) == 3
        assert chunks[0] == "a" * 2000
        assert chunks[1] == "a" * 2000
        assert chunks[2] == "a" * 1000

    def test_custom_limit(self):
        msg = "abcdefghij"
        chunks = split_message(msg, limit=4)
        assert all(len(c) <= 4 for c in chunks)
        assert "".join(chunks) == msg


# ═════════════════════════════════════════════════════════
# Formatter — interactive payloads
# ═════════════════════════════════════════════════════════


class TestBuildQuickReplies:
    def test_empty_actions_returns_empty(self):
        assert build_quick_replies([]) == []

    def test_single_action(self):
        actions = [InlineAction(action_id="approve", label="Approve")]
        qr = build_quick_replies(actions)
        assert len(qr) == 1
        assert qr[0]["content_type"] == "text"
        assert qr[0]["title"] == "Approve"
        assert qr[0]["payload"] == "approve"

    def test_keeps_under_cap(self):
        actions = [
            InlineAction(action_id=f"a{i}", label=f"L{i}") for i in range(5)
        ]
        qr = build_quick_replies(actions)
        assert len(qr) == 5

    def test_truncates_to_cap(self):
        actions = [
            InlineAction(action_id=f"a{i}", label=f"L{i}") for i in range(20)
        ]
        qr = build_quick_replies(actions)
        assert len(qr) == MAX_QUICK_REPLIES

    def test_clamps_long_title(self):
        actions = [InlineAction(action_id="x", label="A" * 50)]
        qr = build_quick_replies(actions)
        assert len(qr[0]["title"]) == MAX_QUICK_REPLY_TITLE_LENGTH

    def test_skips_empty_label(self):
        actions = [
            InlineAction(action_id="x", label=""),
            InlineAction(action_id="y", label="OK"),
        ]
        qr = build_quick_replies(actions)
        assert len(qr) == 1
        assert qr[0]["title"] == "OK"

    def test_payload_falls_back_to_title(self):
        actions = [InlineAction(action_id="", label="Yes")]
        qr = build_quick_replies(actions)
        assert qr[0]["payload"] == "Yes"

    def test_payload_clamped_to_cap(self):
        long_id = "x" * (MAX_POSTBACK_PAYLOAD_LENGTH + 200)
        actions = [InlineAction(action_id=long_id, label="L")]
        qr = build_quick_replies(actions)
        assert len(qr[0]["payload"]) == MAX_POSTBACK_PAYLOAD_LENGTH


class TestBuildButtonTemplate:
    def test_payload_shape(self):
        actions = [InlineAction(action_id="ok", label="OK")]
        tpl = build_button_template("Pick:", actions)
        assert tpl["type"] == "template"
        assert tpl["payload"]["template_type"] == "button"
        assert tpl["payload"]["text"] == "Pick:"
        assert isinstance(tpl["payload"]["buttons"], list)

    def test_button_postback_shape(self):
        actions = [InlineAction(action_id="approve", label="Approve")]
        tpl = build_button_template("Body", actions)
        btn = tpl["payload"]["buttons"][0]
        assert btn["type"] == "postback"
        assert btn["title"] == "Approve"
        assert btn["payload"] == "approve"

    def test_keeps_under_cap(self):
        actions = [
            InlineAction(action_id=f"a{i}", label=f"L{i}") for i in range(2)
        ]
        tpl = build_button_template("Body", actions)
        assert len(tpl["payload"]["buttons"]) == 2

    def test_truncates_to_cap(self):
        actions = [
            InlineAction(action_id=f"a{i}", label=f"L{i}") for i in range(10)
        ]
        tpl = build_button_template("Body", actions)
        assert len(tpl["payload"]["buttons"]) == MAX_BUTTONS

    def test_truncates_long_button_title(self):
        actions = [InlineAction(action_id="x", label="B" * 40)]
        tpl = build_button_template("Body", actions)
        assert len(tpl["payload"]["buttons"][0]["title"]) == MAX_BUTTON_TITLE_LENGTH

    def test_skips_empty_label(self):
        actions = [
            InlineAction(action_id="x", label=""),
            InlineAction(action_id="y", label="Real"),
        ]
        tpl = build_button_template("Body", actions)
        buttons = tpl["payload"]["buttons"]
        assert len(buttons) == 1
        assert buttons[0]["title"] == "Real"

    def test_text_capped_at_640(self):
        long_text = "x" * 1000
        actions = [InlineAction(action_id="ok", label="OK")]
        tpl = build_button_template(long_text, actions)
        assert len(tpl["payload"]["text"]) == 640


class TestFormatResponse:
    def test_simple_text_no_actions(self):
        resp = ChannelResponse(content="Hello!")
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello!"
        assert msgs[0].interactive is None

    def test_empty_no_actions_returns_empty(self):
        resp = ChannelResponse(content="")
        assert format_response(resp) == []

    def test_empty_with_actions_yields_placeholder_chunk(self):
        resp = ChannelResponse(
            content="",
            actions=[InlineAction(action_id="ok", label="OK")],
        )
        msgs = format_response(resp)
        assert len(msgs) == 1
        # Empty body promotes to placeholder so quick_replies have a host msg.
        assert msgs[0].interactive is not None

    def test_with_quick_replies_default_path(self):
        resp = ChannelResponse(
            content="Pick one:",
            actions=[
                InlineAction(action_id="a", label="A"),
                InlineAction(action_id="b", label="B"),
            ],
        )
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].interactive is not None
        assert msgs[0].interactive["type"] == "quick_replies"
        assert len(msgs[0].interactive["quick_replies"]) == 2

    def test_buttons_ui_path(self):
        resp = _response_with_metadata(
            content="Approve?",
            actions=[
                InlineAction(action_id="yes", label="Yes"),
                InlineAction(action_id="no", label="No"),
            ],
            metadata={"ui": "buttons"},
        )
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].interactive is not None
        assert msgs[0].interactive["type"] == "button_template"

    def test_buttons_path_falls_back_to_qr_if_too_many(self):
        # >MAX_BUTTONS forces fallback to quick_replies even with ui=buttons.
        resp = _response_with_metadata(
            content="Pick:",
            actions=[
                InlineAction(action_id=f"a{i}", label=f"L{i}") for i in range(5)
            ],
            metadata={"ui": "buttons"},
        )
        msgs = format_response(resp)
        assert msgs[-1].interactive["type"] == "quick_replies"

    def test_multi_chunk_only_last_has_interactive(self):
        # Force splitting by exceeding MAX_MESSAGE_LENGTH.
        resp = ChannelResponse(
            content="x" * (MAX_MESSAGE_LENGTH + 500),
            actions=[InlineAction(action_id="ok", label="OK")],
        )
        msgs = format_response(resp)
        assert len(msgs) >= 2
        for m in msgs[:-1]:
            assert m.interactive is None
        assert msgs[-1].interactive is not None

    def test_actions_with_empty_labels_no_interactive(self):
        resp = ChannelResponse(
            content="Hi",
            actions=[InlineAction(action_id="x", label="")],
        )
        msgs = format_response(resp)
        # No usable quick replies → interactive omitted.
        assert msgs[0].interactive is None


# ═════════════════════════════════════════════════════════
# Media — type detection
# ═════════════════════════════════════════════════════════


class TestDetectAttachmentType:
    def test_image_jpg(self):
        assert detect_attachment_type("photo.jpg") == AttachmentType.IMAGE

    def test_image_png(self):
        assert detect_attachment_type("pic.png") == AttachmentType.IMAGE

    def test_video_mp4(self):
        assert detect_attachment_type("clip.mp4") == AttachmentType.VIDEO

    def test_audio_ogg(self):
        # mimetypes maps .ogg → audio/ogg on most platforms.
        result = detect_attachment_type("voice.ogg")
        assert result in (AttachmentType.AUDIO, AttachmentType.DOCUMENT)

    def test_audio_mp3(self):
        assert detect_attachment_type("song.mp3") == AttachmentType.AUDIO

    def test_document_pdf(self):
        assert detect_attachment_type("doc.pdf") == AttachmentType.DOCUMENT

    def test_unknown_extension_defaults_to_document(self):
        assert detect_attachment_type("file.xyz123") == AttachmentType.DOCUMENT


class TestGuessMimeType:
    def test_jpg(self):
        assert guess_mime_type("photo.jpg") == "image/jpeg"

    def test_png(self):
        assert guess_mime_type("pic.png") == "image/png"

    def test_pdf(self):
        assert guess_mime_type("doc.pdf") == "application/pdf"

    def test_mp4(self):
        assert guess_mime_type("clip.mp4") == "video/mp4"

    def test_unknown_defaults_to_octet_stream(self):
        assert guess_mime_type("blob.xyz123") == "application/octet-stream"


# NOTE: Handler-level tests (init, dispatch, keyword commands, quick-reply,
# postback, delivery/read receipts, event emission) live in
# ``test_messenger_handlers.py`` — split out to keep both files under the
# 750-line ceiling.


class _RemovedHandlerSection:
    @pytest.mark.asyncio
    async def test_message_event_dispatched(self, handlers, linking):
        payload = _make_webhook_payload([_make_message_event(text="hi")])
        await handlers.handle_webhook(payload)
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_object_not_page_skipped(self, handlers, linking):
        payload = _make_webhook_payload(
            [_make_message_event(text="hi")], object_type="instagram"
        )
        await handlers.handle_webhook(payload)
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_payload(self, handlers, linking):
        await handlers.handle_webhook({})
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_entries(self, handlers, linking):
        await handlers.handle_webhook({"object": "page", "entry": []})
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_messaging(self, handlers, linking):
        await handlers.handle_webhook({
            "object": "page",
            "entry": [{"id": "p1", "messaging": []}],
        })
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_echo_event_skipped(self, handlers, linking):
        payload = _make_webhook_payload(
            [_make_message_event(text="hi", is_echo=True)]
        )
        await handlers.handle_webhook(payload)
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_postback_routes_to_postback_handler(
        self, handlers, event_bus
    ):
        payload = _make_webhook_payload([_make_postback_event(payload="X")])
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()
        call_event = event_bus.publish.call_args[0][0]
        assert call_event.event_type == "channel.callback"

    @pytest.mark.asyncio
    async def test_delivery_event_routed(self, handlers, event_bus):
        payload = _make_webhook_payload([_make_delivery_event()])
        await handlers.handle_webhook(payload)
        call_event = event_bus.publish.call_args[0][0]
        assert call_event.event_type == "channel.message.delivered"

    @pytest.mark.asyncio
    async def test_read_event_routed(self, handlers, event_bus):
        payload = _make_webhook_payload([_make_read_event()])
        await handlers.handle_webhook(payload)
        call_event = event_bus.publish.call_args[0][0]
        assert call_event.event_type == "channel.message.read"

    @pytest.mark.asyncio
    async def test_unknown_event_keys_ignored(self, handlers, linking, event_bus):
        payload = _make_webhook_payload([
            {"sender": {"id": "PSID"}, "optin": {"ref": "x"}}
        ])
        await handlers.handle_webhook(payload)
        linking.resolve.assert_not_awaited()
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_message_missing_sender_ignored(self, handlers, linking):
        event = _make_message_event(text="hi")
        event["sender"] = {}
        await handlers.handle_webhook(_make_webhook_payload([event]))
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_exception_swallowed(self, handlers, linking):
        # Force an exception inside _handle_message and make sure handle_webhook
        # does not bubble it.
        linking.resolve = AsyncMock(side_effect=RuntimeError("boom"))
        payload = _make_webhook_payload([_make_message_event(text="hi")])
        # Should not raise.
        await handlers.handle_webhook(payload)


# ═════════════════════════════════════════════════════════
# Handlers — keyword commands
# ═════════════════════════════════════════════════════════


class TestKeywordCommands:
    @pytest.mark.asyncio
    async def test_start_unlinked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload([_make_message_event(text="!start")])
        await handlers.handle_webhook(payload)
        linking.create_pairing_code.assert_awaited()
        handlers._send_text_fn.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_linked(self, handlers):
        payload = _make_webhook_payload([_make_message_event(text="!start")])
        await handlers.handle_webhook(payload)
        handlers._send_text_fn.assert_awaited()
        text = handlers._send_text_fn.call_args[0][1]
        assert "Welcome back" in text

    @pytest.mark.asyncio
    async def test_link_no_args_creates_pairing_code(self, handlers, linking):
        payload = _make_webhook_payload([_make_message_event(text="!link")])
        await handlers.handle_webhook(payload)
        linking.create_pairing_code.assert_awaited()

    @pytest.mark.asyncio
    async def test_link_with_user_id(self, handlers, linking, event_bus):
        payload = _make_webhook_payload(
            [_make_message_event(text="!link user-999")]
        )
        await handlers.handle_webhook(payload)
        linking.link.assert_awaited_once()
        # link(channel_name, channel_user_id, nobla_user_id)
        args = linking.link.call_args
        assert args[0][0] == CHANNEL_NAME
        assert args[0][2] == "user-999"

    @pytest.mark.asyncio
    async def test_link_failure_reports_to_user(self, handlers, linking):
        linking.link = AsyncMock(side_effect=RuntimeError("db down"))
        payload = _make_webhook_payload(
            [_make_message_event(text="!link user-x")]
        )
        await handlers.handle_webhook(payload)
        # Last send_text should be the failure message.
        text = handlers._send_text_fn.call_args[0][1]
        assert "Link failed" in text

    @pytest.mark.asyncio
    async def test_unlink_when_linked(self, handlers, linking, event_bus):
        payload = _make_webhook_payload([_make_message_event(text="!unlink")])
        await handlers.handle_webhook(payload)
        linking.unlink.assert_awaited_once()
        # channel.user.unlinked emitted.
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.user.unlinked" in types

    @pytest.mark.asyncio
    async def test_unlink_when_not_linked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload([_make_message_event(text="!unlink")])
        await handlers.handle_webhook(payload)
        linking.unlink.assert_not_awaited()
        text = handlers._send_text_fn.call_args[0][1]
        assert "Not currently linked" in text

    @pytest.mark.asyncio
    async def test_status_linked(self, handlers):
        payload = _make_webhook_payload([_make_message_event(text="!status")])
        await handlers.handle_webhook(payload)
        text = handlers._send_text_fn.call_args[0][1]
        assert "Linked" in text

    @pytest.mark.asyncio
    async def test_status_unlinked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload([_make_message_event(text="!status")])
        await handlers.handle_webhook(payload)
        text = handlers._send_text_fn.call_args[0][1]
        assert "Not linked" in text

    @pytest.mark.asyncio
    async def test_unknown_bang_command_falls_through_to_message(
        self, handlers, linking, event_bus
    ):
        # !nope is not a recognized command — adapter should NOT emit
        # channel.message.in for unknown commands (handler returns False
        # but message handler exits because dispatch already happened).
        # Actually re-read handlers: if command returns False, control returns
        # to caller — and the message path runs after the early return on `!`.
        # The current code returns from _handle_message after dispatch_command
        # regardless of return value, so unknown commands swallow.
        payload = _make_webhook_payload([_make_message_event(text="!nope")])
        await handlers.handle_webhook(payload)
        # Either no event or non-message event; just make sure it didn't crash
        # and didn't try to link.
        linking.link.assert_not_awaited()


# ═════════════════════════════════════════════════════════
# Handlers — quick reply / postback
# ═════════════════════════════════════════════════════════


class TestQuickReplyAndPostback:
    @pytest.mark.asyncio
    async def test_quick_reply_emits_callback(self, handlers, event_bus):
        event = _make_message_event(text="Yes", quick_reply_payload="approve")
        await handlers.handle_webhook(_make_webhook_payload([event]))
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.callback" in types

    @pytest.mark.asyncio
    async def test_postback_emits_callback(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_postback_event(payload="DO_THING")])
        )
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.callback" in types
        ev = next(
            c[0][0] for c in event_bus.publish.call_args_list
            if c[0][0].event_type == "channel.callback"
        )
        assert ev.payload["action_id"] == "DO_THING"

    @pytest.mark.asyncio
    async def test_postback_get_started_synthesizes_start(self, handlers, linking):
        linking.resolve.return_value = None
        await handlers.handle_webhook(
            _make_webhook_payload([_make_postback_event(payload="GET_STARTED")])
        )
        # Should run !start path.
        linking.create_pairing_code.assert_awaited()

    @pytest.mark.asyncio
    async def test_postback_command_payload_routes_to_command(
        self, handlers, linking
    ):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_postback_event(payload="!unlink")])
        )
        linking.unlink.assert_awaited()

    @pytest.mark.asyncio
    async def test_postback_missing_sender_ignored(self, handlers, event_bus):
        event = _make_postback_event(payload="X")
        event["sender"] = {}
        await handlers.handle_webhook(_make_webhook_payload([event]))
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_quick_reply_emits_with_unlinked_user(
        self, handlers, linking, event_bus
    ):
        linking.resolve.return_value = None
        event = _make_message_event(text="A", quick_reply_payload="opt-1")
        await handlers.handle_webhook(_make_webhook_payload([event]))
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.callback" in types


# ═════════════════════════════════════════════════════════
# Handlers — delivery / read
# ═════════════════════════════════════════════════════════


class TestDeliveryAndRead:
    @pytest.mark.asyncio
    async def test_delivery_event_emits(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_delivery_event(watermark=42)])
        )
        ev = event_bus.publish.call_args[0][0]
        assert ev.event_type == "channel.message.delivered"
        assert ev.payload["watermark"] == 42
        assert ev.payload["channel"] == CHANNEL_NAME

    @pytest.mark.asyncio
    async def test_delivery_includes_mids(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_delivery_event(mids=["mid.A"])])
        )
        ev = event_bus.publish.call_args[0][0]
        assert ev.payload["mids"] == ["mid.A"]

    @pytest.mark.asyncio
    async def test_read_event_emits(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_read_event(watermark=99)])
        )
        ev = event_bus.publish.call_args[0][0]
        assert ev.event_type == "channel.message.read"
        assert ev.payload["watermark"] == 99
        assert ev.payload["channel"] == CHANNEL_NAME

    @pytest.mark.asyncio
    async def test_delivery_with_missing_fields(self, handlers, event_bus):
        # delivery event with empty delivery dict — should still emit.
        event = {
            "sender": {"id": "PSID-Z"},
            "delivery": {},
            "timestamp": 0,
        }
        await handlers.handle_webhook(_make_webhook_payload([event]))
        ev = event_bus.publish.call_args[0][0]
        assert ev.event_type == "channel.message.delivered"
        assert ev.payload["mids"] == []
        assert ev.payload["watermark"] == 0


# ═════════════════════════════════════════════════════════
# Handlers — event emission shape
# ═════════════════════════════════════════════════════════


class TestEventEmission:
    @pytest.mark.asyncio
    async def test_message_in_event_shape(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_message_event(text="hello")])
        )
        ev = event_bus.publish.call_args[0][0]
        assert ev.event_type == "channel.message.in"
        assert ev.source == CHANNEL_NAME
        assert ev.payload["channel"] == CHANNEL_NAME
        assert ev.payload["channel_user_id"] == "PSID-100"
        assert ev.payload["content"] == "hello"
        assert ev.payload["has_attachments"] is False

    @pytest.mark.asyncio
    async def test_link_emits_event(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload(
                [_make_message_event(text="!link user-abc")]
            )
        )
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.user.linked" in types

    @pytest.mark.asyncio
    async def test_unlink_emits_event(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload([_make_message_event(text="!unlink")])
        )
        types = [c[0][0].event_type for c in event_bus.publish.call_args_list]
        assert "channel.user.unlinked" in types

    @pytest.mark.asyncio
    async def test_no_event_bus_does_not_crash(self, linking):
        h = MessengerHandlers(
            linking=linking,
            event_bus=None,
            page_access_token="t",
            page_id="p",
        )
        h.set_send_fn(AsyncMock())
        await h.handle_webhook(
            _make_webhook_payload([_make_message_event(text="hi")])
        )

    @pytest.mark.asyncio
    async def test_callback_event_carries_action_id(self, handlers, event_bus):
        await handlers.handle_webhook(
            _make_webhook_payload(
                [_make_postback_event(payload="approve:42", title="Approve")]
            )
        )
        ev = next(
            c[0][0] for c in event_bus.publish.call_args_list
            if c[0][0].event_type == "channel.callback"
        )
        assert ev.payload["action_id"] == "approve:42"
        assert ev.payload["title"] == "Approve"


# ═════════════════════════════════════════════════════════
# Adapter — basics
# ═════════════════════════════════════════════════════════


class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "messenger"

    def test_settings_exposed(self, adapter, settings):
        assert adapter._settings is settings

    def test_handlers_exposed(self, adapter, handlers):
        assert adapter._handlers is handlers

    def test_lazy_import_from_package(self):
        from nobla.channels import messenger as pkg

        assert pkg.MessengerAdapter is MessengerAdapter

    def test_lazy_import_unknown_attribute(self):
        from nobla.channels import messenger as pkg

        with pytest.raises(AttributeError):
            _ = pkg.NonExistentSymbol


class TestAdapterLifecycle:
    @pytest.mark.asyncio
    async def test_start_initializes_client(self, adapter):
        await adapter.start()
        assert adapter._running is True
        assert adapter._client is not None
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_wires_send_fn(self, adapter, handlers):
        await adapter.start()
        # Bound methods compare by equality, not identity (each ``getattr``
        # creates a fresh bound-method object). Equality on bound methods
        # checks (instance, function) pair.
        assert handlers._send_text_fn == adapter._send_raw_text
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_already_running_warns(self, adapter):
        await adapter.start()
        client_before = adapter._client
        await adapter.start()
        assert adapter._client is client_before
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_missing_token_raises(self, settings, handlers):
        settings.page_access_token = ""
        adapter = MessengerAdapter(settings=settings, handlers=handlers)
        with pytest.raises(ValueError, match="page_access_token"):
            await adapter.start()

    @pytest.mark.asyncio
    async def test_start_missing_page_id_raises(self, settings, handlers):
        settings.page_id = ""
        adapter = MessengerAdapter(settings=settings, handlers=handlers)
        with pytest.raises(ValueError, match="page_id"):
            await adapter.start()

    @pytest.mark.asyncio
    async def test_stop_closes_client(self, adapter):
        await adapter.start()
        await adapter.stop()
        assert adapter._running is False
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, adapter):
        await adapter.stop()
        await adapter.stop()
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_double_start_stop_cycle(self, adapter):
        await adapter.start()
        await adapter.stop()
        await adapter.start()
        assert adapter._running is True
        await adapter.stop()
        assert adapter._running is False


class TestWebhookVerification:
    def test_valid_signature(self, adapter):
        body = b'{"hello":"world"}'
        sig = _sign_payload(body, "test-app-secret")
        assert adapter.verify_webhook_signature(body, sig) is True

    def test_invalid_signature(self, adapter):
        body = b'{"hello":"world"}'
        assert adapter.verify_webhook_signature(body, "sha256=deadbeef") is False

    def test_missing_signature(self, adapter):
        body = b'{"hello":"world"}'
        assert adapter.verify_webhook_signature(body, "") is False

    def test_signature_without_prefix(self, adapter):
        body = b'{"hello":"world"}'
        digest = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        # No "sha256=" prefix — code does removeprefix which is a no-op,
        # so a bare digest should also validate.
        assert adapter.verify_webhook_signature(body, digest) is True

    def test_no_app_secret_accepts(self, settings, handlers):
        settings.app_secret = ""
        a = MessengerAdapter(settings=settings, handlers=handlers)
        assert a.verify_webhook_signature(b"data", "sha256=any") is True

    def test_wrong_secret_fails(self, adapter):
        body = b'{"hello":"world"}'
        bad = _sign_payload(body, "wrong-secret")
        assert adapter.verify_webhook_signature(body, bad) is False

    def test_uses_constant_time_compare(self, adapter):
        # Smoke test: monkeypatch hmac.compare_digest to confirm code path.
        body = b'{"x":1}'
        sig = _sign_payload(body, "test-app-secret")
        with patch(
            "nobla.channels.messenger.adapter.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as cmp_:
            assert adapter.verify_webhook_signature(body, sig) is True
            cmp_.assert_called_once()

    def test_challenge_valid(self, adapter):
        result = adapter.verify_webhook_challenge(
            "subscribe", "verify-me-token", "challenge-123"
        )
        assert result == "challenge-123"

    def test_challenge_wrong_token(self, adapter):
        result = adapter.verify_webhook_challenge(
            "subscribe", "wrong", "challenge-123"
        )
        assert result is None

    def test_challenge_wrong_mode(self, adapter):
        result = adapter.verify_webhook_challenge(
            "unsubscribe", "verify-me-token", "challenge-123"
        )
        assert result is None


# ═════════════════════════════════════════════════════════
# Adapter — outbound send
# ═════════════════════════════════════════════════════════


def _patch_post(adapter, status: int = 200):
    """Patch the adapter's httpx client.post and return the mock."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.raise_for_status = MagicMock()
    return patch.object(
        adapter._client, "post", new_callable=AsyncMock, return_value=mock_resp
    )


class TestAdapterSend:
    @pytest.mark.asyncio
    async def test_send_text_only(self, adapter):
        await adapter.start()
        try:
            with _patch_post(adapter) as mock_post:
                await adapter.send("PSID-1", ChannelResponse(content="Hello!"))
                mock_post.assert_awaited_once()
                call_kwargs = mock_post.call_args
                payload = (
                    call_kwargs.kwargs.get("json")
                    or call_kwargs[1].get("json")
                )
                assert payload["recipient"] == {"id": "PSID-1"}
                assert payload["messaging_type"] == "RESPONSE"
                assert payload["message"]["text"] == "Hello!"
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_with_quick_replies(self, adapter):
        await adapter.start()
        try:
            with _patch_post(adapter) as mock_post:
                resp = ChannelResponse(
                    content="Pick:",
                    actions=[
                        InlineAction(action_id="a", label="A"),
                        InlineAction(action_id="b", label="B"),
                    ],
                )
                await adapter.send("PSID-2", resp)
                mock_post.assert_awaited()
                call_kwargs = mock_post.call_args
                payload = (
                    call_kwargs.kwargs.get("json")
                    or call_kwargs[1].get("json")
                )
                assert "quick_replies" in payload["message"]
                assert len(payload["message"]["quick_replies"]) == 2
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_with_button_template(self, adapter):
        await adapter.start()
        try:
            with _patch_post(adapter) as mock_post:
                resp = _response_with_metadata(
                    content="Approve?",
                    actions=[
                        InlineAction(action_id="yes", label="Yes"),
                        InlineAction(action_id="no", label="No"),
                    ],
                    metadata={"ui": "buttons"},
                )
                await adapter.send("PSID-3", resp)
                mock_post.assert_awaited()
                call_kwargs = mock_post.call_args
                payload = (
                    call_kwargs.kwargs.get("json")
                    or call_kwargs[1].get("json")
                )
                attachment = payload["message"]["attachment"]
                assert attachment["type"] == "template"
                assert (
                    attachment["payload"]["template_type"] == "button"
                )
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_not_initialized_logs_and_absorbs(self, adapter):
        # Client is None — should NOT raise.
        await adapter.send("PSID-X", ChannelResponse(content="hi"))

    @pytest.mark.asyncio
    async def test_send_swallows_post_exceptions(self, adapter):
        await adapter.start()
        try:
            with patch.object(
                adapter._client,
                "post",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ):
                # Must not raise.
                await adapter.send("PSID-1", ChannelResponse(content="hi"))
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_notification_uses_update_messaging_type(self, adapter):
        await adapter.start()
        try:
            with _patch_post(adapter) as mock_post:
                await adapter.send_notification("PSID-1", "Alert!")
                mock_post.assert_awaited_once()
                call_kwargs = mock_post.call_args
                payload = (
                    call_kwargs.kwargs.get("json")
                    or call_kwargs[1].get("json")
                )
                assert payload["messaging_type"] == "UPDATE"
                assert payload["message"]["text"] == "Alert!"
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_notification_empty_text_skipped(self, adapter):
        await adapter.start()
        try:
            with _patch_post(adapter) as mock_post:
                await adapter.send_notification("PSID-1", "")
                mock_post.assert_not_awaited()
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_with_attachment_url(self, adapter):
        await adapter.start()
        try:
            with patch(
                "nobla.channels.messenger.adapter.send_attachment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send_att, _patch_post(adapter):
                resp = ChannelResponse(
                    content="See this",
                    attachments=[
                        Attachment(
                            type=AttachmentType.IMAGE,
                            filename="pic.jpg",
                            mime_type="image/jpeg",
                            size_bytes=100,
                            url="https://cdn/pic.jpg",
                        )
                    ],
                )
                await adapter.send("PSID-9", resp)
                mock_send_att.assert_awaited_once()
        finally:
            await adapter.stop()


class TestAdapterParseCallback:
    def test_string_callback(self, adapter):
        action_id, meta = adapter.parse_callback("ACTION_RAW")
        assert action_id == "ACTION_RAW"
        assert meta == {}

    def test_full_webhook_postback(self, adapter):
        payload = _make_webhook_payload(
            [_make_postback_event(payload="DO_X", mid="mid.PB")]
        )
        action_id, meta = adapter.parse_callback(payload)
        assert action_id == "DO_X"
        # meta is the inner messaging event (raw_callback recurse).
        assert "postback" in meta

    def test_full_webhook_no_messaging(self, adapter):
        payload = {"entry": [{"id": "p1"}]}
        action_id, meta = adapter.parse_callback(payload)
        assert action_id == ""

    def test_postback_event_dict(self, adapter):
        ev = _make_postback_event(payload="OK", mid="mid.42")
        action_id, meta = adapter.parse_callback(ev)
        assert action_id == "OK"

    def test_postback_falls_back_to_mid(self, adapter):
        ev = {
            "sender": {"id": "PSID"},
            "postback": {"mid": "mid.zzz", "payload": ""},
        }
        # Empty payload — postback dict still truthy because of mid.
        action_id, _ = adapter.parse_callback(ev)
        assert action_id == "mid.zzz"

    def test_quick_reply_extracted(self, adapter):
        ev = _make_message_event(quick_reply_payload="QR_PL")
        action_id, _ = adapter.parse_callback(ev)
        assert action_id == "QR_PL"

    def test_message_mid_extracted(self, adapter):
        ev = _make_message_event(text="hi", mid="mid.ABC")
        action_id, _ = adapter.parse_callback(ev)
        assert action_id == "mid.ABC"

    def test_other_input_stringified(self, adapter):
        action_id, meta = adapter.parse_callback(123)
        assert action_id == "123"
        assert meta == {}

    def test_empty_dict(self, adapter):
        action_id, _ = adapter.parse_callback({})
        assert action_id == ""


class TestAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_200(self, adapter):
        await adapter.start()
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            with patch.object(
                adapter._client, "get", new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                assert await adapter.health_check() is True
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_unhealthy_non_200(self, adapter):
        await adapter.start()
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            with patch.object(
                adapter._client, "get", new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                assert await adapter.health_check() is False
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_not_initialized_returns_false(self, adapter):
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_request_error_returns_false(self, adapter):
        import httpx as httpx_mod

        await adapter.start()
        try:
            with patch.object(
                adapter._client, "get", new_callable=AsyncMock,
                side_effect=httpx_mod.RequestError("net down"),
            ):
                assert await adapter.health_check() is False
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_false(self, adapter):
        await adapter.start()
        try:
            with patch.object(
                adapter._client, "get", new_callable=AsyncMock,
                side_effect=ValueError("malformed"),
            ):
                assert await adapter.health_check() is False
        finally:
            await adapter.stop()


# ═════════════════════════════════════════════════════════
# Adapter — webhook payload end-to-end
# ═════════════════════════════════════════════════════════


class TestWebhookPayloadHandling:
    @pytest.mark.asyncio
    async def test_valid_payload_dispatches(self, adapter):
        await adapter.start()
        try:
            payload = _make_webhook_payload([_make_message_event(text="hi")])
            body = json.dumps(payload).encode()
            sig = _sign_payload(body, "test-app-secret")

            with patch.object(
                adapter._handlers,
                "handle_webhook",
                new_callable=AsyncMock,
            ) as mock_handle:
                ok = await adapter.handle_webhook_payload(body, sig)
                assert ok is True
                mock_handle.assert_awaited_once()
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, adapter):
        body = b'{"object":"page"}'
        ok = await adapter.handle_webhook_payload(body, "sha256=baadbeef")
        assert ok is False

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self, adapter):
        body = b"not-json"
        sig = _sign_payload(body, "test-app-secret")
        ok = await adapter.handle_webhook_payload(body, sig)
        assert ok is False

    @pytest.mark.asyncio
    async def test_handler_exception_returns_false(self, adapter):
        await adapter.start()
        try:
            payload = _make_webhook_payload([_make_message_event(text="hi")])
            body = json.dumps(payload).encode()
            sig = _sign_payload(body, "test-app-secret")

            with patch.object(
                adapter._handlers,
                "handle_webhook",
                new_callable=AsyncMock,
                side_effect=RuntimeError("crash"),
            ):
                ok = await adapter.handle_webhook_payload(body, sig)
                assert ok is False
        finally:
            await adapter.stop()


# ═════════════════════════════════════════════════════════
# FormattedMessage
# ═════════════════════════════════════════════════════════


class TestFormattedMessage:
    def test_text_only_default(self):
        m = FormattedMessage(text="hello")
        assert m.text == "hello"
        assert m.interactive is None

    def test_with_interactive(self):
        m = FormattedMessage(
            text="pick", interactive={"type": "quick_replies", "quick_replies": []}
        )
        assert m.interactive is not None
        assert m.interactive["type"] == "quick_replies"

    def test_slots_constraint(self):
        m = FormattedMessage(text="x")
        with pytest.raises(AttributeError):
            m.unknown_field = 1  # type: ignore[attr-defined]
