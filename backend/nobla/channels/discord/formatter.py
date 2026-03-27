"""Discord message formatting and response conversion (Phase 5A).

Discord supports standard Markdown natively — no escaping required.
This module converts ``ChannelResponse`` objects into Discord-ready
messages with button views built from ``InlineAction`` lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.discord.models import MAX_MESSAGE_LENGTH


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Discord's 2000 char limit.

    Splits on paragraph boundaries first, then newlines, then sentences,
    then hard-cuts as a last resort.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try paragraph boundary
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind(". ", 0, limit)
            if cut != -1:
                cut += 1
        if cut <= 0:
            cut = limit

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    return chunks


@dataclass(slots=True)
class ButtonSpec:
    """A single button to attach to a Discord message."""

    label: str
    custom_id: str
    style: str = "primary"  # "primary", "danger", "secondary"


@dataclass(slots=True)
class FormattedMessage:
    """A single formatted Discord message ready to send."""

    content: str
    buttons: list[ButtonSpec] | None = None


def build_button_specs(
    actions: list[InlineAction] | None,
) -> list[ButtonSpec] | None:
    """Convert InlineActions to Discord ButtonSpec list.

    Discord allows up to 5 buttons per ActionRow, up to 5 rows (25 buttons).
    We limit to a single row of 5 for simplicity.
    """
    if not actions:
        return None

    specs: list[ButtonSpec] = []
    for action in actions[:25]:  # Discord max 25 buttons
        specs.append(ButtonSpec(
            label=action.label,
            custom_id=action.action_id,
            style=action.style,
        ))

    return specs


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Convert a ChannelResponse into one or more FormattedMessages.

    Discord uses standard Markdown — no escaping needed. Buttons are
    attached only to the *last* chunk.
    """
    chunks = split_message(response.content)
    buttons = build_button_specs(response.actions)

    messages: list[FormattedMessage] = []
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        messages.append(FormattedMessage(
            content=chunk,
            buttons=buttons if is_last else None,
        ))

    return messages
