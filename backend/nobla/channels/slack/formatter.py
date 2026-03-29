"""Slack Block Kit message formatting (Phase 5-Channels).

Converts markdown-style text into Slack Block Kit blocks:
  - ``# heading`` -> header block
  - ``---`` -> divider block
  - code fences -> section with mrkdwn code formatting
  - plain text -> section with mrkdwn
  - InlineActions -> actions block with buttons

Slack mrkdwn is similar to standard markdown but uses ``*bold*``,
``_italic_``, ``~strike~``, and ``>`` for quotes.
"""

from __future__ import annotations

import re
from typing import Any

from nobla.channels.base import ChannelResponse, InlineAction
from nobla.channels.slack.models import (
    MAX_ACTIONS,
    MAX_BLOCKS,
    MAX_BUTTON_TEXT_LENGTH,
    MAX_MESSAGE_LENGTH,
)


# -- Text splitting --------------------------------------------------


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks that fit Slack's message limit.

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

        split_pos = remaining.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = remaining.rfind(" ", 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


# -- Block Kit builders ----------------------------------------------


def _header_block(text: str) -> dict[str, Any]:
    """Build a Block Kit header block (max 150 chars)."""
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": text[:150], "emoji": True},
    }


def _section_block(mrkdwn: str) -> dict[str, Any]:
    """Build a Block Kit section block with mrkdwn text (max 3000 chars)."""
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": mrkdwn[:3000]},
    }


def _divider_block() -> dict[str, Any]:
    """Build a Block Kit divider block."""
    return {"type": "divider"}


# -- Markdown to blocks conversion -----------------------------------

# Regex patterns
_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_DIVIDER_RE = re.compile(r"^---+\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def markdown_to_blocks(text: str) -> list[dict[str, Any]]:
    """Convert markdown text into Slack Block Kit blocks.

    Handles: headers (# ## ###), dividers (---), code fences (```),
    and regular text as mrkdwn sections.
    """
    if not text:
        return []

    blocks: list[dict[str, Any]] = []

    # First, extract code fences and replace with placeholders
    code_blocks: list[str] = []

    def _replace_code(match: re.Match) -> str:
        lang = match.group(1)
        code = match.group(2).rstrip("\n")
        formatted = f"```{code}```" if not lang else f"```\n{code}\n```"
        idx = len(code_blocks)
        code_blocks.append(formatted)
        return f"\x00CODE{idx}\x00"

    processed = _CODE_FENCE_RE.sub(_replace_code, text)

    # Split into lines and process
    lines = processed.split("\n")
    current_text: list[str] = []

    def _flush_text() -> None:
        joined = "\n".join(current_text).strip()
        if joined:
            blocks.append(_section_block(joined))
        current_text.clear()

    for line in lines:
        stripped = line.strip()

        # Check for code placeholder
        if stripped.startswith("\x00CODE") and stripped.endswith("\x00"):
            _flush_text()
            try:
                idx = int(stripped[5:-1])
                blocks.append(_section_block(code_blocks[idx]))
            except (ValueError, IndexError):
                current_text.append(line)
            continue

        # Check for divider
        if _DIVIDER_RE.match(line):
            _flush_text()
            blocks.append(_divider_block())
            continue

        # Check for header
        header_match = _HEADER_RE.match(line)
        if header_match:
            _flush_text()
            header_text = header_match.group(2).strip()
            blocks.append(_header_block(header_text))
            continue

        # Regular text line
        current_text.append(line)

    _flush_text()

    # Cap at MAX_BLOCKS
    return blocks[:MAX_BLOCKS]


# -- Actions block ---------------------------------------------------


def build_actions_block(actions: list[InlineAction]) -> dict[str, Any]:
    """Convert InlineActions to a Slack Block Kit actions block with buttons."""
    elements: list[dict[str, Any]] = []

    for action in actions[:MAX_ACTIONS]:
        label = action.label[:MAX_BUTTON_TEXT_LENGTH]
        btn: dict[str, Any] = {
            "type": "button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "action_id": action.action_id,
        }
        # Slack only supports "primary" and "danger" styles
        if action.style in ("primary", "danger"):
            btn["style"] = action.style

        elements.append(btn)

    return {"type": "actions", "elements": elements}


# -- Main formatting entry point -------------------------------------


def format_response(response: ChannelResponse) -> dict[str, Any]:
    """Format a ChannelResponse into a Slack message payload.

    Returns a dict with ``text`` (fallback) and ``blocks`` (Block Kit).
    If the response has actions, an actions block is appended.
    """
    if not response.content:
        return {"text": "", "blocks": []}

    # Build blocks from markdown content
    blocks = markdown_to_blocks(response.content)

    # Add actions block if present
    if response.actions:
        actions_block = build_actions_block(response.actions)
        if actions_block["elements"]:
            blocks.append(actions_block)

    # Fallback text (plain, truncated)
    fallback = response.content[:MAX_MESSAGE_LENGTH]

    return {"text": fallback, "blocks": blocks[:MAX_BLOCKS]}
