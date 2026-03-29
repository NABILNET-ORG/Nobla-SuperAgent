"""WhatsApp message formatting and interactive message building (Phase 5-Channels).

WhatsApp supports a subset of formatting:
  *bold*  _italic_  ~strikethrough~  ```monospace```  > quote (line-start)

Interactive messages use structured JSON payloads (buttons, lists) rather
than inline keyboard markup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.whatsapp.models import (
    MAX_BUTTON_TEXT_LENGTH,
    MAX_BUTTONS,
    MAX_LIST_ITEMS,
    MAX_MESSAGE_LENGTH,
)


@dataclass(slots=True)
class FormattedMessage:
    """A single outbound WhatsApp message chunk."""

    text: str
    interactive: dict[str, Any] | None = None  # Interactive payload (buttons/list)


@dataclass(slots=True)
class InteractiveButton:
    """A reply button for WhatsApp interactive messages."""

    id: str
    title: str


@dataclass(slots=True)
class ListRow:
    """A row in a WhatsApp interactive list."""

    id: str
    title: str
    description: str = ""


# ── Text formatting ───────────────────────────────────────


def escape_whatsapp_text(text: str) -> str:
    """Escape special formatting characters in plain text.

    WhatsApp auto-formats *bold*, _italic_, ~strike~, ```code```.
    We only escape when we want to prevent accidental formatting in
    user-generated content.
    """
    # WhatsApp formatting is context-aware (word boundaries), so we only
    # escape characters at word boundaries to prevent unintended formatting.
    # For outbound bot messages we generally *want* formatting, so this
    # is used selectively — not on every message.
    replacements = [
        ("*", r"\*"),
        ("_", r"\_"),
        ("~", r"\~"),
        ("`", r"\`"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks that fit WhatsApp's message limit.

    Prefers splitting at newlines, then at spaces, then hard-cuts.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at a newline
        split_pos = remaining.rfind("\n", 0, limit)
        if split_pos == -1:
            # Try to split at a space
            split_pos = remaining.rfind(" ", 0, limit)
        if split_pos == -1:
            # Hard cut
            split_pos = limit

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


# ── Interactive message builders ──────────────────────────


def build_reply_buttons(
    actions: list[InlineAction],
) -> list[InteractiveButton]:
    """Convert InlineActions to WhatsApp reply buttons (max 3)."""
    buttons: list[InteractiveButton] = []
    for action in actions[:MAX_BUTTONS]:
        title = action.label[:MAX_BUTTON_TEXT_LENGTH]
        buttons.append(InteractiveButton(id=action.action_id, title=title))
    return buttons


def build_interactive_payload(
    body_text: str,
    buttons: list[InteractiveButton],
) -> dict[str, Any]:
    """Build a WhatsApp interactive 'button' message payload."""
    return {
        "type": "button",
        "body": {"text": body_text[:MAX_MESSAGE_LENGTH]},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": btn.id, "title": btn.title},
                }
                for btn in buttons
            ],
        },
    }


def build_list_payload(
    body_text: str,
    button_text: str,
    rows: list[ListRow],
    header: str | None = None,
) -> dict[str, Any]:
    """Build a WhatsApp interactive 'list' message payload."""
    payload: dict[str, Any] = {
        "type": "list",
        "body": {"text": body_text[:MAX_MESSAGE_LENGTH]},
        "action": {
            "button": button_text[:MAX_BUTTON_TEXT_LENGTH],
            "sections": [
                {
                    "title": "Options",
                    "rows": [
                        {
                            "id": row.id,
                            "title": row.title[:24],
                            **({"description": row.description[:72]} if row.description else {}),
                        }
                        for row in rows[:MAX_LIST_ITEMS]
                    ],
                }
            ],
        },
    }
    if header:
        payload["header"] = {"type": "text", "text": header}
    return payload


# ── Main formatting entry point ───────────────────────────


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Format a ChannelResponse into WhatsApp message chunks.

    If the response has actions (<=3), the last chunk gets interactive
    reply buttons. Text is split to respect the 4096-char limit.
    """
    if not response.content:
        return []

    chunks = split_message(response.content)
    messages: list[FormattedMessage] = []

    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        interactive = None

        if is_last and response.actions:
            buttons = build_reply_buttons(response.actions)
            if buttons:
                interactive = build_interactive_payload(chunk, buttons)

        messages.append(FormattedMessage(text=chunk, interactive=interactive))

    return messages
