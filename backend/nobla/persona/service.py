# backend/nobla/persona/service.py
"""Shared service function for persona-aware LLM routing."""
from __future__ import annotations

from nobla.persona.models import EmotionResult, PersonaContext
from nobla.persona.manager import PersonaManager
from nobla.persona.prompt import PromptBuilder
from nobla.brain.base_provider import LLMMessage, LLMResponse

# Module-level accessors (set during app lifespan).
_persona_manager: PersonaManager | None = None
_prompt_builder: PromptBuilder | None = None


def set_persona_manager(mgr: PersonaManager) -> None:
    global _persona_manager
    _persona_manager = mgr


def get_persona_manager() -> PersonaManager | None:
    return _persona_manager


def set_prompt_builder(builder: PromptBuilder) -> None:
    global _prompt_builder
    _prompt_builder = builder


def get_prompt_builder() -> PromptBuilder | None:
    return _prompt_builder


async def resolve_and_route(
    messages: list[LLMMessage],
    session_id: str,
    user_id: str,
    emotion: EmotionResult | None = None,
    router=None,
) -> tuple[LLMResponse, PersonaContext]:
    """Resolve persona, build prompt, route through LLM.

    Returns both the LLM response and the PersonaContext (needed by
    voice handler for TTS voice_config selection).
    """
    from nobla.gateway.websocket import get_router

    brain_router = router or get_router()
    manager = _persona_manager
    builder = _prompt_builder

    persona = await manager.resolve(session_id, user_id)
    ctx = builder.build(persona, emotion)

    response = await brain_router.route(
        messages,
        system_prompt_extra=ctx.system_prompt_addition,
        temperature_bias=ctx.temperature_bias,
    )
    return response, ctx
