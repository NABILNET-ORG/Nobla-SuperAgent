"""Gateway RPC handlers for channel and event bus operations.

Phase 5-Foundation: service setters and basic channel RPC methods.
Full channel message routing is wired in Phase 5A.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nobla.channels.manager import ChannelManager
    from nobla.channels.linking import UserLinkingService
    from nobla.events.bus import NoblaEventBus

_channel_manager: ChannelManager | None = None
_linking_service: UserLinkingService | None = None
_event_bus: NoblaEventBus | None = None


def set_channel_manager(mgr: ChannelManager) -> None:
    global _channel_manager
    _channel_manager = mgr


def set_linking_service(svc: UserLinkingService) -> None:
    global _linking_service
    _linking_service = svc


def set_event_bus(bus: NoblaEventBus) -> None:
    global _event_bus
    _event_bus = bus


def get_channel_manager() -> ChannelManager | None:
    return _channel_manager


def get_linking_service() -> UserLinkingService | None:
    return _linking_service


def get_event_bus() -> NoblaEventBus | None:
    return _event_bus
