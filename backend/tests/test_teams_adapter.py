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


# ── Media ───────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock


class TestDetectAttachmentType:
    def test_image_png(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("image/png") == AttachmentType.IMAGE

    def test_audio_mpeg(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("audio/mpeg") == AttachmentType.AUDIO

    def test_video_mp4(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("video/mp4") == AttachmentType.VIDEO

    def test_unknown_defaults_document(self):
        from nobla.channels.teams.media import detect_attachment_type
        from nobla.channels.base import AttachmentType
        assert detect_attachment_type("application/x-unknown") == AttachmentType.DOCUMENT


@pytest.mark.asyncio
class TestDownloadAttachment:
    async def test_download_content_url(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"filedata"
        mock_resp.headers = {"Content-Length": "8", "Content-Type": "image/png"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await download_attachment(
            {"contentType": "image/png", "contentUrl": "https://teams.cdn/file.png", "name": "file.png"},
            "token-123", mock_client,
        )
        assert result is not None
        assert result.data == b"filedata"
        assert result.mime_type == "image/png"

    async def test_download_direct_url(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"filedata"
        mock_resp.headers = {"Content-Length": "8", "Content-Type": "application/pdf"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await download_attachment(
            {"contentType": "application/vnd.microsoft.teams.file.download.info",
             "content": {"downloadUrl": "https://direct/file.pdf"}, "name": "file.pdf"},
            "token-123", mock_client,
        )
        assert result is not None

    async def test_download_size_exceeded(self):
        from nobla.channels.teams.media import download_attachment
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b""
        mock_resp.headers = {"Content-Length": "999999999", "Content-Type": "video/mp4"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await download_attachment(
            {"contentType": "video/mp4", "contentUrl": "https://teams.cdn/big.mp4", "name": "big.mp4"},
            "token", mock_client, max_size_bytes=1000,
        )
        assert result is None

    async def test_download_error_returns_none(self):
        from nobla.channels.teams.media import download_attachment
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        result = await download_attachment(
            {"contentType": "image/png", "contentUrl": "https://teams.cdn/file.png", "name": "file.png"},
            "token", mock_client,
        )
        assert result is None


@pytest.mark.asyncio
class TestSendAttachment:
    async def test_send_small_inline_base64(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(type=AttachmentType.IMAGE, filename="small.png", mime_type="image/png",
                         size_bytes=100, data=b"\x89PNG" + b"\x00" * 96)
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/", "conv-1", att, "token", mock_client
        )
        assert result is True

    async def test_send_large_with_url_as_hero_card(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(type=AttachmentType.DOCUMENT, filename="big.zip", mime_type="application/zip",
                         size_bytes=500_000, url="https://example.com/big.zip")
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/", "conv-1", att, "token", mock_client
        )
        assert result is True

    async def test_send_large_no_url_returns_false(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(type=AttachmentType.VIDEO, filename="big.mp4", mime_type="video/mp4",
                         size_bytes=500_000, data=b"\x00" * 500_000)
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/", "conv-1", att, "token", AsyncMock()
        )
        assert result is False

    async def test_send_no_data_no_url_returns_false(self):
        from nobla.channels.teams.media import send_attachment
        from nobla.channels.base import Attachment, AttachmentType
        att = Attachment(type=AttachmentType.DOCUMENT, filename="empty.txt", mime_type="text/plain", size_bytes=0)
        result = await send_attachment(
            "https://smba.trafficmanager.net/teams/", "conv-1", att, "token", AsyncMock()
        )
        assert result is False


# ── Handlers ────────────────────────────────────────────────


def _make_linking_mock(linked_user=None):
    mock = AsyncMock()
    mock.resolve = AsyncMock(return_value=linked_user)
    mock.create_pairing_code = AsyncMock(return_value="ABC123")
    mock.link = AsyncMock()
    mock.unlink = AsyncMock()
    return mock


def _make_event_bus_mock():
    mock = AsyncMock()
    mock.publish = AsyncMock()
    return mock


def _make_linked_user(nobla_user_id="nobla-user-1"):
    user = MagicMock()
    user.nobla_user_id = nobla_user_id
    user.conversation_id = "conv-1"
    return user


def _make_message_activity(text="hello", user_id="user-123", user_name="Test User",
                            conversation_id="conv-456",
                            service_url="https://smba.trafficmanager.net/teams/",
                            channel_id=None, entities=None, tenant_id="tenant-abc"):
    activity = {
        "type": "message", "id": "msg-789", "text": text,
        "from": {"id": user_id, "name": user_name},
        "conversation": {"id": conversation_id,
                          "conversationType": "personal" if not channel_id else "channel"},
        "channelId": "msteams", "serviceUrl": service_url,
        "channelData": {"tenant": {"id": tenant_id}},
    }
    if channel_id:
        activity["channelData"]["channel"] = {"id": channel_id}
    if entities:
        activity["entities"] = entities
    return activity


@pytest.mark.asyncio
class TestTeamsHandlers:
    async def test_set_send_fn(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        fn = AsyncMock()
        h.set_send_fn(fn)
        assert h._send_fn is fn

    async def test_handle_message_dm_always_responds(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())
        await h.handle_activity(_make_message_activity(text="hi there"))
        assert h._event_bus.publish.called

    async def test_handle_message_channel_no_mention_ignored(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())
        await h.handle_activity(_make_message_activity(text="hello", channel_id="ch-1"))
        assert not h._event_bus.publish.called

    async def test_handle_message_channel_with_mention(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())
        entities = [{"type": "mention", "mentioned": {"id": "app-id", "name": "Nobla"}}]
        await h.handle_activity(_make_message_activity(
            text="<at>Nobla</at> what time is it", channel_id="ch-1", entities=entities))
        assert h._event_bus.publish.called

    async def test_mention_stripped_from_text(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())
        entities = [{"type": "mention", "mentioned": {"id": "app-id", "name": "Nobla"}}]
        await h.handle_activity(_make_message_activity(text="<at>Nobla</at> do something", entities=entities))
        event = bus.publish.call_args[0][0]
        assert "<at>" not in event.payload.get("content", "")

    async def test_unlinked_user_gets_pairing_code(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linking = _make_linking_mock(linked_user=None)
        h = TeamsHandlers(linking, _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="hello"))
        linking.create_pairing_code.assert_called_once()
        assert send_fn.called

    async def test_conversation_ref_captured(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        h.set_send_fn(AsyncMock())
        await h.handle_activity(_make_message_activity(
            user_id="user-123", service_url="https://smba.trafficmanager.net/teams/",
            conversation_id="conv-456"))
        ref = h.get_conversation_ref("user-123")
        assert ref is not None
        assert ref["service_url"] == "https://smba.trafficmanager.net/teams/"
        assert ref["conversation_id"] == "conv-456"


@pytest.mark.asyncio
class TestTeamsKeywordCommands:
    async def test_cmd_start_unlinked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!start"))
        msg = send_fn.call_args[0][1]
        assert "ABC123" in msg

    async def test_cmd_start_already_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!start"))
        msg = send_fn.call_args[0][1]
        assert "Welcome back" in msg

    async def test_cmd_link_no_args_gives_pairing_code(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!link"))
        msg = send_fn.call_args[0][1]
        assert "ABC123" in msg

    async def test_cmd_link_with_user_id(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linking = _make_linking_mock()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(linking, bus, "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!link my-nobla-id"))
        linking.link.assert_called_once_with("teams", "user-123", "my-nobla-id")
        assert bus.publish.called

    async def test_cmd_unlink_when_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        linking = _make_linking_mock(linked)
        bus = _make_event_bus_mock()
        h = TeamsHandlers(linking, bus, "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!unlink"))
        linking.unlink.assert_called_once()
        msg = send_fn.call_args[0][1]
        assert "unlinked" in msg.lower()

    async def test_cmd_unlink_when_not_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!unlink"))
        msg = send_fn.call_args[0][1]
        assert "not" in msg.lower()

    async def test_cmd_status_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        h = TeamsHandlers(_make_linking_mock(linked), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!status"))
        msg = send_fn.call_args[0][1]
        assert "Linked" in msg

    async def test_cmd_status_not_linked(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        await h.handle_activity(_make_message_activity(text="!status"))
        msg = send_fn.call_args[0][1]
        assert "Not linked" in msg


@pytest.mark.asyncio
class TestTeamsActivityDispatch:
    async def test_invoke_activity_emits_callback(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())
        activity = {
            "type": "invoke", "name": "adaptiveCard/action",
            "from": {"id": "user-123", "name": "Test"},
            "conversation": {"id": "conv-1", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelData": {"tenant": {"id": "t1"}},
            "value": {"action": {"data": {"action_id": "approval:req-1:approve"}}},
        }
        await h.handle_activity(activity)
        assert bus.publish.called

    async def test_conversation_update_bot_added(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        send_fn = AsyncMock()
        h.set_send_fn(send_fn)
        activity = {
            "type": "conversationUpdate",
            "membersAdded": [{"id": "app-id", "name": "Nobla"}],
            "from": {"id": "user-1", "name": "U"},
            "conversation": {"id": "conv-1", "conversationType": "personal"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelData": {"tenant": {"id": "t1"}},
        }
        await h.handle_activity(activity)
        assert send_fn.called
        msg = send_fn.call_args[0][1]
        assert "Nobla" in msg

    async def test_ignored_activity_type(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(), bus, "app-id")
        await h.handle_activity({
            "type": "typing", "from": {"id": "u1", "name": "U"},
            "conversation": {"id": "c1"}, "serviceUrl": "http://x",
            "channelData": {"tenant": {"id": "t1"}},
        })
        assert not bus.publish.called

    async def test_event_bus_emission_content(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        linked = _make_linked_user()
        bus = _make_event_bus_mock()
        h = TeamsHandlers(_make_linking_mock(linked), bus, "app-id")
        h.set_send_fn(AsyncMock())
        await h.handle_activity(_make_message_activity(text="test message"))
        event = bus.publish.call_args[0][0]
        assert event.event_type == "channel.message.in"
        assert event.source == "teams"
        assert event.payload["content"] == "test message"

    async def test_send_fn_not_set_logs_warning(self):
        from nobla.channels.teams.handlers import TeamsHandlers
        h = TeamsHandlers(_make_linking_mock(), _make_event_bus_mock(), "app-id")
        await h.handle_activity(_make_message_activity(text="!start"))
