"""Telegram-specific data models (Phase 5A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TelegramUserContext:
    """Per-message context extracted from a Telegram update.

    Carries Telegram-specific metadata alongside the normalized
    ChannelMessage so handlers can reference chat details without
    coupling to the raw ``telegram.Update`` object.
    """

    chat_id: int
    user_id: int
    username: str | None = None
    first_name: str | None = None
    is_group: bool = False
    is_bot_mentioned: bool = False
    is_reply_to_bot: bool = False
    message_id: int | None = None
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def chat_id_str(self) -> str:
        return str(self.chat_id)

    @property
    def user_id_str(self) -> str:
        return str(self.user_id)


# Telegram API constants
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MIME_TO_SEND_METHOD = {
    "image/jpeg": "send_photo",
    "image/png": "send_photo",
    "image/gif": "send_animation",
    "image/webp": "send_sticker",
    "audio/mpeg": "send_audio",
    "audio/ogg": "send_voice",
    "audio/wav": "send_audio",
    "video/mp4": "send_video",
    "video/webm": "send_video_note",
}
