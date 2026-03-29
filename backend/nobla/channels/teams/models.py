"""Microsoft Teams channel adapter data models and API constants (Phase 5-Channels).

Spec reference: Azure Bot Framework REST API + Adaptive Cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# -- API constants ---------------------------------------------------

CHANNEL_NAME = "teams"

MAX_CARD_SIZE_BYTES = 28_672
MAX_CARD_ACTIONS = 5
MAX_TEXT_BLOCK_LENGTH = 10_000
MAX_ATTACHMENT_INLINE_BYTES = 262_144
MAX_FILE_SIZE_BYTES = 104_857_600

BOT_FRAMEWORK_TOKEN_URL = (
    "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
)
BOT_FRAMEWORK_OPENID_URL = (
    "https://login.botframework.com/v1/.well-known/openidconfiguration"
)
BOT_FRAMEWORK_TOKEN_SCOPE = "https://api.botframework.com/.default"

MIME_TO_MEDIA_TYPE: dict[str, str] = {
    "image/jpeg": "image", "image/png": "image", "image/gif": "image", "image/webp": "image",
    "audio/mpeg": "audio", "audio/mp4": "audio", "audio/ogg": "audio", "audio/wav": "audio",
    "video/mp4": "video", "video/quicktime": "video",
    "application/pdf": "document", "application/zip": "document",
    "text/plain": "document", "text/csv": "document", "application/json": "document",
}

SUPPORTED_ACTIVITY_TYPES = frozenset({
    "message", "invoke", "conversationUpdate", "messageReaction",
})

IGNORED_ACTIVITY_TYPES = frozenset({
    "typing", "endOfConversation", "event", "installationUpdate",
})


@dataclass(slots=True)
class TeamsUserContext:
    """Normalized context extracted from an inbound Teams Activity."""
    user_id: str
    display_name: str
    tenant_id: str
    conversation_id: str
    service_url: str
    message_id: str
    channel_id: str | None = None
    is_dm: bool = False
    is_bot_mentioned: bool = False
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id_str(self) -> str:
        return self.user_id

    @property
    def channel_id_str(self) -> str:
        return self.channel_id or self.conversation_id
