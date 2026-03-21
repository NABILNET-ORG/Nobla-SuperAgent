# backend/nobla/persona/manager.py
"""Persona manager — resolution chain, session tracking, clone."""
from __future__ import annotations

import logging
from typing import Union

from nobla.persona.models import Persona, PersonaCreate
from nobla.persona.presets import (
    PRESETS,
    PROFESSIONAL_ID,
    PresetPersona,
    get_preset,
    get_preset_by_id,
)
from nobla.persona.repository import PersonaRepository

logger = logging.getLogger(__name__)

AnyPersona = Union[PresetPersona, Persona]


class PersonaManager:
    """Loads presets, resolves per-session persona, manages cloning."""

    def __init__(self, repo: PersonaRepository) -> None:
        self._repo = repo
        self._session_personas: dict[str, str] = {}

    def set_session_persona(self, session_id: str, persona_id: str) -> None:
        self._session_personas[session_id] = persona_id

    def clear_session(self, session_id: str) -> None:
        self._session_personas.pop(session_id, None)

    async def resolve(
        self, session_id: str, user_id: str
    ) -> AnyPersona:
        """Resolution chain: session override -> user default -> Professional."""
        # 1. Session override
        override_id = self._session_personas.get(session_id)
        if override_id:
            persona = await self.get_persona(override_id)
            if persona is not None:
                return persona

        # 2. User default from DB
        try:
            default_id = await self._repo.get_default(user_id)
            if default_id:
                persona = await self.get_persona(default_id)
                if persona is not None:
                    return persona
        except Exception:
            logger.warning(
                "DB unreachable during persona resolve, falling back to preset",
                exc_info=True,
            )

        # 3. Professional fallback
        return get_preset_by_id(PROFESSIONAL_ID)  # type: ignore[return-value]

    async def get_persona(self, persona_id: str) -> AnyPersona | None:
        """Lookup by ID — checks presets first, then DB."""
        preset = get_preset_by_id(persona_id)
        if preset is not None:
            return preset
        try:
            return await self._repo.get(persona_id)
        except Exception:
            logger.warning("DB error looking up persona %s", persona_id)
            return None

    async def list_for_user(self, user_id: str) -> list[AnyPersona]:
        """Returns all presets + user's custom personas."""
        result: list[AnyPersona] = list(PRESETS.values())
        try:
            db_personas = await self._repo.list_by_user(user_id)
            result.extend(db_personas)
        except Exception:
            logger.warning("DB error listing personas for user %s", user_id)
        return result

    async def clone(self, persona_id: str, user_id: str) -> Persona:
        """Clone a preset or custom persona as an editable copy."""
        source = await self.get_persona(persona_id)
        if source is None:
            raise ValueError(f"Persona {persona_id} not found")

        base_name = f"{source.name} (Copy)"
        name = base_name
        counter = 2
        # Resolve name collisions
        existing = await self._repo.list_by_user(user_id)
        existing_names = {p.name for p in existing}
        while name in existing_names:
            name = f"{source.name} (Copy {counter})"
            counter += 1

        data = PersonaCreate(
            name=name,
            personality=source.personality,
            language_style=source.language_style,
            background=getattr(source, "background", None) or "",
            voice_config=getattr(source, "voice_config", None),
            rules=list(source.rules) if source.rules else [],
            temperature_bias=getattr(source, "temperature_bias", None),
            max_response_length=getattr(source, "max_response_length", None),
        )
        return await self._repo.create(user_id, data)
