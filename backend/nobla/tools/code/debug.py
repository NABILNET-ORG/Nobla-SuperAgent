"""DebugAssistantTool — error parsing and LLM-powered fix suggestions."""
from __future__ import annotations

import re

from nobla.brain.base_provider import LLMMessage
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.codegen import get_router
from nobla.tools.code.runner import get_settings
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

# --- Error patterns per language ---------------------------------------------

_ERROR_PATTERNS = {
    "python": re.compile(
        r'(?:File "(?P<file>.+?)", line (?P<line>\d+).*?\n)?'
        r"(?P<type>\w+Error): (?P<message>.+)",
        re.DOTALL,
    ),
    "javascript": re.compile(
        r"(?P<type>\w*Error): (?P<message>[^\n]+)"
        r"(?:\n\s+at .+?[:\(](?P<file>.+?):(?P<line>\d+))?",
    ),
    "bash": re.compile(
        r"(?:(?P<file>.+?): )?line (?P<line>\d+): (?P<message>.+)",
    ),
}

# --- System prompt -----------------------------------------------------------

_DEBUG_SYSTEM_PROMPT = (
    "You are a debugging assistant. Analyze the error and suggest a fix. "
    "Be concise: state the cause in 1-2 sentences, then provide the corrected "
    "code. If the original code is provided, show the fix as a minimal diff."
)


# --- Helper ------------------------------------------------------------------


def _parse_error(error: str, language: str) -> dict:
    """Best-effort error parsing. Never raises."""
    try:
        if not error:
            return {"type": None, "message": "", "file": None, "line": None}
        pattern = _ERROR_PATTERNS.get(language)
        if pattern:
            match = pattern.search(error)
            if match:
                groups = match.groupdict()
                line_val = groups.get("line")
                return {
                    "type": groups.get("type"),
                    "message": groups.get("message", error[:200]),
                    "file": groups.get("file"),
                    "line": int(line_val) if line_val else None,
                }
    except Exception:
        pass
    return {"type": None, "message": str(error)[:200], "file": None, "line": None}


# --- Tool --------------------------------------------------------------------


@register_tool
class DebugAssistantTool(BaseTool):
    name = "code.debug"
    description = "Analyze error messages and suggest fixes"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code execution is disabled")

        error = params.args.get("error", "")
        if not error or not error.strip():
            raise ValueError("Error message is required and cannot be empty")

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        error = params.args["error"]
        code = params.args.get("code", "")
        language = params.args.get("language", settings.code.default_language)

        # Truncate error before sending to LLM
        max_err = settings.code.debug_max_error_length
        error = error[:max_err]

        parsed = _parse_error(error, language)

        # Build LLM prompt
        user_parts = [f"## Error\n{error}"]
        if code:
            user_parts.append(f"## Code\n```{language}\n{code}\n```")
        user_parts.append(f"## Language\n{language}")
        user_content = "\n\n".join(user_parts)

        messages = [
            LLMMessage(role="system", content=_DEBUG_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ]

        try:
            response = await get_router().route(messages)
        except Exception as e:
            return ToolResult(
                success=False, data={}, error=f"Debug analysis failed: {e}",
            )

        return ToolResult(
            success=True,
            data={
                "parsed_error": parsed,
                "suggestion": response.content,
                "language": language,
            },
        )
