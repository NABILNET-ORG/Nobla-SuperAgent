"""LLM task interpreter — understands what the user wants scheduled (Phase 6).

Uses the LLM router to separate the time expression from the task
description and optionally map the task to existing Nobla tools.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nobla.automation.models import TaskInterpretation

if TYPE_CHECKING:
    from nobla.brain.router import LLMRouter
    from nobla.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_INTERPRETATION_PROMPT = """\
You are a task scheduler assistant. The user wants to schedule a task.
Extract two parts from their input:

1. **task_description**: What they want done (the action/task).
2. **time_expression**: When they want it done (the schedule/time).

Also check if the task maps to one of these available tools:
{tool_list}

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "task_description": "...",
  "time_expression": "...",
  "tool_name": null or "tool.name",
  "tool_params": {{}}
}}

User input: {user_input}
"""


async def interpret_task(
    user_input: str,
    router: LLMRouter,
    tool_registry: ToolRegistry | None = None,
) -> TaskInterpretation:
    """Use the LLM to interpret a user's scheduling request.

    Separates the time expression from the task description and
    optionally maps to an existing Nobla tool.

    Falls back to simple heuristic parsing if the LLM call fails.
    """
    # Build tool list for the prompt
    tool_list = "None available"
    if tool_registry:
        tools = tool_registry.list_all()
        if tools:
            tool_list = "\n".join(
                f"- {t.name}: {t.description}" for t in tools[:30]
            )

    prompt = _INTERPRETATION_PROMPT.format(
        tool_list=tool_list,
        user_input=user_input,
    )

    try:
        response = await router.route(
            prompt=prompt,
            complexity="easy",
        )
        result = _parse_llm_response(response.text, user_input)
        if result:
            return result
    except Exception:
        logger.warning("LLM interpretation failed, using fallback", exc_info=True)

    # Fallback: simple heuristic
    return _fallback_interpret(user_input)


def _parse_llm_response(
    text: str,
    raw_input: str,
) -> TaskInterpretation | None:
    """Parse the LLM's JSON response into a TaskInterpretation."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.debug("Failed to parse LLM response as JSON: %s", text[:200])
        return None

    task_desc = data.get("task_description", "").strip()
    time_expr = data.get("time_expression", "").strip()

    if not task_desc or not time_expr:
        return None

    tool_name = data.get("tool_name")
    tool_params = data.get("tool_params", {})

    return TaskInterpretation(
        task_description=task_desc,
        time_expression=time_expr,
        raw_input=raw_input,
        tool_name=tool_name if tool_name else None,
        tool_params=tool_params if isinstance(tool_params, dict) else {},
        is_tool_task=bool(tool_name),
    )


def _fallback_interpret(user_input: str) -> TaskInterpretation:
    """Simple heuristic fallback when LLM is unavailable.

    Looks for common time keywords and splits on them.
    """
    lower = user_input.lower()

    # Common time prepositions to split on
    time_markers = [
        " every ", " daily ", " weekly ", " monthly ",
        " at ", " on ", " in ", " tomorrow ", " tonight ",
        " next ",
    ]

    best_split = -1
    best_marker = ""

    for marker in time_markers:
        idx = lower.find(marker)
        if idx != -1 and (best_split == -1 or idx < best_split):
            best_split = idx
            best_marker = marker

    if best_split != -1:
        # Check if marker is at start (time first) or middle (task first)
        time_at_start = best_split < len(user_input) // 3

        if time_at_start:
            # "Every morning at 9am check the logs"
            # Try to find where time ends and task begins
            time_end = _find_time_end(lower, best_split)
            time_expr = user_input[:time_end].strip()
            task_desc = user_input[time_end:].strip()
        else:
            # "Check the logs every morning at 9am"
            task_desc = user_input[:best_split].strip()
            time_expr = user_input[best_split:].strip()

        if task_desc and time_expr:
            return TaskInterpretation(
                task_description=task_desc,
                time_expression=time_expr,
                raw_input=user_input,
            )

    # Last resort: return the whole thing as task, empty time
    return TaskInterpretation(
        task_description=user_input,
        time_expression="",
        raw_input=user_input,
    )


def _find_time_end(lower: str, start: int) -> int:
    """Find where the time expression ends in a string.

    Scans forward from start looking for a verb or non-time word.
    """
    # Common words that signal transition from time to task
    task_signals = {
        "check", "run", "send", "remind", "backup", "clean",
        "update", "deploy", "build", "test", "fetch", "sync",
        "generate", "create", "delete", "review", "monitor",
        "scan", "process", "analyze", "report", "notify",
    }

    words = lower[start:].split()
    offset = start

    for word in words:
        clean_word = word.strip(".,!?;:")
        if clean_word in task_signals:
            return offset
        offset += len(word) + 1  # +1 for space

    return len(lower)
