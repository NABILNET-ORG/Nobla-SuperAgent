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
