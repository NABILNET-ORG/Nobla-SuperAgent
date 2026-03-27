"""User linking service — maps platform identities to Nobla accounts.

Spec reference: Phase 5-Foundation §4.2 — User Linking.

Auth flow: Unlinked user sends message -> adapter cannot resolve ->
emits channel.auth.required -> adapter sends one-time pairing code ->
user enters it in Flutter or via /link command -> accounts linked.
All subsequent messages auto-resolve.
Unlinked users get a pairing prompt and nothing else — no open access.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone

from nobla.security.permissions import Tier

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LinkedChannel:
    """A specific platform link for a Nobla user."""

    channel: str          # "telegram", "discord"
    channel_user_id: str  # Platform-specific user ID
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class LinkedUser:
    """Resolved Nobla user from a channel identity."""

    nobla_user_id: str
    tier: Tier
    preferred_channel: str  # Most recently active channel


# ── Pairing code ───────────────────────────────────────────

PAIRING_CODE_LENGTH = 6
PAIRING_CODE_TTL_SECONDS = 300  # 5 minutes


@dataclass(slots=True)
class PairingRequest:
    """Pending pairing code awaiting user confirmation."""

    code: str
    channel: str
    channel_user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed > PAIRING_CODE_TTL_SECONDS


def _generate_pairing_code() -> str:
    """Generate a short, user-friendly pairing code (6 uppercase alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(PAIRING_CODE_LENGTH))


# ── Service ────────────────────────────────────────────────


class UserLinkingService:
    """Maps platform identities to Nobla user accounts.

    In-memory implementation for Phase 5-Foundation. PostgreSQL persistence
    will be added in Phase 5A when channel bots go live.
    """

    def __init__(self) -> None:
        # {(channel, channel_user_id): LinkedUser}
        self._links: dict[tuple[str, str], LinkedUser] = {}
        # {nobla_user_id: [LinkedChannel, ...]}  — preferred channel first
        self._user_channels: dict[str, list[LinkedChannel]] = {}
        # {code: PairingRequest}
        self._pending_pairings: dict[str, PairingRequest] = {}

    async def link(
        self,
        channel: str,
        channel_user_id: str,
        nobla_user_id: str,
        tier: Tier = Tier.SAFE,
    ) -> None:
        """Link a channel identity to a Nobla account."""
        key = (channel, channel_user_id)
        self._links[key] = LinkedUser(
            nobla_user_id=nobla_user_id,
            tier=tier,
            preferred_channel=channel,
        )

        # Add to user's channel list (avoid duplicates)
        channels = self._user_channels.setdefault(nobla_user_id, [])
        if not any(c.channel == channel and c.channel_user_id == channel_user_id for c in channels):
            channels.insert(0, LinkedChannel(channel=channel, channel_user_id=channel_user_id))

        logger.info(
            "Linked %s:%s -> nobla user '%s'", channel, channel_user_id, nobla_user_id
        )

    async def unlink(self, channel: str, channel_user_id: str) -> None:
        """Remove a channel link. No-op if not linked."""
        key = (channel, channel_user_id)
        linked = self._links.pop(key, None)
        if linked is None:
            return

        channels = self._user_channels.get(linked.nobla_user_id, [])
        self._user_channels[linked.nobla_user_id] = [
            c for c in channels
            if not (c.channel == channel and c.channel_user_id == channel_user_id)
        ]
        logger.info("Unlinked %s:%s", channel, channel_user_id)

    async def resolve(self, channel: str, channel_user_id: str) -> LinkedUser | None:
        """Resolve a channel identity to a linked Nobla user.

        Returns None if the user is not linked (trigger pairing flow).
        Updates preferred_channel to the current channel on resolve.
        """
        key = (channel, channel_user_id)
        linked = self._links.get(key)
        if linked is not None:
            # Update preferred channel to most recently active
            linked.preferred_channel = channel
        return linked

    async def get_channels(self, nobla_user_id: str) -> list[LinkedChannel]:
        """Get all linked channels for a Nobla user (preferred first)."""
        return self._user_channels.get(nobla_user_id, [])

    # ── Pairing flow ───────────────────────────────────────

    async def create_pairing_code(
        self, channel: str, channel_user_id: str
    ) -> str:
        """Generate a pairing code for an unlinked channel user."""
        # Clean expired codes
        self._pending_pairings = {
            code: req
            for code, req in self._pending_pairings.items()
            if not req.is_expired
        }

        code = _generate_pairing_code()
        self._pending_pairings[code] = PairingRequest(
            code=code,
            channel=channel,
            channel_user_id=channel_user_id,
        )
        logger.info("Created pairing code for %s:%s", channel, channel_user_id)
        return code

    async def complete_pairing(
        self, code: str, nobla_user_id: str, tier: Tier = Tier.SAFE
    ) -> bool:
        """Complete a pairing by code. Returns True if successful."""
        request = self._pending_pairings.pop(code, None)
        if request is None or request.is_expired:
            return False

        await self.link(
            channel=request.channel,
            channel_user_id=request.channel_user_id,
            nobla_user_id=nobla_user_id,
            tier=tier,
        )
        return True

    async def update_tier(
        self, channel: str, channel_user_id: str, tier: Tier
    ) -> bool:
        """Update the permission tier for a linked user."""
        key = (channel, channel_user_id)
        linked = self._links.get(key)
        if linked is None:
            return False
        linked.tier = tier
        return True
