"""Microsoft Teams channel adapter tests (Phase 5-Channels)."""

from __future__ import annotations

import pytest


class TestTeamsUserContext:
    def test_create_minimal(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123", display_name="Test User", tenant_id="tenant-abc",
            conversation_id="conv-456", service_url="https://smba.trafficmanager.net/teams/",
            message_id="msg-789",
        )
        assert ctx.user_id == "user-123"
        assert ctx.display_name == "Test User"
        assert ctx.tenant_id == "tenant-abc"
        assert ctx.conversation_id == "conv-456"
        assert ctx.service_url == "https://smba.trafficmanager.net/teams/"
        assert ctx.message_id == "msg-789"
        assert ctx.channel_id is None
        assert ctx.is_dm is False
        assert ctx.is_bot_mentioned is False
        assert ctx.raw_extras == {}

    def test_create_full(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123", display_name="Test User", tenant_id="tenant-abc",
            conversation_id="conv-456", service_url="https://smba.trafficmanager.net/teams/",
            message_id="msg-789", channel_id="19:abc@thread.tacv2",
            is_dm=True, is_bot_mentioned=True, raw_extras={"locale": "en-US"},
        )
        assert ctx.channel_id == "19:abc@thread.tacv2"
        assert ctx.is_dm is True
        assert ctx.is_bot_mentioned is True
        assert ctx.raw_extras == {"locale": "en-US"}

    def test_user_id_str_property(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="user-123", display_name="U", tenant_id="t",
            conversation_id="c", service_url="http://x", message_id="m",
        )
        assert ctx.user_id_str == "user-123"

    def test_channel_id_str_property(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="u", display_name="U", tenant_id="t",
            conversation_id="conv-1", service_url="http://x",
            message_id="m", channel_id="ch-1",
        )
        assert ctx.channel_id_str == "ch-1"

    def test_channel_id_str_none_returns_conversation_id(self):
        from nobla.channels.teams.models import TeamsUserContext
        ctx = TeamsUserContext(
            user_id="u", display_name="U", tenant_id="t",
            conversation_id="conv-1", service_url="http://x", message_id="m",
        )
        assert ctx.channel_id_str == "conv-1"


class TestTeamsConstants:
    def test_channel_name(self):
        from nobla.channels.teams.models import CHANNEL_NAME
        assert CHANNEL_NAME == "teams"

    def test_mime_to_media_type_image(self):
        from nobla.channels.teams.models import MIME_TO_MEDIA_TYPE
        assert MIME_TO_MEDIA_TYPE["image/png"] == "image"
        assert MIME_TO_MEDIA_TYPE["image/jpeg"] == "image"

    def test_supported_activity_types(self):
        from nobla.channels.teams.models import SUPPORTED_ACTIVITY_TYPES
        assert "message" in SUPPORTED_ACTIVITY_TYPES
        assert "invoke" in SUPPORTED_ACTIVITY_TYPES
        assert "conversationUpdate" in SUPPORTED_ACTIVITY_TYPES
        assert "typing" not in SUPPORTED_ACTIVITY_TYPES


# ── Formatter ───────────────────────────────────────────────


class TestSplitMessage:
    def test_short_text_no_split(self):
        from nobla.channels.teams.formatter import split_message
        assert split_message("Hello world", 100) == ["Hello world"]

    def test_split_at_newline(self):
        from nobla.channels.teams.formatter import split_message
        result = split_message("line1\nline2\nline3", 10)
        assert len(result) >= 2
        assert result[0] == "line1"

    def test_split_at_space(self):
        from nobla.channels.teams.formatter import split_message
        result = split_message("word1 word2 word3", 10)
        assert len(result) >= 2

    def test_hard_cut(self):
        from nobla.channels.teams.formatter import split_message
        result = split_message("abcdefghijklmnop", 8)
        assert result[0] == "abcdefgh"


class TestMarkdownToCardBody:
    def test_empty_text(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        assert markdown_to_card_body("") == []

    def test_plain_text(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("Hello world")
        assert len(body) == 1
        assert body[0]["type"] == "TextBlock"
        assert body[0]["text"] == "Hello world"
        assert body[0]["wrap"] is True

    def test_h1_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("# Big Title")
        assert body[0]["size"] == "Large"
        assert body[0]["weight"] == "Bolder"
        assert body[0]["text"] == "Big Title"

    def test_h2_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("## Medium Title")
        assert body[0]["size"] == "Medium"
        assert body[0]["weight"] == "Bolder"

    def test_h3_heading(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("### Small Title")
        assert body[0]["size"] == "Default"
        assert body[0]["weight"] == "Bolder"

    def test_code_block(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("```\nprint('hi')\n```")
        code_block = [b for b in body if b.get("fontType") == "Monospace"]
        assert len(code_block) == 1
        assert "print('hi')" in code_block[0]["text"]

    def test_divider(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("above\n---\nbelow")
        separators = [b for b in body if b.get("type") == "ColumnSet"]
        assert len(separators) == 1

    def test_blockquote(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        body = markdown_to_card_body("> This is a quote")
        containers = [b for b in body if b.get("type") == "Container"]
        assert len(containers) == 1
        assert containers[0]["style"] == "accent"

    def test_mixed_content(self):
        from nobla.channels.teams.formatter import markdown_to_card_body
        text = "# Title\nSome text\n---\n```\ncode\n```\n> quote"
        body = markdown_to_card_body(text)
        assert len(body) >= 4


class TestBuildCardActions:
    def test_single_action(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="test:1:approve", label="Approve")]
        result = build_card_actions(actions)
        assert len(result) == 1
        assert result[0]["type"] == "Action.Submit"
        assert result[0]["title"] == "Approve"
        assert result[0]["data"]["action_id"] == "test:1:approve"

    def test_primary_style(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="a:1:go", label="Go", style="primary")]
        result = build_card_actions(actions)
        assert result[0]["style"] == "positive"

    def test_danger_style(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id="a:1:del", label="Delete", style="danger")]
        result = build_card_actions(actions)
        assert result[0]["style"] == "destructive"

    def test_max_actions_cap(self):
        from nobla.channels.teams.formatter import build_card_actions
        from nobla.channels.base import InlineAction
        actions = [InlineAction(action_id=f"a:{i}:x", label=f"Btn{i}") for i in range(10)]
        result = build_card_actions(actions)
        assert len(result) == 5


class TestFormatResponse:
    def test_empty_content(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content=""))
        assert result["type"] == "message"
        assert result["attachments"] == []

    def test_text_produces_adaptive_card(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content="Hello"))
        assert len(result["attachments"]) == 1
        card = result["attachments"][0]
        assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
        assert card["content"]["type"] == "AdaptiveCard"
        assert card["content"]["version"] == "1.4"

    def test_actions_included_in_card(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse, InlineAction
        actions = [InlineAction(action_id="a:1:ok", label="OK")]
        result = format_response(ChannelResponse(content="Choose:", actions=actions))
        card = result["attachments"][0]["content"]
        assert len(card["actions"]) == 1

    def test_text_only_no_actions(self):
        from nobla.channels.teams.formatter import format_response
        from nobla.channels.base import ChannelResponse
        result = format_response(ChannelResponse(content="Just text"))
        card = result["attachments"][0]["content"]
        assert card["actions"] == []
