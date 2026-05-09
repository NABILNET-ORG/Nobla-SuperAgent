"""Facebook Messenger message formatting and interactive payload building (Phase 5-Channels).

Messenger sends mostly plain text — there is no native bold/italic/code
markup like WhatsApp's. Interactive UX is delivered via:

  * quick_replies — up to 13 inline chips attached to a text message
  * button template — up to 3 postback/url buttons attached to a card
  * generic template / list template — richer card UIs

We expose two interactive shapes by default: quick_replies (preferred for
most action sets) and button template (when ``response.metadata["ui"] ==
"buttons"`` is requested).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.messenger.models import (
    MAX_BUTTON_TITLE_LENGTH,
    MAX_BUTTONS,
    MAX_MESSAGE_LENGTH,
    MAX_POSTBACK_PAYLOAD_LENGTH,
    MAX_QUICK_REPLIES,
    MAX_QUICK_REPLY_TITLE_LENGTH,
)


@dataclass(slots=True)
class FormattedMessage:
    """A single outbound Messenger message chunk.

    Attributes:
        text: Plain-text body. Always present; empty string when the chunk is
            attachment-only (e.g. a button template carries its body inline).
        interactive: Optional interactive payload. Two recognized shapes:
            * ``{"type": "quick_replies", "text": <body>, "quick_replies": [...]}``
            * ``{"type": "button_template", "text": <body>, "buttons": [...]}``
    """

    text: str
    interactive: dict[str, Any] | None = None


# ── Text formatting ───────────────────────────────────────


# Control characters except common whitespace (newline, tab, carriage return).
_CONTROL_CHAR_RE = re.compile(
    r"[" + "".join(map(chr, list(range(0, 9)) + [11, 12] + list(range(14, 32)) + [127])) + r"]"
)


def escape_messenger_text(text: str) -> str:
    """Sanitize text for the Messenger Send API.

    Messenger does not interpret markdown — all characters render literally —
    but the API rejects payloads containing raw control characters. We strip
    those, normalize Unicode to NFC, and collapse runs of whitespace inside
    individual lines while preserving paragraph breaks.
    """
    if not text:
        return ""

    # Normalize to NFC so visually-identical sequences don't blow the byte cap.
    text = unicodedata.normalize("NFC", text)

    # Strip disallowed control chars (keeps \n, \t, \r).
    text = _CONTROL_CHAR_RE.sub("", text)

    # Collapse intra-line whitespace runs but keep newline structure intact.
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.splitlines()]
    return "\n".join(cleaned_lines).strip("\n")


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks that fit Messenger's body limit.

    Mirrors the WhatsApp algorithm: prefer newline boundaries, then spaces,
    then hard-cut. Empty input yields an empty list.
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

        split_pos = remaining.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = remaining.rfind(" ", 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


# ── Interactive payload builders ──────────────────────────


def _truncate_payload(value: str) -> str:
    """Clamp a postback payload to the Messenger limit."""
    return value[:MAX_POSTBACK_PAYLOAD_LENGTH]


def build_quick_replies(actions: list[InlineAction]) -> list[dict[str, Any]]:
    """Convert inline actions to Messenger quick_replies (max 13)."""
    quick_replies: list[dict[str, Any]] = []
    for action in actions[:MAX_QUICK_REPLIES]:
        title = (action.label or "")[:MAX_QUICK_REPLY_TITLE_LENGTH]
        if not title:
            # Quick replies require a non-empty title; skip degenerate actions.
            continue
        quick_replies.append({
            "content_type": "text",
            "title": title,
            "payload": _truncate_payload(action.action_id or title),
        })
    return quick_replies


def build_button_template(
    text: str,
    actions: list[InlineAction],
) -> dict[str, Any]:
    """Build a Messenger button-template payload (max 3 postback buttons)."""
    buttons: list[dict[str, Any]] = []
    for action in actions[:MAX_BUTTONS]:
        title = (action.label or "")[:MAX_BUTTON_TITLE_LENGTH]
        if not title:
            continue
        buttons.append({
            "type": "postback",
            "title": title,
            "payload": _truncate_payload(action.action_id or title),
        })

    return {
        "type": "template",
        "payload": {
            "template_type": "button",
            "text": text[:640],  # Button-template text cap is 640 chars.
            "buttons": buttons,
        },
    }


# ── Main formatting entry point ───────────────────────────


def format_response(response: ChannelResponse) -> list[FormattedMessage]:
    """Format a ``ChannelResponse`` into Messenger message chunks.

    Strategy:
      * No actions → split text into ``FormattedMessage`` chunks with
        ``interactive=None``.
      * ``response.metadata["ui"] == "buttons"`` and ``len(actions) <=
        MAX_BUTTONS`` → final chunk uses a button template.
      * Otherwise (and ``len(actions) <= MAX_QUICK_REPLIES``) → final chunk
        carries quick_replies.
      * Action lists exceeding both caps are truncated to the platform limit.
    """
    body = escape_messenger_text(response.content or "")
    chunks = split_message(body)
    if not chunks:
        # Allow attachment-only / action-only responses to still surface
        # a single empty-body message so the adapter's send loop can render
        # quick_replies or buttons attached to a placeholder.
        chunks = [""] if response.actions else []

    messages: list[FormattedMessage] = []
    actions = response.actions or []
    metadata = getattr(response, "metadata", None) or {}
    use_buttons = (
        bool(actions)
        and metadata.get("ui") == "buttons"
        and len(actions) <= MAX_BUTTONS
    )

    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        interactive: dict[str, Any] | None = None

        if is_last and actions:
            if use_buttons:
                template_text = chunk if chunk else (body[:640] if body else " ")
                interactive = {
                    "type": "button_template",
                    "text": template_text,
                    "buttons": build_button_template(template_text, actions),
                }
            else:
                quick_replies = build_quick_replies(actions)
                if quick_replies:
                    interactive = {
                        "type": "quick_replies",
                        "text": chunk,
                        "quick_replies": quick_replies,
                    }

        messages.append(FormattedMessage(text=chunk, interactive=interactive))

    return messages
