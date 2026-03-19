"""Working memory — active conversation context window management.

Manages what goes into the LLM's context window for each request.
Handles token budgeting, observation masking, and rolling summaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ~= 4 characters
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate. Actual counting done at router level."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class ContextMessage:
    role: str
    content: str
    tool_output: Optional[str] = None  # Masked from context
    token_estimate: int = 0

    def __post_init__(self):
        self.token_estimate = estimate_tokens(self.content)


class WorkingMemory:
    """Manages the active context window for a conversation."""

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.messages: list[ContextMessage] = []
        self._rolling_summary: Optional[str] = None

    def add_message(
        self,
        role: str,
        content: str,
        tool_output: Optional[str] = None,
    ) -> None:
        """Add a message to working memory."""
        self.messages.append(ContextMessage(
            role=role,
            content=content,
            tool_output=tool_output,
        ))

    def set_rolling_summary(self, summary: str) -> None:
        """Set the rolling summary for older messages (from warm path)."""
        self._rolling_summary = summary

    def clear(self) -> None:
        """Clear all messages and summary."""
        self.messages.clear()
        self._rolling_summary = None

    def get_context(
        self,
        system_prompt: str,
        memory_block: str,
        current_message: Optional[str] = None,
    ) -> str:
        """Assemble the context window within the token budget.

        Priority order (if budget tight):
        1. System prompt (never truncated)
        2. Current user message (never truncated)
        3. Memory block (truncated to 500 tokens max)
        4. Last 3 messages verbatim (minimum coherence)
        5. Remaining history fills whatever budget is left
        """
        budget = self.max_tokens
        parts: list[str] = []

        # 1. System prompt (always included)
        if system_prompt:
            parts.append(f"[System] {system_prompt}")
            budget -= estimate_tokens(system_prompt)

        # 2. Memory block (cap at 500 tokens)
        if memory_block:
            mem_tokens = estimate_tokens(memory_block)
            if mem_tokens > 500:
                # Truncate memory block
                memory_block = memory_block[:500 * CHARS_PER_TOKEN]
            parts.append(f"[Memory] {memory_block}")
            budget -= min(mem_tokens, 500)

        # 3. Rolling summary of older messages
        if self._rolling_summary:
            parts.append(f"[Summary] {self._rolling_summary}")
            budget -= estimate_tokens(self._rolling_summary)

        # 4. Conversation messages (newest first until budget exhausted)
        message_parts: list[str] = []
        for msg in reversed(self.messages):
            # Observation masking: skip tool_output, keep content only
            msg_text = f"{msg.role}: {msg.content}"
            msg_tokens = estimate_tokens(msg_text)
            if budget - msg_tokens < 0 and len(message_parts) >= 3:
                break  # Keep at least 3 recent messages
            message_parts.append(msg_text)
            budget -= msg_tokens

        # Reverse back to chronological order
        message_parts.reverse()
        parts.extend(message_parts)

        # 5. Current message
        if current_message:
            parts.append(f"user: {current_message}")

        return "\n".join(parts)
