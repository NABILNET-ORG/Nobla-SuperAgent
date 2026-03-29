"""WhatsApp channel adapter data models and API constants (Phase 5-Channels).

Spec reference: WhatsApp Business Cloud API v21.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── API constants ─────────────────────────────────────────

CHANNEL_NAME = "whatsapp"

# WhatsApp Cloud API limits
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_BUTTON_TEXT_LENGTH = 20
MAX_BUTTONS = 3  # Interactive reply buttons
MAX_LIST_ITEMS = 10  # Interactive list rows
MAX_LIST_SECTIONS = 10

GRAPH_API_BASE = "https://graph.facebook.com"

# MIME type → WhatsApp media type mapping
MIME_TO_MEDIA_TYPE: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "audio/aac": "audio",
    "audio/mp4": "audio",
    "audio/mpeg": "audio",
    "audio/ogg": "audio",
    "audio/opus": "audio",
    "video/mp4": "video",
    "video/3gpp": "video",
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.ms-excel": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "text/plain": "document",
}


# ── Data models ───────────────────────────────────────────


@dataclass(slots=True)
class WhatsAppUserContext:
    """Normalized context extracted from an inbound WhatsApp webhook payload.

    Attributes:
        wa_id: WhatsApp ID of the sender (phone number without +).
        display_name: Profile name of the sender.
        message_id: Platform message ID (wamid.*).
        chat_id: For 1-on-1 this equals wa_id; for groups it's the group JID.
        is_group: Whether this message came from a group chat.
        is_bot_mentioned: Whether the bot was @mentioned in a group.
        is_reply_to_bot: Whether this is a reply to a bot message.
        timestamp: Unix timestamp string from the webhook.
        raw_extras: Catch-all for platform-specific fields.
    """

    wa_id: str
    display_name: str
    message_id: str
    chat_id: str
    is_group: bool = False
    is_bot_mentioned: bool = False
    is_reply_to_bot: bool = False
    timestamp: str = ""
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def chat_id_str(self) -> str:
        return self.chat_id

    @property
    def user_id_str(self) -> str:
        return self.wa_id


# ── Webhook payload types ─────────────────────────────────

# Message types the adapter handles
SUPPORTED_MESSAGE_TYPES = frozenset({
    "text", "image", "audio", "video", "document",
    "sticker", "location", "contacts", "interactive",
    "reaction", "button",
})

# Status values for message status updates
MESSAGE_STATUSES = frozenset({"sent", "delivered", "read", "failed"})
