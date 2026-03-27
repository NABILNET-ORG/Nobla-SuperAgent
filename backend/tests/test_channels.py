"""Tests for the Channel Abstraction Layer (Phase 5-Foundation §4.2).

Covers: models, BaseChannelAdapter, ChannelManager, UserLinkingService, bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    BaseChannelAdapter,
    ChannelMessage,
    ChannelResponse,
    InlineAction,
)
from nobla.channels.bridge import ChannelConnectionState, create_channel_connection
from nobla.channels.linking import (
    LinkedUser,
    PairingRequest,
    UserLinkingService,
)
from nobla.channels.manager import ChannelManager
from nobla.security.permissions import Tier


# ── Fake adapter for testing ───────────────────────────────


class FakeAdapter(BaseChannelAdapter):
    """Minimal adapter for testing ChannelManager."""

    def __init__(self, channel_name: str = "fake") -> None:
        self._name = channel_name
        self.started = False
        self.stopped = False
        self.sent: list[tuple[str, ChannelResponse]] = []
        self.notifications: list[tuple[str, str]] = []
        self._healthy = True

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, channel_user_id: str, response: ChannelResponse) -> None:
        self.sent.append((channel_user_id, response))

    async def send_notification(self, channel_user_id: str, text: str) -> None:
        self.notifications.append((channel_user_id, text))

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        return (str(raw_callback), {})

    async def health_check(self) -> bool:
        return self._healthy


# ── Model tests ────────────────────────────────────────────


class TestChannelModels:
    def test_attachment(self):
        att = Attachment(
            type=AttachmentType.IMAGE,
            filename="photo.jpg",
            mime_type="image/jpeg",
            size_bytes=1024,
            url="https://example.com/photo.jpg",
        )
        assert att.type == AttachmentType.IMAGE
        assert att.filename == "photo.jpg"
        assert att.data is None

    def test_inline_action_defaults(self):
        action = InlineAction(action_id="approval:123:approve", label="Approve")
        assert action.style == "primary"

    def test_channel_message(self):
        msg = ChannelMessage(
            channel="telegram",
            channel_user_id="tg-123",
            content="Hello",
        )
        assert msg.nobla_user_id is None
        assert msg.attachments == []
        assert msg.metadata == {}

    def test_channel_response_with_actions(self):
        resp = ChannelResponse(
            content="Tool: code.run",
            actions=[
                InlineAction(action_id="approve", label="Approve", style="primary"),
                InlineAction(action_id="deny", label="Deny", style="danger"),
            ],
        )
        assert len(resp.actions) == 2
        assert resp.actions[1].style == "danger"


# ── ChannelManager tests ──────────────────────────────────


class TestChannelManager:
    @pytest.mark.asyncio
    async def test_register_and_list(self):
        mgr = ChannelManager()
        adapter = FakeAdapter("telegram")
        mgr.register(adapter)
        assert mgr.list_active() == ["telegram"]
        assert mgr.get("telegram") is adapter

    @pytest.mark.asyncio
    async def test_unregister(self):
        mgr = ChannelManager()
        mgr.register(FakeAdapter("telegram"))
        mgr.unregister("telegram")
        assert mgr.list_active() == []
        assert mgr.get("telegram") is None

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_noop(self):
        mgr = ChannelManager()
        mgr.unregister("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_start_all(self):
        mgr = ChannelManager()
        tg = FakeAdapter("telegram")
        dc = FakeAdapter("discord")
        mgr.register(tg)
        mgr.register(dc)
        await mgr.start_all()
        assert tg.started
        assert dc.started

    @pytest.mark.asyncio
    async def test_stop_all(self):
        mgr = ChannelManager()
        tg = FakeAdapter("telegram")
        mgr.register(tg)
        await mgr.stop_all()
        assert tg.stopped

    @pytest.mark.asyncio
    async def test_deliver_no_linking_service(self):
        mgr = ChannelManager()
        result = await mgr.deliver("user-1", ChannelResponse(content="hi"))
        assert result is False

    @pytest.mark.asyncio
    async def test_deliver_to_preferred_channel(self):
        linking = UserLinkingService()
        await linking.link("telegram", "tg-123", "user-1", Tier.STANDARD)

        mgr = ChannelManager(linking_service=linking)
        tg = FakeAdapter("telegram")
        mgr.register(tg)

        resp = ChannelResponse(content="Hello!")
        result = await mgr.deliver("user-1", resp)

        assert result is True
        assert len(tg.sent) == 1
        assert tg.sent[0] == ("tg-123", resp)

    @pytest.mark.asyncio
    async def test_deliver_fallback_channel(self):
        linking = UserLinkingService()
        await linking.link("telegram", "tg-123", "user-1")
        await linking.link("discord", "dc-456", "user-1")

        mgr = ChannelManager(linking_service=linking)
        # Only discord adapter registered (telegram missing)
        dc = FakeAdapter("discord")
        mgr.register(dc)

        resp = ChannelResponse(content="Fallback")
        result = await mgr.deliver("user-1", resp)

        assert result is True
        assert len(dc.sent) == 1

    @pytest.mark.asyncio
    async def test_deliver_no_linked_channels(self):
        linking = UserLinkingService()
        mgr = ChannelManager(linking_service=linking)
        result = await mgr.deliver("unknown-user", ChannelResponse(content="hi"))
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self):
        linking = UserLinkingService()
        await linking.link("telegram", "tg-1", "user-1")
        await linking.link("discord", "dc-1", "user-1")

        mgr = ChannelManager(linking_service=linking)
        tg = FakeAdapter("telegram")
        dc = FakeAdapter("discord")
        mgr.register(tg)
        mgr.register(dc)

        resp = ChannelResponse(content="URGENT")
        count = await mgr.broadcast("user-1", resp)

        assert count == 2
        assert len(tg.sent) == 1
        assert len(dc.sent) == 1

    @pytest.mark.asyncio
    async def test_health(self):
        mgr = ChannelManager()
        tg = FakeAdapter("telegram")
        dc = FakeAdapter("discord")
        dc._healthy = False
        mgr.register(tg)
        mgr.register(dc)

        health = await mgr.health()
        assert health == {"telegram": True, "discord": False}


# ── UserLinkingService tests ──────────────────────────────


class TestUserLinkingService:
    @pytest.mark.asyncio
    async def test_link_and_resolve(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-123", "user-1", Tier.STANDARD)

        user = await svc.resolve("telegram", "tg-123")
        assert user is not None
        assert user.nobla_user_id == "user-1"
        assert user.tier == Tier.STANDARD

    @pytest.mark.asyncio
    async def test_resolve_unlinked_returns_none(self):
        svc = UserLinkingService()
        assert await svc.resolve("telegram", "unknown") is None

    @pytest.mark.asyncio
    async def test_resolve_updates_preferred_channel(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-1", "user-1")
        await svc.link("discord", "dc-1", "user-1")

        # Resolve via discord should update preferred
        user = await svc.resolve("discord", "dc-1")
        assert user is not None
        assert user.preferred_channel == "discord"

    @pytest.mark.asyncio
    async def test_unlink(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-1", "user-1")
        await svc.unlink("telegram", "tg-1")
        assert await svc.resolve("telegram", "tg-1") is None

    @pytest.mark.asyncio
    async def test_unlink_nonexistent_noop(self):
        svc = UserLinkingService()
        await svc.unlink("telegram", "unknown")  # should not raise

    @pytest.mark.asyncio
    async def test_get_channels(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-1", "user-1")
        await svc.link("discord", "dc-1", "user-1")

        channels = await svc.get_channels("user-1")
        assert len(channels) == 2
        channel_names = [c.channel for c in channels]
        assert "telegram" in channel_names
        assert "discord" in channel_names

    @pytest.mark.asyncio
    async def test_get_channels_empty(self):
        svc = UserLinkingService()
        assert await svc.get_channels("unknown") == []

    @pytest.mark.asyncio
    async def test_duplicate_link_no_duplicate_channels(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-1", "user-1")
        await svc.link("telegram", "tg-1", "user-1")  # duplicate

        channels = await svc.get_channels("user-1")
        assert len(channels) == 1

    @pytest.mark.asyncio
    async def test_pairing_flow(self):
        svc = UserLinkingService()
        code = await svc.create_pairing_code("telegram", "tg-999")
        assert len(code) == 6

        success = await svc.complete_pairing(code, "user-1", Tier.STANDARD)
        assert success is True

        user = await svc.resolve("telegram", "tg-999")
        assert user is not None
        assert user.nobla_user_id == "user-1"
        assert user.tier == Tier.STANDARD

    @pytest.mark.asyncio
    async def test_pairing_invalid_code(self):
        svc = UserLinkingService()
        result = await svc.complete_pairing("BADCODE", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_pairing_code_single_use(self):
        svc = UserLinkingService()
        code = await svc.create_pairing_code("telegram", "tg-1")
        await svc.complete_pairing(code, "user-1")
        # Second use should fail
        assert await svc.complete_pairing(code, "user-2") is False

    @pytest.mark.asyncio
    async def test_update_tier(self):
        svc = UserLinkingService()
        await svc.link("telegram", "tg-1", "user-1", Tier.SAFE)
        result = await svc.update_tier("telegram", "tg-1", Tier.ADMIN)
        assert result is True

        user = await svc.resolve("telegram", "tg-1")
        assert user is not None
        assert user.tier == Tier.ADMIN

    @pytest.mark.asyncio
    async def test_update_tier_unlinked(self):
        svc = UserLinkingService()
        assert await svc.update_tier("telegram", "unknown", Tier.ADMIN) is False


# ── Bridge tests ──────────────────────────────────────────


class TestChannelBridge:
    def test_create_channel_connection(self):
        linked = LinkedUser(
            nobla_user_id="user-1",
            tier=Tier.ELEVATED,
            preferred_channel="telegram",
        )
        conn = create_channel_connection(
            linked_user=linked,
            channel="telegram",
            channel_user_id="tg-123",
            passphrase_hash="hash-abc",
        )
        assert conn.connection_id == "telegram:tg-123"
        assert conn.user_id == "user-1"
        assert conn.tier == 3  # ELEVATED as int
        assert conn.passphrase_hash == "hash-abc"
        assert conn.source_channel == "telegram"

    def test_channel_connection_state_defaults(self):
        conn = ChannelConnectionState()
        assert conn.user_id is None
        assert conn.tier == 1
        assert conn.passphrase_hash is None
        assert conn.source_channel == ""
        assert conn.connection_id  # auto-generated UUID

    def test_matches_websocket_connection_state_interface(self):
        """ChannelConnectionState must have the same core fields as ConnectionState."""
        conn = ChannelConnectionState(
            connection_id="test:1",
            user_id="u1",
            tier=2,
            passphrase_hash="hash",
        )
        # These are the fields ToolExecutor/PermissionChecker access
        assert hasattr(conn, "connection_id")
        assert hasattr(conn, "user_id")
        assert hasattr(conn, "tier")
        assert hasattr(conn, "passphrase_hash")
