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
