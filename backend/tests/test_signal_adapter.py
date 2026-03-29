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
