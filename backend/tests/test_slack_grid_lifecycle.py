"""Slack Enterprise Grid lifecycle tests — start() + health_check + lifespan integration.

Cycles 7-8 of the v2.1.6 constitutional-restart mission. Lives in a
fresh focused module per the Boy Scout Exception.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


def _grid_adapter(handlers, *, org_token="xoxa-test-org", team_ids=None):
    s = FakeSlackSettings(
        enterprise_grid=True,
        org_token=org_token,
        team_ids=list(team_ids) if team_ids else ["T1", "T2"],
    )
    s.socket_mode = False
    return SlackAdapter(settings=s, handlers=handlers)


def _non_grid_adapter(handlers):
    s = FakeSlackSettings(enterprise_grid=False)
    s.socket_mode = False
    return SlackAdapter(settings=s, handlers=handlers)


# -- start() + health_check tests ------------------------------------


class TestEnterpriseGridStartAndHealth:
    @pytest.mark.asyncio
    async def test_start_grid_valid_config_succeeds(self, handlers):
        a = _grid_adapter(handlers, org_token="xoxa-x", team_ids=["T1"])
        await a.start()
        assert a._running is True
        await a.stop()

    @pytest.mark.asyncio
    async def test_start_grid_missing_org_token_raises(self, handlers):
        s = FakeSlackSettings(
            enterprise_grid=True, org_token="", team_ids=["T1"],
        )
        s.socket_mode = False
        a = SlackAdapter(settings=s, handlers=handlers)
        with pytest.raises(ValueError, match="org_token"):
            await a.start()

    @pytest.mark.asyncio
    async def test_start_grid_missing_team_ids_raises(self, handlers):
        s = FakeSlackSettings(
            enterprise_grid=True, org_token="xoxa-x", team_ids=[],
        )
        s.socket_mode = False
        a = SlackAdapter(settings=s, handlers=handlers)
        with pytest.raises(ValueError, match="team_ids"):
            await a.start()

    @pytest.mark.asyncio
    async def test_start_non_grid_mode_unchanged(self, handlers):
        a = _non_grid_adapter(handlers)
        await a.start()
        assert a._running is True
        await a.stop()

    @pytest.mark.asyncio
    async def test_health_check_grid_both_tokens_ok(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        with patch.object(
            a._client, "post", new_callable=AsyncMock,
            return_value=ok_response({}),
        ) as mock_post:
            result = await a.health_check()
        assert result is True
        # Two auth.test calls in grid mode (bot + org)
        assert mock_post.await_count == 2
        await a.stop()

    @pytest.mark.asyncio
    async def test_health_check_grid_org_token_invalid(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        with patch.object(
            a._client, "post", new_callable=AsyncMock,
            side_effect=[ok_response({}), err_response("invalid_auth")],
        ):
            result = await a.health_check()
        assert result is False
        await a.stop()

    @pytest.mark.asyncio
    async def test_health_check_grid_bot_token_invalid_short_circuits(self, handlers):
        a = _grid_adapter(handlers)
        await a.start()
        with patch.object(
            a._client, "post", new_callable=AsyncMock,
            side_effect=[err_response("invalid_auth")],
        ) as mock_post:
            result = await a.health_check()
        assert result is False
        # Should not attempt the org-token call after bot fails
        assert mock_post.await_count == 1
        await a.stop()

    @pytest.mark.asyncio
    async def test_health_check_non_grid_unchanged(self, handlers):
        a = _non_grid_adapter(handlers)
        await a.start()
        with patch.object(
            a._client, "post", new_callable=AsyncMock,
            return_value=ok_response({}),
        ) as mock_post:
            result = await a.health_check()
        assert result is True
        # Non-grid: only one auth.test call
        assert mock_post.await_count == 1
        await a.stop()
