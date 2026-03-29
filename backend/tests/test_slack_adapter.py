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


# =====================================================================
# Task 2: Formatter (Block Kit)
# =====================================================================

from nobla.channels.slack.formatter import (
    markdown_to_blocks,
    split_message,
    build_actions_block,
    format_response,
)


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


class TestMarkdownToBlocks:
    def test_plain_text(self):
        blocks = markdown_to_blocks("Hello world")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "section"
        assert "Hello world" in blocks[0]["text"]["text"]

    def test_header_conversion(self):
        blocks = markdown_to_blocks("# My Header\nSome text")
        types = [b["type"] for b in blocks]
        assert "header" in types

    def test_h2_header(self):
        blocks = markdown_to_blocks("## Sub Header\nMore text")
        types = [b["type"] for b in blocks]
        assert "header" in types

    def test_code_block(self):
        blocks = markdown_to_blocks("```python\nprint('hi')\n```")
        # Code blocks become section blocks with code formatting
        found = False
        for b in blocks:
            if b["type"] == "section":
                text = b["text"]["text"]
                if "```" in text:
                    found = True
        assert found

    def test_divider(self):
        blocks = markdown_to_blocks("above\n---\nbelow")
        types = [b["type"] for b in blocks]
        assert "divider" in types

    def test_mixed_content(self):
        md = "# Title\nSome *bold* text\n---\n## Section\nMore text"
        blocks = markdown_to_blocks(md)
        assert len(blocks) >= 3

    def test_empty_text(self):
        blocks = markdown_to_blocks("")
        assert blocks == []

    def test_block_limit(self):
        # Create content that would produce many blocks
        md = "\n".join(f"# Header {i}" for i in range(60))
        blocks = markdown_to_blocks(md)
        assert len(blocks) <= MAX_BLOCKS

    def test_bullet_list(self):
        md = "Items:\n- First\n- Second\n- Third"
        blocks = markdown_to_blocks(md)
        assert len(blocks) >= 1


class TestBuildActionsBlock:
    def test_basic_buttons(self):
        actions = [
            InlineAction(action_id="approve", label="Approve", style="primary"),
            InlineAction(action_id="deny", label="Deny", style="danger"),
        ]
        block = build_actions_block(actions)
        assert block["type"] == "actions"
        assert len(block["elements"]) == 2
        assert block["elements"][0]["action_id"] == "approve"
        assert block["elements"][0]["text"]["text"] == "Approve"

    def test_max_actions_capped(self):
        actions = [
            InlineAction(action_id=f"btn{i}", label=f"Btn {i}")
            for i in range(8)
        ]
        block = build_actions_block(actions)
        assert len(block["elements"]) == MAX_ACTIONS

    def test_style_mapping(self):
        actions = [
            InlineAction(action_id="ok", label="OK", style="primary"),
            InlineAction(action_id="rm", label="Delete", style="danger"),
            InlineAction(action_id="skip", label="Skip", style="secondary"),
        ]
        block = build_actions_block(actions)
        assert block["elements"][0].get("style") == "primary"
        assert block["elements"][1].get("style") == "danger"
        # secondary has no style in Slack Block Kit
        assert "style" not in block["elements"][2]

    def test_empty_actions(self):
        block = build_actions_block([])
        assert block["type"] == "actions"
        assert block["elements"] == []

    def test_long_label_truncated(self):
        actions = [InlineAction(action_id="x", label="A" * 100)]
        block = build_actions_block(actions)
        assert len(block["elements"][0]["text"]["text"]) <= 75


class TestFormatResponse:
    def test_simple_text(self):
        resp = ChannelResponse(content="Hello!")
        result = format_response(resp)
        assert result["text"] == "Hello!"
        assert "blocks" in result
        assert len(result["blocks"]) >= 1

    def test_empty_content(self):
        resp = ChannelResponse(content="")
        result = format_response(resp)
        assert result["text"] == ""
        assert result["blocks"] == []

    def test_with_actions(self):
        resp = ChannelResponse(
            content="Approve?",
            actions=[
                InlineAction(action_id="yes", label="Yes"),
                InlineAction(action_id="no", label="No"),
            ],
        )
        result = format_response(resp)
        types = [b["type"] for b in result["blocks"]]
        assert "actions" in types

    def test_long_text_split(self):
        resp = ChannelResponse(content="x" * 5000)
        result = format_response(resp)
        # Should have fallback text truncated
        assert len(result["text"]) <= MAX_MESSAGE_LENGTH

    def test_markdown_headers_in_blocks(self):
        resp = ChannelResponse(content="# Title\nBody text")
        result = format_response(resp)
        types = [b["type"] for b in result["blocks"]]
        assert "header" in types
