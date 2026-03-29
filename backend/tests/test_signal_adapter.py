"""Tests for the Signal channel adapter (Phase 5-Channels).

Covers: models/constants, formatter (plain text, split), media (disk save/load),
handlers (envelope dispatch, data messages, receipts, read receipts, commands,
group mentions, disappearing messages, event emission), adapter (JSON-RPC
connection, send, receive, reconnect, health check), and edge cases.
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


# ── Models & Constants ──────────────────────────────────────────────


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


# ── Formatter ───────────────────────────────────────────────────────


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
        # Signal has no buttons -- actions should be rendered as text labels
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


# ── Media ───────────────────────────────────────────────────────────


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


# ── Handlers ────────────────────────────────────────────────────────


from nobla.channels.signal.handlers import SignalHandlers


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        signal_handlers._linking.create_pairing_code = AsyncMock(
            return_value="CODE12"
        )
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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        signal_handlers._linking.create_pairing_code = AsyncMock(
            return_value="PAR456"
        )
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
        assert call.event_type == "channel.message.status"

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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
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
        with patch(
            "nobla.channels.signal.handlers.load_attachment_from_path"
        ) as mock_load:
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
        signal_handlers._linking.resolve = AsyncMock(
            return_value=FakeLinkedUser()
        )
        envelope = {
            "source": "+1234567890",
            "sourceUuid": "uuid-1",
            "timestamp": 1000,
            "dataMessage": {"message": "Test", "timestamp": 1000},
        }
        await signal_handlers.handle_message(envelope)
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.event_type == "channel.message.in"
        assert call.payload["channel"] == "signal"
