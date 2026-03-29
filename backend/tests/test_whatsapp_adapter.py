"""Tests for the WhatsApp Business Cloud API channel adapter (Phase 5-Channels).

Covers: adapter lifecycle, webhook verification, handlers (message dispatch,
keyword commands, interactive replies, reactions, status updates),
formatter, media, linking/pairing, and edge cases.
"""

from __future__ import annotations

import hashlib
import hmac
import json
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
from nobla.channels.whatsapp.adapter import WhatsAppAdapter
from nobla.channels.whatsapp.formatter import (
    FormattedMessage,
    InteractiveButton,
    ListRow,
    build_interactive_payload,
    build_list_payload,
    build_reply_buttons,
    escape_whatsapp_text,
    format_response,
    split_message,
)
from nobla.channels.whatsapp.handlers import WhatsAppHandlers
from nobla.channels.whatsapp.media import (
    detect_attachment_type,
    guess_mime_type,
)
from nobla.channels.whatsapp.models import (
    CHANNEL_NAME,
    MAX_BUTTONS,
    MAX_MESSAGE_LENGTH,
    MESSAGE_STATUSES,
    SUPPORTED_MESSAGE_TYPES,
    WhatsAppUserContext,
)


# ── Fixtures ──────────────────────────────────────────────


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


@dataclass
class FakeSettings:
    enabled: bool = True
    access_token: str = "test-token"
    phone_number_id: str = "123456789"
    business_account_id: str = "biz-111"
    app_secret: str = "test-secret"
    verify_token: str = "verify-me"
    webhook_path: str = "/webhook/whatsapp"
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
    h = WhatsAppHandlers(
        linking=linking,
        event_bus=event_bus,
        access_token="test-token",
        phone_number_id="123456789",
        api_version="v21.0",
        max_file_size_mb=100,
    )
    h.set_send_fn(AsyncMock())
    h.set_bot_phone("123456789")
    return h


@pytest.fixture
def adapter(settings, handlers):
    return WhatsAppAdapter(settings=settings, handlers=handlers)


