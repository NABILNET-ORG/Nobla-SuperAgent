"""Slack channel adapter data models and API constants (Phase 5-Channels).

Spec reference: Slack Web API + Events API + Socket Mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# -- API constants ---------------------------------------------------

CHANNEL_NAME = "slack"

# Slack message limits
MAX_MESSAGE_LENGTH = 4000  # chat.postMessage text field limit
MAX_BLOCKS = 50  # Maximum blocks per message
MAX_ACTIONS = 5  # Maximum actions per actions block
MAX_BUTTON_TEXT_LENGTH = 75  # Button text limit
MAX_OPTION_TEXT_LENGTH = 75
MAX_FILE_SIZE_BYTES = 1_000_000_000  # 1 GB (Slack file upload limit)

SLACK_API_BASE = "https://slack.com/api"

# MIME type -> Slack-friendly type mapping
MIME_TO_MEDIA_TYPE: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/ogg": "audio",
    "audio/wav": "audio",
    "video/mp4": "video",
    "video/quicktime": "video",
    "application/pdf": "document",
    "application/zip": "document",
    "text/plain": "snippet",
    "text/csv": "snippet",
    "application/json": "snippet",
}


# -- Data models -----------------------------------------------------


@dataclass(slots=True)
class SlackUserContext:
    """Normalized context extracted from an inbound Slack event payload.

    Attributes:
        user_id: Slack user ID (U...).
        display_name: User's display name.
        team_id: Slack workspace/team ID (T...).
        channel_id: Channel ID (C... for channels, D... for DMs).
        message_ts: Message timestamp (Slack's unique message ID).
        thread_ts: Thread parent timestamp (None if not in thread).
        is_dm: Whether this message is a direct message.
        is_thread: Whether this message is in a thread.
        is_bot_mentioned: Whether the bot was @mentioned.
        raw_extras: Catch-all for platform-specific fields.
    """

    user_id: str
    display_name: str
    team_id: str
    channel_id: str
    message_ts: str
    thread_ts: str | None = None
    is_dm: bool = False
    is_thread: bool = False
    is_bot_mentioned: bool = False
    raw_extras: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id_str(self) -> str:
        return self.user_id

    @property
    def channel_id_str(self) -> str:
        return self.channel_id


# -- Webhook / event payload types -----------------------------------

# Event types the adapter handles
SUPPORTED_EVENT_TYPES = frozenset({
    "message",
    "app_mention",
})

# Message subtypes to ignore (bot messages, edits, etc.)
IGNORED_SUBTYPES = frozenset({
    "bot_message",
    "message_changed",
    "message_deleted",
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "file_share",  # handled separately via files
})
