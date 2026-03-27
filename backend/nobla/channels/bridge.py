"""Channel-to-executor bridge — synthetic ConnectionState for channel requests.

Spec reference: Phase 5-Foundation §4.2 — Channel-to-Executor Bridge.

The existing executor pipeline requires a ConnectionState (WebSocket-specific
dataclass). Channel adapters construct a ChannelConnectionState from the
LinkedUser returned by UserLinkingService.resolve().

The executor pipeline sees a valid ConnectionState and requires no changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from nobla.channels.linking import LinkedUser


@dataclass
class ChannelConnectionState:
    """Synthetic ConnectionState for channel-originated requests.

    Mirrors the interface of gateway.websocket.ConnectionState so the
    executor pipeline (PermissionChecker, ApprovalManager, AuditLogger)
    can process channel requests identically to WebSocket requests.

    Attributes:
        connection_id: "{channel}:{channel_user_id}" (e.g. "telegram:123456").
        user_id: From LinkedUser.nobla_user_id.
        tier: From LinkedUser.tier (int).
        passphrase_hash: Retrieved from user's auth record.
        source_channel: Origin channel name for routing responses back.
    """

    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    tier: int = 1  # Default: SAFE
    passphrase_hash: str | None = None
    source_channel: str = ""  # "telegram", "discord" — extra field for routing


def create_channel_connection(
    linked_user: LinkedUser,
    channel: str,
    channel_user_id: str,
    passphrase_hash: str | None = None,
) -> ChannelConnectionState:
    """Build a ChannelConnectionState from a resolved LinkedUser.

    Called by each adapter's message handler before routing to the gateway.
    The executor pipeline sees a valid ConnectionState and requires no changes.
    """
    return ChannelConnectionState(
        connection_id=f"{channel}:{channel_user_id}",
        user_id=linked_user.nobla_user_id,
        tier=int(linked_user.tier),
        passphrase_hash=passphrase_hash,
        source_channel=channel,
    )
