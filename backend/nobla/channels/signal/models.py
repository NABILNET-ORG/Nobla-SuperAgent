"""Signal adapter models, constants, and user context (Phase 5-Channels).

signal-cli JSON-RPC daemon interface constants and data classes.
"""

from __future__ import annotations

from dataclasses import dataclass

CHANNEL_NAME = "signal"
MAX_MESSAGE_LENGTH = 6000

# JSON-RPC method names for signal-cli daemon
RPC_METHODS: dict[str, str] = {
    "send": "send",
    "receive": "receive",
    "version": "version",
    "list_accounts": "listAccounts",
    "send_receipt": "sendReceipt",
    "send_typing": "sendTyping",
    "get_group": "getGroup",
    "list_groups": "listGroups",
}

# Receipt types
RECEIPT_TYPE_DELIVERY = "delivery"
RECEIPT_TYPE_READ = "read"
RECEIPT_TYPE_VIEWED = "viewed"

# Supported attachment MIME types
SUPPORTED_MIME_TYPES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "video/mp4", "video/3gpp",
    "audio/mpeg", "audio/ogg", "audio/aac",
    "application/pdf", "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})


@dataclass(frozen=True)
class SignalUserContext:
    """Normalized context from an incoming Signal envelope.

    Attributes:
        source_number: Sender phone number (E.164 format).
        source_uuid: Sender UUID assigned by Signal.
        is_group: Whether message came from a group chat.
        is_bot_mentioned: Whether bot was mentioned in a group.
        timestamp: Signal envelope timestamp (milliseconds).
        group_id: Group identifier (None for DMs).
        expires_in_seconds: Disappearing message timer (0 = disabled).
    """

    source_number: str
    source_uuid: str
    is_group: bool
    is_bot_mentioned: bool
    timestamp: int
    group_id: str | None = None
    expires_in_seconds: int = 0

    @property
    def user_id_str(self) -> str:
        return self.source_number

    @property
    def chat_id_str(self) -> str:
        return self.group_id if self.group_id else self.source_number

    @property
    def is_disappearing(self) -> bool:
        return self.expires_in_seconds > 0
