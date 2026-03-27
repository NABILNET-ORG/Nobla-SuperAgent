"""Channel manager — registers adapters and routes delivery.

Spec reference: Phase 5-Foundation §4.2 — ChannelManager.

Delivery logic: sends to user's most recently active channel by default.
Broadcast to all channels only for priority: urgent events (kill switch,
auto-rollback). Users can override preferred channel via /notify command.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nobla.channels.base import BaseChannelAdapter, ChannelResponse

if TYPE_CHECKING:
    from nobla.channels.linking import UserLinkingService

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages channel adapter lifecycle and message delivery routing."""

    def __init__(self, linking_service: UserLinkingService | None = None) -> None:
        self._adapters: dict[str, BaseChannelAdapter] = {}
        self._linking_service = linking_service

    # ── Registration ───────────────────────────────────────

    def register(self, adapter: BaseChannelAdapter) -> None:
        """Register a channel adapter. Overwrites if name already exists."""
        name = adapter.name
        if name in self._adapters:
            logger.warning("Overwriting existing adapter '%s'", name)
        self._adapters[name] = adapter
        logger.info("Registered channel adapter '%s'", name)

    def unregister(self, channel: str) -> None:
        """Remove a channel adapter by name. No-op if not registered."""
        if channel in self._adapters:
            del self._adapters[channel]
            logger.info("Unregistered channel adapter '%s'", channel)

    def get(self, channel: str) -> BaseChannelAdapter | None:
        """Get an adapter by name."""
        return self._adapters.get(channel)

    def list_active(self) -> list[str]:
        """Return names of all registered adapters."""
        return list(self._adapters.keys())

    # ── Lifecycle ──────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all registered adapters."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.start()
                logger.info("Started channel adapter '%s'", name)
            except Exception:
                logger.exception("Failed to start channel adapter '%s'", name)

    async def stop_all(self) -> None:
        """Stop all registered adapters gracefully."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info("Stopped channel adapter '%s'", name)
            except Exception:
                logger.exception("Failed to stop channel adapter '%s'", name)

    # ── Delivery ───────────────────────────────────────────

    async def deliver(self, user_id: str, response: ChannelResponse) -> bool:
        """Deliver a response to a user's preferred channel.

        Sends to the most recently active channel (via UserLinkingService).
        Returns True if delivery succeeded, False otherwise.
        """
        if self._linking_service is None:
            logger.error("Cannot deliver: no linking service configured")
            return False

        linked = await self._linking_service.get_channels(user_id)
        if not linked:
            logger.warning("No linked channels for user '%s'", user_id)
            return False

        # Find preferred channel (most recently active)
        preferred = linked[0]  # get_channels returns preferred-first
        adapter = self._adapters.get(preferred.channel)
        if adapter is None:
            logger.warning(
                "Preferred channel '%s' not registered for user '%s'",
                preferred.channel,
                user_id,
            )
            # Fallback to any available linked channel
            for link in linked[1:]:
                adapter = self._adapters.get(link.channel)
                if adapter is not None:
                    preferred = link
                    break

        if adapter is None:
            logger.warning("No active adapter found for user '%s'", user_id)
            return False

        try:
            await adapter.send(preferred.channel_user_id, response)
            return True
        except Exception:
            logger.exception(
                "Failed to deliver to user '%s' via '%s'",
                user_id,
                preferred.channel,
            )
            return False

    async def broadcast(self, user_id: str, response: ChannelResponse) -> int:
        """Deliver to ALL linked channels. Used for urgent events only.

        Returns the number of successful deliveries.
        """
        if self._linking_service is None:
            logger.error("Cannot broadcast: no linking service configured")
            return 0

        linked = await self._linking_service.get_channels(user_id)
        delivered = 0
        for link in linked:
            adapter = self._adapters.get(link.channel)
            if adapter is None:
                continue
            try:
                await adapter.send(link.channel_user_id, response)
                delivered += 1
            except Exception:
                logger.exception(
                    "Broadcast failed for user '%s' via '%s'",
                    user_id,
                    link.channel,
                )
        return delivered

    async def health(self) -> dict[str, bool]:
        """Health check all registered adapters."""
        results: dict[str, bool] = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.health_check()
            except Exception:
                results[name] = False
        return results
