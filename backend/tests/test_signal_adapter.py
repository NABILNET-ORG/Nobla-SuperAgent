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