def _make_webhook_payload(
    text: str = "hello",
    wa_id: str = "5551234",
    msg_id: str = "wamid.test123",
    msg_type: str = "text",
) -> dict:
    """Build a minimal Cloud API webhook payload."""
    message: dict[str, Any] = {
        "from": wa_id,
        "id": msg_id,
        "timestamp": "1700000000",
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz-111",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001234",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [
                                {
                                    "wa_id": wa_id,
                                    "profile": {"name": "Test User"},
                                }
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def _sign_payload(body: bytes, secret: str) -> str:
    """Compute X-Hub-Signature-256 for a payload."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ═════════════════════════════════════════════════════════
# Models
# ═════════════════════════════════════════════════════════


class TestWhatsAppUserContext:
    def test_basic_properties(self):
        ctx = WhatsAppUserContext(
            wa_id="5551234", display_name="Alice",
            message_id="wamid.1", chat_id="5551234",
        )
        assert ctx.user_id_str == "5551234"
        assert ctx.chat_id_str == "5551234"
        assert ctx.display_name == "Alice"
        assert ctx.is_group is False
        assert ctx.is_bot_mentioned is False

    def test_group_context(self):
        ctx = WhatsAppUserContext(
            wa_id="5551234", display_name="Bob",
            message_id="wamid.2", chat_id="group-jid",
            is_group=True, is_bot_mentioned=True,
        )
        assert ctx.is_group is True
        assert ctx.is_bot_mentioned is True
        assert ctx.chat_id_str == "group-jid"

    def test_raw_extras(self):
        ctx = WhatsAppUserContext(
            wa_id="5551234", display_name="Eve",
            message_id="wamid.3", chat_id="5551234",
            raw_extras={"key": "value"},
        )
        assert ctx.raw_extras == {"key": "value"}


class TestConstants:
    def test_channel_name(self):
        assert CHANNEL_NAME == "whatsapp"

    def test_supported_message_types(self):
        assert "text" in SUPPORTED_MESSAGE_TYPES
        assert "image" in SUPPORTED_MESSAGE_TYPES
        assert "interactive" in SUPPORTED_MESSAGE_TYPES
        assert "unsupported_type" not in SUPPORTED_MESSAGE_TYPES

    def test_message_statuses(self):
        for status in ("sent", "delivered", "read", "failed"):
            assert status in MESSAGE_STATUSES

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 4096

    def test_max_buttons(self):
        assert MAX_BUTTONS == 3


# ═════════════════════════════════════════════════════════
# Formatter
# ═════════════════════════════════════════════════════════


class TestEscapeWhatsAppText:
    def test_escapes_bold(self):
        assert escape_whatsapp_text("*bold*") == r"\*bold\*"

    def test_escapes_italic(self):
        assert escape_whatsapp_text("_italic_") == r"\_italic\_"

    def test_escapes_strike(self):
        assert escape_whatsapp_text("~strike~") == r"\~strike\~"

    def test_escapes_code(self):
        assert escape_whatsapp_text("`code`") == r"\`code\`"

    def test_plain_text_unchanged(self):
        assert escape_whatsapp_text("hello world") == "hello world"

    def test_mixed_escaping(self):
        result = escape_whatsapp_text("*bold* and _italic_")
        assert r"\*" in result
        assert r"\_" in result


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


class TestBuildReplyButtons:
    def test_builds_buttons(self):
        actions = [
            InlineAction(action_id="approve", label="Approve"),
            InlineAction(action_id="deny", label="Deny"),
        ]
        buttons = build_reply_buttons(actions)
        assert len(buttons) == 2
        assert buttons[0].id == "approve"
        assert buttons[0].title == "Approve"

    def test_max_buttons_capped(self):
        actions = [
            InlineAction(action_id=f"btn{i}", label=f"Button {i}")
            for i in range(5)
        ]
        buttons = build_reply_buttons(actions)
        assert len(buttons) == MAX_BUTTONS

    def test_truncates_long_title(self):
        actions = [InlineAction(action_id="x", label="A" * 50)]
        buttons = build_reply_buttons(actions)
        assert len(buttons[0].title) == 20

    def test_empty_actions(self):
        assert build_reply_buttons([]) == []


class TestBuildInteractivePayload:
    def test_button_payload_structure(self):
        buttons = [InteractiveButton(id="yes", title="Yes")]
        payload = build_interactive_payload("Choose:", buttons)
        assert payload["type"] == "button"
        assert payload["body"]["text"] == "Choose:"
        assert len(payload["action"]["buttons"]) == 1
        assert payload["action"]["buttons"][0]["reply"]["id"] == "yes"

    def test_multiple_buttons(self):
        buttons = [
            InteractiveButton(id="a", title="A"),
            InteractiveButton(id="b", title="B"),
            InteractiveButton(id="c", title="C"),
        ]
        payload = build_interactive_payload("Pick:", buttons)
        assert len(payload["action"]["buttons"]) == 3


class TestBuildListPayload:
    def test_list_payload_structure(self):
        rows = [ListRow(id="r1", title="Row 1", description="Desc")]
        payload = build_list_payload("Body", "View", rows)
        assert payload["type"] == "list"
        assert payload["body"]["text"] == "Body"
        assert payload["action"]["button"] == "View"
        assert len(payload["action"]["sections"][0]["rows"]) == 1

    def test_with_header(self):
        rows = [ListRow(id="r1", title="Row 1")]
        payload = build_list_payload("Body", "View", rows, header="Title")
        assert payload["header"]["text"] == "Title"

    def test_without_header(self):
        rows = [ListRow(id="r1", title="Row 1")]
        payload = build_list_payload("Body", "View", rows)
        assert "header" not in payload


class TestFormatResponse:
    def test_simple_text(self):
        resp = ChannelResponse(content="Hello!")
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello!"
        assert msgs[0].interactive is None

    def test_empty_content(self):
        resp = ChannelResponse(content="")
        assert format_response(resp) == []

    def test_with_buttons(self):
        resp = ChannelResponse(
            content="Approve?",
            actions=[
                InlineAction(action_id="yes", label="Yes"),
                InlineAction(action_id="no", label="No"),
            ],
        )
        msgs = format_response(resp)
        assert len(msgs) == 1
        assert msgs[0].interactive is not None
        assert msgs[0].interactive["type"] == "button"

    def test_long_text_with_buttons_on_last_chunk(self):
        resp = ChannelResponse(
            content="x" * 5000,
            actions=[InlineAction(action_id="ok", label="OK")],
        )
        msgs = format_response(resp)
        assert len(msgs) >= 2
        # Only last chunk gets buttons
        for msg in msgs[:-1]:
            assert msg.interactive is None
        assert msgs[-1].interactive is not None


# ═════════════════════════════════════════════════════════
# Media
# ═════════════════════════════════════════════════════════


class TestDetectAttachmentType:
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


class TestGuessMimeType:
    def test_known_extension(self):
        assert guess_mime_type("photo.jpg") in ("image/jpeg",)
        assert guess_mime_type("doc.pdf") == "application/pdf"

    def test_unknown_extension(self):
        assert guess_mime_type("file.xyz123") == "application/octet-stream"


# ═════════════════════════════════════════════════════════
# Handlers
# ═════════════════════════════════════════════════════════


class TestWhatsAppHandlersInit:
    def test_init(self, handlers):
        assert handlers._access_token == "test-token"
        assert handlers._phone_number_id == "123456789"

    def test_set_bot_phone(self, handlers):
        handlers.set_bot_phone("987654321")
        assert handlers._bot_phone == "987654321"


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_text_message(self, handlers, linking):
        payload = _make_webhook_payload(text="hello")
        await handlers.handle_webhook(payload)
        # Should resolve user
        linking.resolve.assert_awaited()

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_code(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload(text="hello")
        await handlers.handle_webhook(payload)
        linking.create_pairing_code.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_messages_field(self, handlers, linking):
        payload = {
            "entry": [{"changes": [{"field": "other", "value": {}}]}]
        }
        await handlers.handle_webhook(payload)
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_payload(self, handlers, linking):
        await handlers.handle_webhook({})
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unsupported_message_type(self, handlers, linking):
        payload = _make_webhook_payload(msg_type="unsupported_type_xyz")
        # Patch message type to something unsupported
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "order"
        await handlers.handle_webhook(payload)
        # Should not try to resolve
        linking.resolve.assert_not_awaited()


class TestKeywordCommands:
    @pytest.mark.asyncio
    async def test_start_command_unlinked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload(text="!start")
        await handlers.handle_webhook(payload)
        linking.create_pairing_code.assert_awaited()
        handlers._send_text_fn.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_command_linked(self, handlers, linking):
        payload = _make_webhook_payload(text="!start")
        await handlers.handle_webhook(payload)
        handlers._send_text_fn.assert_awaited()
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "Welcome back" in call_text

    @pytest.mark.asyncio
    async def test_link_no_args(self, handlers, linking):
        payload = _make_webhook_payload(text="!link")
        await handlers.handle_webhook(payload)
        linking.create_pairing_code.assert_awaited()

    @pytest.mark.asyncio
    async def test_link_with_user_id(self, handlers, linking, event_bus):
        payload = _make_webhook_payload(text="!link user-999")
        await handlers.handle_webhook(payload)
        linking.link.assert_awaited_once()
        args = linking.link.call_args
        assert args[0][2] == "user-999"  # nobla_user_id

    @pytest.mark.asyncio
    async def test_unlink_linked(self, handlers, linking, event_bus):
        payload = _make_webhook_payload(text="!unlink")
        await handlers.handle_webhook(payload)
        linking.unlink.assert_awaited_once()
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_unlink_not_linked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload(text="!unlink")
        await handlers.handle_webhook(payload)
        linking.unlink.assert_not_awaited()
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "Not currently linked" in call_text

    @pytest.mark.asyncio
    async def test_status_linked(self, handlers, linking):
        payload = _make_webhook_payload(text="!status")
        await handlers.handle_webhook(payload)
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "Linked" in call_text

    @pytest.mark.asyncio
    async def test_status_unlinked(self, handlers, linking):
        linking.resolve.return_value = None
        payload = _make_webhook_payload(text="!status")
        await handlers.handle_webhook(payload)
        call_text = handlers._send_text_fn.call_args[0][1]
        assert "Not linked" in call_text


class TestInteractiveReplies:
    @pytest.mark.asyncio
    async def test_button_reply(self, handlers, event_bus):
        payload = _make_webhook_payload(msg_type="interactive")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["interactive"] = {
            "type": "button_reply",
            "button_reply": {"id": "approve:req-1:yes", "title": "Yes"},
        }
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_list_reply(self, handlers, event_bus):
        payload = _make_webhook_payload(msg_type="interactive")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["interactive"] = {
            "type": "list_reply",
            "list_reply": {"id": "option-1", "title": "Option 1"},
        }
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_button_payload(self, handlers, event_bus):
        payload = _make_webhook_payload(msg_type="button")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["button"] = {"text": "Click", "payload": "action:123:do"}
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()


class TestReactions:
    @pytest.mark.asyncio
    async def test_reaction_event(self, handlers, event_bus):
        payload = _make_webhook_payload(msg_type="reaction")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["reaction"] = {"emoji": "\u0001f44d", "message_id": "wamid.original"}
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_reaction_unlinked_ignored(self, handlers, linking, event_bus):
        linking.resolve.return_value = None
        payload = _make_webhook_payload(msg_type="reaction")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["reaction"] = {"emoji": "\u0001f44d", "message_id": "wamid.original"}
        await handlers.handle_webhook(payload)
        # Should not emit event for unlinked user reaction
        event_bus.publish.assert_not_awaited()


class TestStatusUpdates:
    @pytest.mark.asyncio
    async def test_delivery_status(self, handlers, event_bus):
        payload = {
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "statuses": [{
                            "id": "wamid.123",
                            "status": "delivered",
                            "timestamp": "1700000000",
                            "recipient_id": "5551234",
                        }],
                    },
                }],
            }],
        }
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_read_status(self, handlers, event_bus):
        payload = {
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "statuses": [{
                            "id": "wamid.456",
                            "status": "read",
                            "timestamp": "1700000001",
                            "recipient_id": "5551234",
                        }],
                    },
                }],
            }],
        }
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_unknown_status_ignored(self, handlers, event_bus):
        payload = {
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "statuses": [{
                            "id": "wamid.789",
                            "status": "unknown_status",
                            "timestamp": "1700000002",
                            "recipient_id": "5551234",
                        }],
                    },
                }],
            }],
        }
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_not_awaited()


class TestAttachmentExtraction:
    @pytest.mark.asyncio
    async def test_image_attachment(self, handlers, linking):
        payload = _make_webhook_payload(msg_type="image")
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        msg["image"] = {
            "id": "media-123",
            "mime_type": "image/jpeg",
        }
        with patch(
            "nobla.channels.whatsapp.handlers.download_attachment",
            new_callable=AsyncMock,
            return_value=Attachment(
                type=AttachmentType.IMAGE,
                filename="media-123.jpg",
                mime_type="image/jpeg",
                size_bytes=1024,
                data=b"fake-image",
            ),
        ):
            await handlers.handle_webhook(payload)

    @pytest.mark.asyncio
    async def test_text_message_no_attachments(self, handlers, linking):
        payload = _make_webhook_payload(text="plain text")
        await handlers.handle_webhook(payload)
        # No download_attachment calls for text messages


class TestEventEmission:
    @pytest.mark.asyncio
    async def test_inbound_message_emits_event(self, handlers, event_bus):
        payload = _make_webhook_payload(text="hello")
        await handlers.handle_webhook(payload)
        event_bus.publish.assert_awaited()
        event = event_bus.publish.call_args[0][0]
        assert event.event_type == "channel.message.in"
        assert event.source == CHANNEL_NAME

    @pytest.mark.asyncio
    async def test_link_emits_event(self, handlers, event_bus):
        payload = _make_webhook_payload(text="!link user-abc")
        await handlers.handle_webhook(payload)
        calls = event_bus.publish.call_args_list
        event_types = [c[0][0].event_type for c in calls]
        assert "channel.user.linked" in event_types

    @pytest.mark.asyncio
    async def test_no_event_bus(self, linking):
        h = WhatsAppHandlers(
            linking=linking, event_bus=None,
            access_token="t", phone_number_id="p",
        )
        h.set_send_fn(AsyncMock())
        payload = _make_webhook_payload(text="hello")
        # Should not crash even without event bus
        await h.handle_webhook(payload)


# ═════════════════════════════════════════════════════════
# Adapter
# ═════════════════════════════════════════════════════════


class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "whatsapp"


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
    async def test_start_no_token(self, settings, handlers):
        settings.access_token = ""
        adapter = WhatsAppAdapter(settings=settings, handlers=handlers)
        with pytest.raises(ValueError, match="access_token"):
            await adapter.start()

    @pytest.mark.asyncio
    async def test_start_no_phone_number_id(self, settings, handlers):
        settings.phone_number_id = ""
        adapter = WhatsAppAdapter(settings=settings, handlers=handlers)
        with pytest.raises(ValueError, match="phone_number_id"):
            await adapter.start()

    @pytest.mark.asyncio
    async def test_stop(self, adapter):
        await adapter.start()
        await adapter.stop()
        assert adapter._running is False
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_stop_not_running(self, adapter):
        await adapter.stop()  # Should not crash


class TestWebhookVerification:
    def test_valid_signature(self, adapter):
        body = b'{"test": "payload"}'
        sig = _sign_payload(body, "test-secret")
        assert adapter.verify_webhook_signature(body, sig) is True

    def test_invalid_signature(self, adapter):
        body = b'{"test": "payload"}'
        assert adapter.verify_webhook_signature(body, "sha256=wrong") is False

    def test_no_app_secret(self, settings, handlers):
        settings.app_secret = ""
        adapter = WhatsAppAdapter(settings=settings, handlers=handlers)
        # Should pass without secret (warns)
        assert adapter.verify_webhook_signature(b"data", "sha256=any") is True

    def test_challenge_valid(self, adapter):
        result = adapter.verify_webhook_challenge("subscribe", "verify-me", "challenge123")
        assert result == "challenge123"

    def test_challenge_wrong_token(self, adapter):
        result = adapter.verify_webhook_challenge("subscribe", "wrong", "challenge123")
        assert result is None

    def test_challenge_wrong_mode(self, adapter):
        result = adapter.verify_webhook_challenge("unsubscribe", "verify-me", "challenge123")
        assert result is None


class TestAdapterSend:
    @pytest.mark.asyncio
    async def test_send_text(self, adapter):
        await adapter.start()
        resp = ChannelResponse(content="Hello!")

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            await adapter.send("5551234", resp)
            mock_post.assert_awaited_once()
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["type"] == "text"
            assert payload["to"] == "5551234"

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_interactive(self, adapter):
        await adapter.start()
        resp = ChannelResponse(
            content="Approve?",
            actions=[InlineAction(action_id="yes", label="Yes")],
        )

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            await adapter.send("5551234", resp)
            # Should send interactive message
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["type"] == "interactive"

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_not_initialized(self, adapter):
        resp = ChannelResponse(content="Hello!")
        # Should not crash
        await adapter.send("5551234", resp)

    @pytest.mark.asyncio
    async def test_send_notification(self, adapter):
        await adapter.start()
        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            await adapter.send_notification("5551234", "Alert!")
            mock_post.assert_awaited_once()

        await adapter.stop()


class TestAdapterParseCallback:
    def test_dict_callback(self, adapter):
        action_id, meta = adapter.parse_callback({"id": "action:123", "title": "Yes"})
        assert action_id == "action:123"
        assert meta["title"] == "Yes"

    def test_string_callback(self, adapter):
        action_id, meta = adapter.parse_callback("raw_data")
        assert action_id == "raw_data"
        assert meta == {}


class TestAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, adapter):
        await adapter.start()
        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp

            assert await adapter.health_check() is True

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, adapter):
        await adapter.start()
        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_get.return_value = mock_resp

            assert await adapter.health_check() is False

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, adapter):
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, adapter):
        await adapter.start()
        with patch.object(adapter._client, "get", side_effect=Exception("timeout")):
            assert await adapter.health_check() is False
        await adapter.stop()


class TestWebhookPayloadHandling:
    @pytest.mark.asyncio
    async def test_valid_payload(self, adapter, handlers):
        await adapter.start()
        payload = _make_webhook_payload(text="hi")
        body = json.dumps(payload).encode()
        sig = _sign_payload(body, "test-secret")

        result = await adapter.handle_webhook_payload(body, sig)
        assert result is True
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_invalid_signature(self, adapter):
        body = b'{"test": true}'
        result = await adapter.handle_webhook_payload(body, "sha256=invalid")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_json(self, adapter):
        body = b"not json"
        sig = _sign_payload(body, "test-secret")
        result = await adapter.handle_webhook_payload(body, sig)
        assert result is False
