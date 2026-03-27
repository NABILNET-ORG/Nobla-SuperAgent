"""Telegram MarkdownV2 formatting and response conversion (Phase 5A).

Telegram's MarkdownV2 requires escaping a specific set of characters.
This module converts ``ChannelResponse`` objects into Telegram-safe
messages with inline keyboards built from ``InlineAction`` lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.telegram.models import MAX_MESSAGE_LENGTH


# Characters that must be escaped in MarkdownV2 outside of code blocks.
_ESCAPE_CHARS = r"_*[]()~`>#+\-=|{}.!"
_ESCAPE_RE = re.compile(r"([" + re.escape(_ESCAPE_CHARS) + r"])")

# Pattern to detect existing markdown code blocks (``` ... ```)
_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```|`[^`]+`)")


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Preserves content inside inline code and code blocks — only the
    text *outside* fenced regions is escaped.
    """
    parts = _CODE_BLOCK_RE.split(text)
    result: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside code block — leave as-is
            result.append(part)
        else:
            result.append(_ESCAPE_RE.sub(r"\\\1", part))
    return "".join(result)


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit.

    Splits on paragraph boundaries first, then sentence boundaries,
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
            # Try newline
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            # Try sentence boundary
            cut = remaining.rfind(". ", 0, limit)
            if cut != -1:
                cut += 1  # include the period
        if cut <= 0:
            # Hard cut
            cut = limit

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    return chunks


@dataclass(slots=True)
class FormattedMessage:
    """A single formatted Telegram message ready to send."""

    text: str
    parse_mode: str = "MarkdownV2"
    reply_markup: list[list[dict]] | None = None


def build_inline_keyboard(
    actions: list[InlineAction] | None,
) -> list[list[dict]] | None:
    """Convert InlineActions to Telegram InlineKeyboardMarkup rows.

    Returns the ``inline_keyboard`` list-of-rows structure expected by
    the Telegram Bot API. Groups up to 3 buttons per row.
    """
    if not actions:
        return None

    rows: list[list[dict]] = []
    current_row: list[dict] = []

    for action in actions:
        current_row.append({
            "text": action.label,
            "callback_data": action.action_id,
        })
        if len(current_row) >= 3:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    return rows


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Convert a ChannelResponse into one or more FormattedMessages.

    Escapes content for MarkdownV2, splits long messages, and attaches
    the inline keyboard only to the *last* chunk so the user sees
    buttons after the full response.
    """
    escaped = escape_markdown_v2(response.content)
    chunks = split_message(escaped)
    keyboard = build_inline_keyboard(response.actions)

    messages: list[FormattedMessage] = []
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        messages.append(FormattedMessage(
            text=chunk,
            reply_markup=keyboard if is_last else None,
        ))

    return messages
