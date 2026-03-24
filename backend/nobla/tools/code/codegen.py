"""CodeGenerationTool — LLM-powered code generation with optional execution."""
from __future__ import annotations

import re

from nobla.brain.base_provider import LLMMessage
from nobla.brain.router import LLMRouter
from nobla.config.settings import Settings
from nobla.security.permissions import Tier
from nobla.tools.base import BaseTool
from nobla.tools.code.runner import get_settings, run_code
from nobla.tools.models import ToolCategory, ToolParams, ToolResult
from nobla.tools.registry import register_tool

# --- Lazy singleton for LLM router ------------------------------------------

_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter(get_settings())
    return _router


def set_router(router: LLMRouter) -> None:
    """Inject a router for testing."""
    global _router
    _router = router


# --- System prompt -----------------------------------------------------------

_CODEGEN_SYSTEM_PROMPT = (
    "You are a code generation assistant. Generate clean, correct code that "
    "solves the user's request. Output ONLY code — no explanations, no markdown "
    "unless wrapping in a code fence. The code must be self-contained and runnable."
)


# --- Helper ------------------------------------------------------------------


def _extract_code(response: str) -> str:
    """Strip markdown code fences from LLM response."""
    match = re.search(r"```(?:\w*)\n(.*?)```", response, re.DOTALL)
    return match.group(1).strip() if match else response.strip()


# --- Tool --------------------------------------------------------------------


@register_tool
class CodeGenerationTool(BaseTool):
    name = "code.generate"
    description = "Generate code from a natural language description"
    category = ToolCategory.CODE
    tier = Tier.STANDARD
    requires_approval = False

    async def validate(self, params: ToolParams) -> None:
        settings = get_settings()
        if not settings.code.enabled:
            raise ValueError("Code execution is disabled")

        description = params.args.get("description", "")
        if not description or not description.strip():
            raise ValueError("Description is required and cannot be empty")

        language = params.args.get("language", settings.code.default_language)
        if language not in settings.code.supported_languages:
            raise ValueError(
                f"Unsupported language '{language}'. "
                f"Supported: {settings.code.supported_languages}"
            )

    async def execute(self, params: ToolParams) -> ToolResult:
        settings = get_settings()
        description = params.args["description"]
        language = params.args.get("language", settings.code.default_language)
        run = params.args.get("run", False)

        messages = [
            LLMMessage(role="system", content=_CODEGEN_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"Language: {language}\n\nTask: {description}",
            ),
        ]

        try:
            response = await get_router().route(
                messages, max_tokens=settings.code.codegen_max_tokens,
            )
        except Exception as e:
            return ToolResult(success=False, data={}, error=f"LLM error: {e}")

        code = _extract_code(response.content)
        execution = None

        if run:
            result = await run_code(
                code, language, params.connection_state.connection_id,
            )
            execution = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "execution_time_ms": result.execution_time_ms,
                "timed_out": result.timed_out,
            }

        return ToolResult(
            success=True,
            data={
                "code": code,
                "language": language,
                "execution": execution,
            },
        )
