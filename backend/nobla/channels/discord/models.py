"""Discord-specific data models (Phase 5A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DiscordUserContext:
    """Per-message context extracted from a Discord message.

    Carries Discord-specific metadata alongside the normalized
    ChannelMessage so handlers can reference guild/channel details
    without coupling to the raw ``discord.Message`` object.
    """

    channel_id: int
    user_id: int
    username: str | None = None
    display_name: str | None = None
    guild_id: int | None = None
    is_guild: bool = False
    is_bot_mentioned: bool = False
    is_reply_to_bot: bool = False
    message_id: int | None = None
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def channel_id_str(self) -> str:
        return str(self.channel_id)

    @property
    def user_id_str(self) -> str:
        return str(self.user_id)


# Discord API constants
MAX_MESSAGE_LENGTH = 2000
MAX_EMBED_DESCRIPTION = 4096
MAX_FILE_SIZE_DEFAULT_MB = 25
MAX_FILE_SIZE_BOOSTED_MB = 100

MIME_TO_EMBED_TYPE = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/webm": "video",
    "audio/mpeg": "audio",
    "audio/ogg": "audio",
    "audio/wav": "audio",
}
