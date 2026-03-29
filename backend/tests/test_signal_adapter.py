"""Tests for the Signal channel adapter (Phase 5-Channels).

Covers: models, formatter, media, handlers, adapter, and edge cases.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nobla.channels.base import (
    Attachment, AttachmentType, ChannelResponse, InlineAction,
)
from nobla.channels.signal.adapter import SignalAdapter
from nobla.channels.signal.formatter import FormattedMessage, format_response, split_message
from nobla.channels.signal.handlers import SignalHandlers
from nobla.channels.signal.media import (
    guess_mime_type, load_attachment_from_path,
    save_attachment_to_disk, validate_file_size,
)
from nobla.channels.signal.models import (
    CHANNEL_NAME, MAX_MESSAGE_LENGTH, RPC_METHODS, SignalUserContext,
)


# ── Fixtures ────────────────────────────────────────────────────────

@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


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


def _make_envelope(source="+1234567890", uuid="uuid-1", ts=1000, **dm_fields):
    """Helper to build a signal envelope with dataMessage."""
    dm = {"timestamp": ts, **dm_fields}
    return {"source": source, "sourceUuid": uuid, "timestamp": ts, "dataMessage": dm}


@pytest.fixture
def signal_handlers():
    linking = AsyncMock()
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    h = SignalHandlers(
        linking_service=linking, event_bus=event_bus,
        bot_phone_number="+15551234567",
    )
    h.set_send_fn(AsyncMock())
    return h


def _make_adapter():
    handlers = MagicMock()
    handlers.handle_message = AsyncMock()
    return SignalAdapter(settings=_FakeSignalSettings(), handlers=handlers)


# ── Models & Constants ──────────────────────────────────────────────

class TestSignalModels:
    def test_channel_name(self):
        assert CHANNEL_NAME == "signal"

    def test_max_message_length(self):
        assert MAX_MESSAGE_LENGTH == 6000

    def test_rpc_methods(self):
        assert isinstance(RPC_METHODS, dict)
        assert "send" in RPC_METHODS and "receive" in RPC_METHODS and "version" in RPC_METHODS

    def test_user_context_basic(self):
        ctx = SignalUserContext(
            source_number="+1234567890", source_uuid="uuid-123",
            is_group=False, is_bot_mentioned=False, timestamp=1234567890000,
        )
        assert ctx.source_number == "+1234567890"
        assert ctx.user_id_str == "+1234567890"
        assert ctx.chat_id_str == "+1234567890"

    def test_user_context_group(self):
        ctx = SignalUserContext(
            source_number="+1234567890", source_uuid="uuid-123",
            group_id="group-abc", is_group=True, is_bot_mentioned=True,
            timestamp=1234567890000,
        )
        assert ctx.chat_id_str == "group-abc"
        assert ctx.is_group is True

    def test_user_context_disappearing(self):
        ctx = SignalUserContext(
            source_number="+1", source_uuid="u1", is_group=False,
            is_bot_mentioned=False, timestamp=0, expires_in_seconds=3600,
        )
        assert ctx.expires_in_seconds == 3600 and ctx.is_disappearing is True

    def test_user_context_not_disappearing(self):
        ctx = SignalUserContext(
            source_number="+1", source_uuid="u1", is_group=False,
            is_bot_mentioned=False, timestamp=0,
        )
        assert ctx.expires_in_seconds == 0 and ctx.is_disappearing is False


# ── Formatter ───────────────────────────────────────────────────────

class TestSignalFormatter:
    def test_split_short(self):
        assert split_message("Hello", 6000) == ["Hello"]

    def test_split_at_newline(self):
        chunks = split_message("Line\n" * 4000, 6000)
        assert all(len(c) <= 6000 for c in chunks)

    def test_split_long_word(self):
        assert len(split_message("X" * 12000, 6000)) == 2

    def test_split_exactly_at_limit(self):
        assert len(split_message("A" * 6000, 6000)) == 1

    def test_format_response_simple(self):
        msgs = format_response(ChannelResponse(content="Hello Signal"))
        assert len(msgs) == 1 and msgs[0].text == "Hello Signal"

    def test_format_response_empty(self):
        assert format_response(ChannelResponse(content="")) == []

    def test_format_response_long_splits(self):
        assert len(format_response(ChannelResponse(content="Y" * 12000))) >= 2

    def test_format_response_actions_as_text(self):
        resp = ChannelResponse(
            content="Choose:",
            actions=[InlineAction(action_id="a:1:yes", label="Yes"),
                     InlineAction(action_id="a:1:no", label="No")],
        )
        combined = " ".join(m.text for m in format_response(resp))
        assert "Yes" in combined and "No" in combined

    def test_formatted_message_dataclass(self):
        assert FormattedMessage(text="hello").text == "hello"


# ── Media ───────────────────────────────────────────────────────────

class TestSignalMedia:
    def test_save_attachment_to_disk(self):
        att = Attachment(type=AttachmentType.IMAGE, filename="test.png",
                         mime_type="image/png", size_bytes=4, data=b"\x89PNG")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_attachment_to_disk(att, tmpdir)
            assert os.path.exists(path) and path.endswith("test.png")
            with open(path, "rb") as f:
                assert f.read() == b"\x89PNG"

    def test_save_attachment_sanitizes_filename(self):
        att = Attachment(type=AttachmentType.DOCUMENT, filename="../../../etc/passwd",
                         mime_type="text/plain", size_bytes=5, data=b"hello")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_attachment_to_disk(att, tmpdir)
            assert path.startswith(tmpdir)

    def test_save_attachment_no_data(self):
        att = Attachment(type=AttachmentType.IMAGE, filename="empty.png",
                         mime_type="image/png", size_bytes=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="no data"):
                save_attachment_to_disk(att, tmpdir)

    def test_load_attachment_from_path(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG_DATA")
            f.flush()
            path = f.name
        try:
            att = load_attachment_from_path(path, "image/png")
            assert att.type == AttachmentType.IMAGE and att.data == b"\x89PNG_DATA"
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
        assert guess_mime_type("file.xyz") == "application/octet-stream"

    def test_guess_mime_type_pdf(self):
        assert guess_mime_type("doc.pdf") == "application/pdf"


# ── Handlers ────────────────────────────────────────────────────────

class TestSignalHandlers:
    @pytest.mark.asyncio
    async def test_handle_dm_message(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(_make_envelope(message="Hello bot"))
        signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_group_message_with_mention(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        signal_handlers._bot_uuid = "bot-uuid"
        env = _make_envelope(
            message="Hey bot",
            groupInfo={"groupId": "group-abc", "type": "DELIVER"},
            mentions=[{"uuid": "bot-uuid", "start": 0, "length": 3}],
        )
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_handle_group_message_no_mention_ignored(self, signal_handlers):
        env = _make_envelope(
            message="Regular chat",
            groupInfo={"groupId": "group-abc", "type": "DELIVER"},
        )
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_own_message_ignored(self, signal_handlers):
        env = _make_envelope(source="+15551234567", uuid="bot-uuid", message="echo")
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_start(self, signal_handlers):
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="CODE12")
        await signal_handlers.handle_message(
            _make_envelope(source="+111", uuid="u2", message="/start"))
        signal_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_command_link(self, signal_handlers):
        signal_handlers._linking.link = AsyncMock(return_value=True)
        await signal_handlers.handle_message(
            _make_envelope(source="+111", uuid="u2", message="/link user-001"))
        signal_handlers._linking.link.assert_called()

    @pytest.mark.asyncio
    async def test_command_unlink(self, signal_handlers):
        signal_handlers._linking.unlink = AsyncMock(return_value=True)
        await signal_handlers.handle_message(
            _make_envelope(source="+111", uuid="u2", message="/unlink"))
        signal_handlers._linking.unlink.assert_called()

    @pytest.mark.asyncio
    async def test_command_status_linked(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(
            _make_envelope(source="+111", uuid="u2", message="/status"))
        signal_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_unlinked_user_gets_pairing_prompt(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=None)
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="PAR456")
        await signal_handlers.handle_message(
            _make_envelope(source="+999", uuid="uuid-new", message="Hello"))
        signal_handlers._send_fn.assert_called()
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_delivery_receipt(self, signal_handlers):
        env = {"source": "+1234567890", "sourceUuid": "uuid-1", "timestamp": 2000,
               "receiptMessage": {"type": "DELIVERY", "timestamps": [1000]}}
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_called()
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.event_type == "channel.message.status"

    @pytest.mark.asyncio
    async def test_handle_read_receipt(self, signal_handlers):
        env = {"source": "+1234567890", "sourceUuid": "uuid-1", "timestamp": 2000,
               "receiptMessage": {"type": "READ", "timestamps": [1000]}}
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_sends_read_receipt_on_process(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        signal_handlers._send_receipt_fn = AsyncMock()
        await signal_handlers.handle_message(
            _make_envelope(ts=1234567890000, message="Test"))
        signal_handlers._send_receipt_fn.assert_called_with("+1234567890", 1234567890000)

    @pytest.mark.asyncio
    async def test_disappearing_message_sets_metadata(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(
            _make_envelope(message="Secret", expiresInSeconds=3600))
        call = signal_handlers._event_bus.publish.call_args[0][0]
        meta = call.payload.get("metadata", {})
        assert meta.get("disappearing") is True and meta.get("expires_in_seconds") == 3600

    @pytest.mark.asyncio
    async def test_handle_message_with_attachment(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        env = _make_envelope(
            message="See file",
            attachments=[{"contentType": "image/png", "filename": "photo.png",
                          "size": 2048, "id": "att-1"}],
        )
        with patch("nobla.channels.signal.handlers.load_attachment_from_path") as ml:
            ml.return_value = Attachment(type=AttachmentType.IMAGE, filename="photo.png",
                                        mime_type="image/png", size_bytes=2048, data=b"png")
            await signal_handlers.handle_message(env)
            signal_handlers._event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_event_has_correct_channel(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(_make_envelope(message="Test"))
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.event_type == "channel.message.in"
        assert call.payload["channel"] == "signal"


# ── Adapter ─────────────────────────────────────────────────────────

class TestSignalAdapter:
    def test_name(self):
        assert _make_adapter().name == "signal"

    @pytest.mark.asyncio
    async def test_send_dm(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        await adapter.send("+1234567890", ChannelResponse(content="Hello"))
        adapter._rpc_call.assert_called()
        assert adapter._rpc_call.call_args[0][0] == "send"

    @pytest.mark.asyncio
    async def test_send_group(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        await adapter.send("group-abc", ChannelResponse(content="Group hello"), is_group=True)
        assert "groupId" in adapter._rpc_call.call_args[1]

    @pytest.mark.asyncio
    async def test_send_notification(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        await adapter.send_notification("+1234567890", "Alert!")
        adapter._rpc_call.assert_called()

    @pytest.mark.asyncio
    async def test_send_long_message_splits(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"timestamp": 1000})
        await adapter.send("+1234567890", ChannelResponse(content="Z" * 12000))
        assert adapter._rpc_call.call_count >= 2

    def test_parse_callback_noop(self):
        action_id, meta = _make_adapter().parse_callback({"anything": "data"})
        assert action_id == "" and meta == {}

    @pytest.mark.asyncio
    async def test_send_read_receipt(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock()
        await adapter.send_read_receipt("+1234567890", 1234567890000)
        adapter._rpc_call.assert_called_with(
            "sendReceipt", recipient="+1234567890", timestamp=1234567890000, type="read")

    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(return_value={"version": "0.13.0"})
        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock(side_effect=ConnectionError("refused"))
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_rpc_call_formats_request(self):
        adapter = _make_adapter()
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_reader.readline = AsyncMock(
            return_value=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
            ).encode() + b"\n")
        adapter._reader, adapter._writer, adapter._rpc_id = mock_reader, mock_writer, 0
        assert await adapter._rpc_call("version") == {"ok": True}

    @pytest.mark.asyncio
    async def test_rpc_call_error_response(self):
        adapter = _make_adapter()
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_reader.readline = AsyncMock(
            return_value=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "fail"}}
            ).encode() + b"\n")
        adapter._reader, adapter._writer, adapter._rpc_id = mock_reader, mock_writer, 0
        with pytest.raises(Exception, match="fail"):
            await adapter._rpc_call("bad_method")

    @pytest.mark.asyncio
    async def test_start_connects(self):
        adapter = _make_adapter()
        with patch("asyncio.open_connection", new_callable=AsyncMock) as mc:
            mc.return_value = (AsyncMock(), MagicMock(close=MagicMock()))
            with patch.object(adapter, "_start_receive_loop", new_callable=AsyncMock):
                await adapter.start()
                mc.assert_called_with("localhost", 7583)

    @pytest.mark.asyncio
    async def test_stop_closes_connection(self):
        adapter = _make_adapter()
        mw = MagicMock(close=MagicMock(), wait_closed=AsyncMock())
        adapter._writer, adapter._reader, adapter._receive_task = mw, AsyncMock(), None
        await adapter.stop()
        mw.close.assert_called()

    def test_reconnect_backoff(self):
        adapter = _make_adapter()
        assert adapter._reconnect_delay(0) == 1
        assert adapter._reconnect_delay(1) == 2
        assert adapter._reconnect_delay(2) == 4
        assert adapter._reconnect_delay(10) == 30


# ── Edge Cases ──────────────────────────────────────────────────────

class TestSignalEdgeCases:
    # Formatter
    def test_split_empty_string(self):
        assert split_message("", 6000) == []

    def test_format_response_actions_only(self):
        resp = ChannelResponse(content="",
                               actions=[InlineAction(action_id="a:1:go", label="Go")])
        msgs = format_response(resp)
        assert len(msgs) >= 1 and "Go" in msgs[0].text

    # Media
    def test_save_attachment_creates_subdir(self):
        att = Attachment(type=AttachmentType.DOCUMENT, filename="doc.pdf",
                         mime_type="application/pdf", size_bytes=3, data=b"pdf")
        with tempfile.TemporaryDirectory() as tmpdir:
            assert os.path.dirname(save_attachment_to_disk(att, tmpdir)) != tmpdir

    def test_validate_file_size_zero(self):
        assert validate_file_size(0, max_mb=100) is True

    def test_guess_mime_type_jpeg(self):
        assert guess_mime_type("photo.jpg") in ("image/jpeg", "image/jpg")

    def test_guess_mime_type_mp4(self):
        assert guess_mime_type("video.mp4") == "video/mp4"

    # Handlers
    @pytest.mark.asyncio
    async def test_typing_indicator_ignored(self, signal_handlers):
        env = {"source": "+1234567890", "sourceUuid": "uuid-1", "timestamp": 1000,
               "typingMessage": {"action": "STARTED"}}
        await signal_handlers.handle_message(env)
        signal_handlers._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_data_message(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(_make_envelope(source="+1234567890"))

    @pytest.mark.asyncio
    async def test_command_case_insensitive(self, signal_handlers):
        signal_handlers._linking.create_pairing_code = AsyncMock(return_value="A1")
        await signal_handlers.handle_message(
            _make_envelope(source="+111", uuid="u2", message="/START"))
        signal_handlers._send_fn.assert_called()

    @pytest.mark.asyncio
    async def test_disappearing_zero_means_disabled(self, signal_handlers):
        signal_handlers._linking.resolve = AsyncMock(return_value=FakeLinkedUser())
        await signal_handlers.handle_message(
            _make_envelope(message="Normal", expiresInSeconds=0))
        call = signal_handlers._event_bus.publish.call_args[0][0]
        assert call.payload.get("metadata", {}).get("disappearing", False) is False

    # Adapter
    @pytest.mark.asyncio
    async def test_send_empty_response(self):
        adapter = _make_adapter()
        adapter._rpc_call = AsyncMock()
        await adapter.send("+1", ChannelResponse(content=""))
        adapter._rpc_call.assert_not_called()

    def test_reconnect_delay_capped(self):
        assert _make_adapter()._reconnect_delay(100) == 30

    def test_reconnect_delay_first_attempt(self):
        assert _make_adapter()._reconnect_delay(0) == 1
