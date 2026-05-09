"""Facebook Messenger channel adapter data models and API constants (Phase 5-Channels).

Spec reference: Messenger Platform / Send API on Meta Graph API v21.0.

Messenger uses Page-Scoped IDs (PSIDs) as the user identifier — distinct from
WhatsApp's wa_id (phone number). PSIDs are opaque to the page and stable per
(page, user) pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── API constants ─────────────────────────────────────────

CHANNEL_NAME = "messenger"

# Graph API base + default version (Messenger Send API lives on the same host).
GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"

# Messenger platform limits
MAX_MESSAGE_LENGTH = 2000  # Plain-text body cap
MAX_QUICK_REPLIES = 13     # Send API quick_replies cap
MAX_BUTTONS = 3            # Button template cap (per attachment)
MAX_GENERIC_TEMPLATE_ELEMENTS = 10  # Generic template element cap
MAX_LIST_ITEMS = 4         # List template (legacy) row cap

# Messenger quick-reply title cap (UTF-8 chars)
MAX_QUICK_REPLY_TITLE_LENGTH = 20
# Messenger button title cap (UTF-8 chars)
MAX_BUTTON_TITLE_LENGTH = 20
# Messenger postback payload cap
MAX_POSTBACK_PAYLOAD_LENGTH = 1000


# ── Data models ───────────────────────────────────────────


@dataclass(slots=True)
class MessengerUserContext:
    """Normalized context extracted from an inbound Messenger webhook event.

    Attributes:
        psid: Page-Scoped ID of the sender (Messenger's user identifier).
        display_name: Display name of the sender, when available.
        message_id: Platform message ID (mid.*).
        chat_id: For 1:1 this equals psid; group threads carry a distinct id.
        is_group: Whether this message came from a group thread.
        is_bot_mentioned: Whether the bot was @mentioned in a group.
        is_reply_to_bot: Whether this is a reply to a bot message.
        timestamp: Unix timestamp in milliseconds from the Messenger payload.
        raw_extras: Catch-all for platform-specific fields.
    """

    psid: str
    display_name: str | None = None
    message_id: str = ""
    chat_id: str = ""
    is_group: bool = False
    is_bot_mentioned: bool = False
    is_reply_to_bot: bool = False
    timestamp: int = 0
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def chat_id_str(self) -> str:
        return self.chat_id or self.psid

    @property
    def user_id_str(self) -> str:
        return self.psid

    @property
    def is_dm(self) -> bool:
        """Convenience: True when the message originates from a 1:1 thread."""
        return not self.is_group


# ── Webhook payload types ─────────────────────────────────

# Message types the adapter handles (mapped from Messenger attachment.type
# values plus our synthetic "text" type for non-attachment messages).
SUPPORTED_MESSAGE_TYPES = frozenset({
    "text", "image", "video", "audio", "file", "location",
})

# Send API messaging_type values
MESSAGING_TYPES = frozenset({"RESPONSE", "UPDATE", "MESSAGE_TAG"})

# Webhook subscription fields the adapter subscribes to / processes
WEBHOOK_FIELDS = frozenset({
    "messages",
    "messaging_postbacks",
    "messaging_deliveries",
    "messaging_reads",
})
