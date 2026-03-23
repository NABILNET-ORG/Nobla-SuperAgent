# backend/nobla/persona/prompt.py
"""Build LLM system prompt additions from persona + emotion context."""
from __future__ import annotations

from nobla.persona.models import EmotionResult, PersonaContext

# Confidence threshold below which emotion is treated as neutral.
_EMOTION_CONFIDENCE_THRESHOLD = 0.5


class PromptBuilder:
    """Assembles persona + emotion into a system prompt string."""

    def build(
        self,
        persona,  # PresetPersona or Persona ORM row (duck-typed)
        emotion: EmotionResult | None = None,
    ) -> PersonaContext:
        parts: list[str] = []

        parts.append(f"You are {persona.name}. {persona.personality}")
        parts.append(f"\nCommunication style: {persona.language_style}")

        if persona.background:
            parts.append(f"Background: {persona.background}")

        if persona.rules:
            parts.append("\nRules:")
            for rule in persona.rules:
                parts.append(f"- {rule}")

        if (
            emotion is not None
            and emotion.confidence >= _EMOTION_CONFIDENCE_THRESHOLD
        ):
            parts.append(
                f"\nUser's current mood: {emotion.emotion} "
                f"(confidence: {emotion.confidence})"
            )
            parts.append("Adapt your response accordingly.")

        if getattr(persona, "max_response_length", None):
            parts.append(
                f"\nKeep responses under {persona.max_response_length} tokens."
            )

        return PersonaContext(
            persona_id=persona.id,
            persona_name=persona.name,
            system_prompt_addition="\n".join(parts),
            temperature_bias=getattr(persona, "temperature_bias", None),
            voice_config=getattr(persona, "voice_config", None),
        )
