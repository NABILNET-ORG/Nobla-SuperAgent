"""Slack Enterprise Grid handler tests — enterprise_id extraction.

Cycle 3 of the v2.1.6 constitutional-restart mission. Lives in a fresh
focused module per the Boy Scout Exception (no growth on the
grandfathered test_slack_adapter.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nobla.channels.slack.handlers import SlackHandlers
from nobla.channels.slack.models import SlackUserContext
from tests._slack_grid_helpers import make_slack_event


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
        linking=linking,
        event_bus=event_bus,
        bot_token="xoxb-test-token",
        bot_user_id="U_BOT",
        max_file_size_mb=100,
    )
    h.set_send_fn(AsyncMock())
    return h


# -- Tests -----------------------------------------------------------


class TestHandlerEnterpriseIdExtraction:
    @pytest.mark.asyncio
    async def test_enterprise_id_extracted_from_top_level(self, handlers):
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["enterprise_id"] = "E0ABCDEF"
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        handlers._handle_message = _spy
        await handlers.handle_event(payload)
        assert len(captured) == 1
        assert captured[0].enterprise_id == "E0ABCDEF"

    @pytest.mark.asyncio
    async def test_enterprise_id_extracted_from_nested_enterprise(self, handlers):
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["enterprise"] = {"id": "E_NESTED"}
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        handlers._handle_message = _spy
        await handlers.handle_event(payload)
        assert captured[0].enterprise_id == "E_NESTED"

    @pytest.mark.asyncio
    async def test_enterprise_id_none_when_absent(self, handlers):
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        handlers._handle_message = _spy
        await handlers.handle_event(payload)
        assert captured[0].enterprise_id is None

    @pytest.mark.asyncio
    async def test_enterprise_id_top_level_takes_precedence(self, handlers):
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["enterprise_id"] = "E_TOP"
        payload["enterprise"] = {"id": "E_NESTED"}
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        handlers._handle_message = _spy
        await handlers.handle_event(payload)
        assert captured[0].enterprise_id == "E_TOP"


def _grid_handlers(linking, event_bus, *, team_ids, enterprise_grid=True):
    h = SlackHandlers(
        linking=linking,
        event_bus=event_bus,
        bot_token="xoxb-test-token",
        bot_user_id="U_BOT",
        max_file_size_mb=100,
        enterprise_grid=enterprise_grid,
        team_ids=team_ids,
    )
    h.set_send_fn(AsyncMock())
    return h


class TestEnterpriseGridRouting:
    @pytest.mark.asyncio
    async def test_grid_drops_event_from_non_allowlisted_team(self, linking, event_bus):
        h = _grid_handlers(linking, event_bus, team_ids=["T_OK_1", "T_OK_2"])
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        h._handle_message = _spy
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["team_id"] = "T_BAD"
        await h.handle_event(payload)
        assert captured == []
        linking.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_grid_allows_event_from_allowlisted_team(self, linking, event_bus):
        h = _grid_handlers(linking, event_bus, team_ids=["T_OK_1", "T_OK_2"])
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        h._handle_message = _spy
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["team_id"] = "T_OK_1"
        await h.handle_event(payload)
        assert len(captured) == 1
        assert captured[0].team_id == "T_OK_1"

    @pytest.mark.asyncio
    async def test_grid_disabled_does_not_filter_team_ids(self, linking, event_bus):
        h = _grid_handlers(linking, event_bus, team_ids=["T_OK_1"], enterprise_grid=False)
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        h._handle_message = _spy
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["team_id"] = "T_NOT_IN_LIST"
        await h.handle_event(payload)
        assert len(captured) == 1

    @pytest.mark.asyncio
    async def test_grid_empty_team_ids_does_not_filter(self, linking, event_bus):
        h = _grid_handlers(linking, event_bus, team_ids=[])
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        h._handle_message = _spy
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["team_id"] = "T_ANY"
        await h.handle_event(payload)
        assert len(captured) == 1

    @pytest.mark.asyncio
    async def test_grid_allowlist_is_exact_match(self, linking, event_bus):
        h = _grid_handlers(linking, event_bus, team_ids=["T1"])
        captured: list[SlackUserContext] = []
        async def _spy(ctx, text, raw_event):
            captured.append(ctx)
        h._handle_message = _spy
        payload = make_slack_event(text="hello", channel="D789", channel_type="im")
        payload["team_id"] = "T1X"  # prefix match must NOT count
        await h.handle_event(payload)
        assert captured == []

    def test_grid_default_kwargs_back_compat(self, linking, event_bus):
        h = SlackHandlers(
            linking=linking, event_bus=event_bus,
            bot_token="xoxb-x", bot_user_id="U_BOT",
            max_file_size_mb=100,
        )
        assert h._enterprise_grid is False
        assert h._team_ids == []
