"""Signal adapter formatter -- plain text only (Phase 5-Channels).

Signal does not support rich text formatting (no markdown, no buttons).
Actions are rendered as numbered text options. Long messages are split
at newlines, then spaces, then hard-cut.
"""

from __future__ import annotations

from dataclasses import dataclass

from nobla.channels.base import ChannelResponse
from nobla.channels.signal.models import MAX_MESSAGE_LENGTH


@dataclass(frozen=True)
class FormattedMessage:
    """A single outbound Signal message (plain text only)."""

    text: str


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks respecting the character limit.

    Split preference: newlines > spaces > hard-cut.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at last newline before limit
        cut = remaining[:limit].rfind("\n")
        if cut <= 0:
            cut = remaining[:limit].rfind(" ")
        if cut <= 0:
            cut = limit

        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")

    return chunks


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Format a ChannelResponse into Signal plain-text messages.

    Since Signal has no interactive buttons, actions are rendered as
    numbered text options appended to the message body.
    """
    if not response.content and not response.actions:
        return []

    text = response.content or ""

    # Render actions as numbered text options (Signal has no buttons)
    if response.actions:
        action_lines = "\n".join(
            f"  [{i + 1}] {a.label}" for i, a in enumerate(response.actions)
        )
        text = f"{text}\n\n{action_lines}" if text else action_lines

    chunks = split_message(text)
    return [FormattedMessage(text=c) for c in chunks]
