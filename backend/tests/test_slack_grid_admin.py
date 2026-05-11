"""Slack Enterprise Grid admin.* API helper tests (admin.users + admin.conversations).

Cycles 5-6 of the v2.1.6 constitutional-restart mission. Lives in a
fresh focused module per the Boy Scout Exception.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from nobla.channels.slack.adapter import SlackAdapter
from nobla.channels.slack.handlers import SlackHandlers
from tests._slack_grid_helpers import (
    FakeSlackSettings,
    err_response,
    ok_response,
)


# -- Fixtures --------------------------------------------------------


@pytest.fixture
def linking():
    svc = AsyncMock()
    svc.resolve = AsyncMock(return_value=None)
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
    h = SlackHandlers(
        linking=linking, event_bus=event_bus,
        bot_token="xoxb-test-token", bot_user_id="U_BOT",
        max_file_size_mb=100,
    )
    h.set_send_fn(AsyncMock())
    return h


def _grid_adapter(handlers, *, org_token: str = "xoxa-test-org", team_ids=None):
    s = FakeSlackSettings(
        enterprise_grid=True,
        org_token=org_token,
        team_ids=list(team_ids) if team_ids else ["T1", "T2"],
    )
    s.socket_mode = False
    return SlackAdapter(settings=s, handlers=handlers)


# -- admin.users.list ------------------------------------------------


class TestAdapterAdminUsersList:
    @pytest.mark.asyncio
    async def test_returns_users_payload(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({
            "members": [{"id": "U1"}, {"id": "U2"}],
            "response_metadata": {"next_cursor": ""},
        }))
        out = await a.list_admin_users(team_id="T1")
        assert out["members"] == [{"id": "U1"}, {"id": "U2"}]
        await a.stop()

    @pytest.mark.asyncio
    async def test_uses_org_token_not_bot_token(self, handlers):
        a = _grid_adapter(handlers, org_token="xoxa-ORG-SPECIFIC")
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"members": []}))
        await a.list_admin_users(team_id="T1")
        headers = a._client.post.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer xoxa-ORG-SPECIFIC"
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_team_id_in_body(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"members": []}))
        await a.list_admin_users(team_id="T_ALPHA")
        body = a._client.post.call_args.kwargs.get("json", {})
        assert body.get("team_id") == "T_ALPHA"
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_cursor_for_pagination(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"members": []}))
        await a.list_admin_users(team_id="T1", cursor="dXNlci0xMDA=")
        body = a._client.post.call_args.kwargs.get("json", {})
        assert body.get("cursor") == "dXNlci0xMDA="
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_limit_default_and_override(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"members": []}))
        await a.list_admin_users(team_id="T1")
        assert a._client.post.call_args.kwargs["json"]["limit"] == 100
        await a.list_admin_users(team_id="T1", limit=25)
        assert a._client.post.call_args.kwargs["json"]["limit"] == 25
        await a.stop()

    @pytest.mark.asyncio
    async def test_targets_admin_users_list_endpoint(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"members": []}))
        await a.list_admin_users(team_id="T1")
        url = a._client.post.call_args.args[0]
        assert url.endswith("/admin.users.list")
        await a.stop()

    @pytest.mark.asyncio
    async def test_raises_when_grid_disabled(self, handlers):
        s = FakeSlackSettings(enterprise_grid=False)
        s.socket_mode = False
        a = SlackAdapter(settings=s, handlers=handlers)
        await a.start()
        with pytest.raises(RuntimeError):
            await a.list_admin_users(team_id="T1")
        await a.stop()

    @pytest.mark.asyncio
    async def test_raises_when_client_not_started(self, handlers):
        a = _grid_adapter(handlers)
        with pytest.raises(RuntimeError):
            await a.list_admin_users(team_id="T1")

    @pytest.mark.asyncio
    async def test_raises_on_slack_api_error(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=err_response("invalid_auth"))
        with pytest.raises(RuntimeError, match="invalid_auth"):
            await a.list_admin_users(team_id="T1")
        await a.stop()


# -- admin.conversations.search --------------------------------------


class TestAdapterAdminConversationsList:
    @pytest.mark.asyncio
    async def test_returns_conversations_payload(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({
            "conversations": [{"id": "C1"}, {"id": "C2"}],
            "next_cursor": "",
        }))
        out = await a.list_admin_conversations(team_id="T1")
        assert out["conversations"] == [{"id": "C1"}, {"id": "C2"}]
        await a.stop()

    @pytest.mark.asyncio
    async def test_uses_org_token_not_bot_token(self, handlers):
        a = _grid_adapter(handlers, org_token="xoxa-ORG-CONV")
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T1")
        headers = a._client.post.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer xoxa-ORG-CONV"
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_team_ids_filter(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T_ALPHA")
        body = a._client.post.call_args.kwargs.get("json", {})
        assert body.get("team_ids") == ["T_ALPHA"]
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_cursor_for_pagination(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T1", cursor="Y29udi0xMA==")
        body = a._client.post.call_args.kwargs.get("json", {})
        assert body.get("cursor") == "Y29udi0xMA=="
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_query_filter_when_supplied(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T1", query="release-")
        body = a._client.post.call_args.kwargs.get("json", {})
        assert body.get("query") == "release-"
        await a.stop()

    @pytest.mark.asyncio
    async def test_targets_admin_conversations_search_endpoint(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T1")
        url = a._client.post.call_args.args[0]
        assert url.endswith("/admin.conversations.search")
        await a.stop()

    @pytest.mark.asyncio
    async def test_passes_limit_default_and_override(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=ok_response({"conversations": []}))
        await a.list_admin_conversations(team_id="T1")
        assert a._client.post.call_args.kwargs["json"]["limit"] == 100
        await a.list_admin_conversations(team_id="T1", limit=10)
        assert a._client.post.call_args.kwargs["json"]["limit"] == 10
        await a.stop()

    @pytest.mark.asyncio
    async def test_raises_when_grid_disabled(self, handlers):
        s = FakeSlackSettings(enterprise_grid=False)
        s.socket_mode = False
        a = SlackAdapter(settings=s, handlers=handlers)
        await a.start()
        with pytest.raises(RuntimeError):
            await a.list_admin_conversations(team_id="T1")
        await a.stop()

    @pytest.mark.asyncio
    async def test_raises_when_client_not_started(self, handlers):
        a = _grid_adapter(handlers)
        with pytest.raises(RuntimeError):
            await a.list_admin_conversations(team_id="T1")

    @pytest.mark.asyncio
    async def test_raises_on_slack_api_error(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        a._client.post = AsyncMock(return_value=err_response("not_authed"))
        with pytest.raises(RuntimeError, match="not_authed"):
            await a.list_admin_conversations(team_id="T1")
        await a.stop()
