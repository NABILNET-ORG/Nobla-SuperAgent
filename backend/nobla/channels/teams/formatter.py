"""Microsoft Teams Adaptive Card message formatting (Phase 5-Channels).

Converts markdown-style text into Adaptive Card body elements:
  - ``# heading`` -> TextBlock Large/Bolder
  - ``## heading`` -> TextBlock Medium/Bolder
  - ``### heading`` -> TextBlock Default/Bolder
  - code fences -> TextBlock Monospace
  - ``---`` -> ColumnSet separator
  - ``> quote`` -> Container accent style
  - plain text -> TextBlock wrap
  - InlineActions -> Action.Submit buttons
"""

from __future__ import annotations

import re
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.teams.models import MAX_CARD_ACTIONS, MAX_TEXT_BLOCK_LENGTH


def split_message(text: str, limit: int = MAX_TEXT_BLOCK_LENGTH) -> list[str]:
    """Split long text into chunks. Prefers newlines > spaces > hard-cut."""
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


def _text_block(text: str, *, size: str | None = None, weight: str | None = None,
                font_type: str | None = None, color: str | None = None, wrap: bool = True) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "TextBlock", "text": text[:MAX_TEXT_BLOCK_LENGTH], "wrap": wrap}
    if size:
        block["size"] = size
    if weight:
        block["weight"] = weight
    if font_type:
        block["fontType"] = font_type
    if color:
        block["color"] = color
    return block


def _separator() -> dict[str, Any]:
    return {"type": "ColumnSet", "separator": True, "spacing": "Medium", "columns": []}


def _quote_container(text: str) -> dict[str, Any]:
    return {"type": "Container", "style": "accent", "items": [_text_block(text, color="Default")]}


_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_DIVIDER_RE = re.compile(r"^---+\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_QUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)
_HEADING_SIZES = {1: "Large", 2: "Medium", 3: "Default"}


def markdown_to_card_body(text: str) -> list[dict[str, Any]]:
    """Convert markdown text into Adaptive Card body elements."""
    if not text:
        return []
    body: list[dict[str, Any]] = []
    code_blocks: list[str] = []

    def _replace_code(match: re.Match) -> str:
        code = match.group(2).rstrip("\n")
        idx = len(code_blocks)
        code_blocks.append(code)
        return f"\x00CODE{idx}\x00"

    processed = _CODE_FENCE_RE.sub(_replace_code, text)
    lines = processed.split("\n")
    current_text: list[str] = []

    def _flush_text() -> None:
        joined = "\n".join(current_text).strip()
        if joined:
            body.append(_text_block(joined))
        current_text.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("\x00CODE") and stripped.endswith("\x00"):
            _flush_text()
            try:
                idx = int(stripped[5:-1])
                body.append(_text_block(code_blocks[idx], font_type="Monospace"))
            except (ValueError, IndexError):
                current_text.append(line)
            continue
        if _DIVIDER_RE.match(line):
            _flush_text()
            body.append(_separator())
            continue
        header_match = _HEADER_RE.match(line)
        if header_match:
            _flush_text()
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            size = _HEADING_SIZES.get(level, "Default")
            body.append(_text_block(header_text, size=size, weight="Bolder"))
            continue
        quote_match = _QUOTE_RE.match(line)
        if quote_match:
            _flush_text()
            body.append(_quote_container(quote_match.group(1)))
            continue
        current_text.append(line)

    _flush_text()
    return body


_STYLE_MAP = {"primary": "positive", "danger": "destructive", "secondary": "default"}


def build_card_actions(actions: list[InlineAction]) -> list[dict[str, Any]]:
    """Convert InlineActions to Adaptive Card Action.Submit list."""
    result: list[dict[str, Any]] = []
    for action in actions[:MAX_CARD_ACTIONS]:
        entry: dict[str, Any] = {
            "type": "Action.Submit",
            "title": action.label,
            "data": {"action_id": action.action_id},
        }
        style = _STYLE_MAP.get(action.style)
        if style and style != "default":
            entry["style"] = style
        result.append(entry)
    return result


def format_response(response: ChannelResponse) -> dict[str, Any]:
    """Format a ChannelResponse into a Teams Activity payload with Adaptive Card."""
    if not response.content:
        return {"type": "message", "attachments": []}
    body = markdown_to_card_body(response.content)
    actions = build_card_actions(response.actions) if response.actions else []
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }
