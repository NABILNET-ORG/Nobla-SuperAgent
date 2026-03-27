"""Channel abstraction: unified message format and adapter interface.

Spec reference: Phase 5-Foundation §4.2 — Channel Abstraction Layer.

Design decision: the existing Flutter WebSocket handler does NOT become a
channel adapter. It remains the primary interface with richer capabilities.
Channels are a secondary interface routing through the same brain/memory/tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enums ──────────────────────────────────────────────────


class AttachmentType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


# ── Data models ────────────────────────────────────────────


@dataclass(slots=True)
class Attachment:
    """File attachment in a channel message."""

    type: AttachmentType
    filename: str
    mime_type: str
    size_bytes: int
    url: str | None = None
    data: bytes | None = None


@dataclass(slots=True)
class InlineAction:
    """Interactive button attached to a response (approve/deny, confirm/cancel).

    action_id format: "{domain}:{resource_id}:{verb}"
    e.g. "approval:req-123:approve", "schedule:task-456:pause"
    """

    action_id: str
    label: str
    style: str = "primary"  # "primary", "danger", "secondary"


@dataclass(slots=True)
class ChannelMessage:
    """Inbound message from any channel, normalized to a common format.

    Attributes:
        channel: Platform name, e.g. "telegram", "discord", "flutter".
        channel_user_id: Platform-specific user identifier.
        nobla_user_id: Mapped Nobla user ID (None before auth/linking).
        conversation_id: Active conversation (None if new).
        content: Text content of the message.
        attachments: File attachments.
        reply_to: Message ID being replied to (platform-specific).
        metadata: Channel-specific extras (e.g. chat_id for Telegram).
    """

    channel: str
    channel_user_id: str
    content: str
    nobla_user_id: str | None = None
    conversation_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChannelResponse:
    """Outbound response to be delivered via a channel adapter.

    Attributes:
        content: Text content.
        attachments: Files to send.
        actions: Inline buttons (e.g. approve/deny for tool approval).
    """

    content: str
    attachments: list[Attachment] = field(default_factory=list)
    actions: list[InlineAction] | None = None


# ── Adapter interface ──────────────────────────────────────


class BaseChannelAdapter(ABC):
    """Abstract base for all channel integrations.

    Adding a new channel = implementing this class. The ChannelManager
    handles registration, lifecycle, and delivery routing.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier, e.g. 'telegram', 'discord'."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter (connect to platform, begin polling/webhook)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the adapter."""
        ...

    @abstractmethod
    async def send(self, channel_user_id: str, response: ChannelResponse) -> None:
        """Send a response to a specific user on this channel."""
        ...

    @abstractmethod
    async def send_notification(self, channel_user_id: str, text: str) -> None:
        """Send a plain-text notification (e.g. schedule result, rollback alert)."""
        ...

    @abstractmethod
    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a platform callback (button press) into (action_id, metadata)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the adapter is healthy and connected."""
        ...
