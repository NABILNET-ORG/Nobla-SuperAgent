"""Tests for the Facebook Messenger Platform webhook handlers (Phase 5-Channels).

Split from ``test_messenger_adapter.py`` to keep both files under the
750-line ceiling. Covers: handler init, webhook dispatch routing, keyword
commands, quick-reply / postback flows, delivery + read receipts, and
event emission shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from nobla.channels.messenger.handlers import MessengerHandlers
from nobla.channels.messenger.models import (
    CHANNEL_NAME,
    DEFAULT_API_VERSION,
)


# ── Fixtures ──────────────────────────────────────────────


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


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


# ═════════════════════════════════════════════════════════
# Init
# ═════════════════════════════════════════════════════════


class TestMessengerHandlersInit:
    def test_accepts_all_ctor_args(self, linking, event_bus):
        h = MessengerHandlers(
            linking=linking,
            event_bus=event_bus,
            page_access_token="t",
            page_id="p",
            api_version="v21.0",
            max_file_size_mb=50,
        )
        assert h._linking is linking
        assert h._event_bus is event_bus
        assert h._page_access_token == "t"
        assert h._page_id == "p"
        assert h._api_version == "v21.0"
        assert h._max_file_size_bytes == 50 * 1024 * 1024

    def test_defaults(self, linking, event_bus):
        h = MessengerHandlers(linking=linking, event_bus=event_bus)
        assert h._page_access_token == ""
        assert h._page_id == ""
        assert h._api_version == DEFAULT_API_VERSION
        assert h._max_file_size_bytes == 100 * 1024 * 1024

    def test_set_send_fn(self, handlers):
        fn = AsyncMock()
        handlers.set_send_fn(fn)
        assert handlers._send_text_fn is fn


# ═════════════════════════════════════════════════════════
# Dispatch
# ═════════════════════════════════════════════════════════


class TestHandleWebhook:
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
    async def test_postback_routes_to_postback_handler(self, handlers, event_bus):
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
        # Force an exception inside _handle_message and make sure
        # handle_webhook does not bubble it.
        linking.resolve = AsyncMock(side_effect=RuntimeError("boom"))
        payload = _make_webhook_payload([_make_message_event(text="hi")])
        # Should not raise.
        await handlers.handle_webhook(payload)


# ═════════════════════════════════════════════════════════
# Keyword commands
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
    async def test_link_with_user_id(self, handlers, linking):
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
    async def test_unknown_bang_command_swallowed(self, handlers, linking):
        # Unknown bang-prefixed text exits the message handler after the
        # dispatch_command call and never reaches the link path.
        payload = _make_webhook_payload([_make_message_event(text="!nope")])
        await handlers.handle_webhook(payload)
        linking.link.assert_not_awaited()


# ═════════════════════════════════════════════════════════
# Quick reply / postback
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
# Delivery / read
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
# Event emission shape
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
