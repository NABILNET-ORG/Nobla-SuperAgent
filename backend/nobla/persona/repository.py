# backend/nobla/persona/repository.py
"""Async CRUD repository for personas and user preferences."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from nobla.persona.models import (
    Persona,
    PersonaCreate,
    PersonaUpdate,
    UserPersonaPreference,
)
from nobla.persona.presets import BUILTIN_NAMES

logger = logging.getLogger(__name__)


class PersonaRepository:
    """Async CRUD operations for personas.

    Uses session_factory (not a single session) for concurrency safety.
    Each method creates its own session via async context manager.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, user_id: str, data: PersonaCreate) -> Persona:
        if data.name.lower() in BUILTIN_NAMES:
            raise ValueError(
                f"Name '{data.name}' conflicts with a builtin persona"
            )
        async with self._session_factory() as session:
            persona = Persona(
                user_id=user_id,
                name=data.name,
                personality=data.personality,
                language_style=data.language_style,
                background=data.background,
                voice_config=data.voice_config,
                rules=data.rules,
                temperature_bias=data.temperature_bias,
                max_response_length=data.max_response_length,
            )
            session.add(persona)
            await session.commit()
            await session.refresh(persona)
            return persona

    async def get(self, persona_id: str) -> Persona | None:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Persona]:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.user_id == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(
        self, persona_id: str, user_id: str, data: PersonaUpdate
    ) -> Persona | None:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()
            if persona is None or persona.user_id != user_id:
                return None
            updates = data.model_dump(exclude_unset=True)
            if "name" in updates and updates["name"].lower() in BUILTIN_NAMES:
                raise ValueError(
                    f"Name '{updates['name']}' conflicts with a builtin persona"
                )
            for key, value in updates.items():
                setattr(persona, key, value)
            persona.updated_at = datetime.now(timezone.utc).isoformat()
            await session.commit()
            await session.refresh(persona)
            return persona

    async def delete(self, persona_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()
            if persona is None or persona.user_id != user_id:
                return False
            await session.execute(
                sa_delete(Persona).where(Persona.id == persona_id)
            )
            await session.commit()
            return True

    async def set_default(
        self, user_id: str, persona_id: str | None
    ) -> None:
        async with self._session_factory() as session:
            stmt = select(UserPersonaPreference).where(
                UserPersonaPreference.user_id == user_id
            )
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            if pref is None:
                pref = UserPersonaPreference(
                    user_id=user_id, default_persona_id=persona_id
                )
                session.add(pref)
            else:
                pref.default_persona_id = persona_id
            await session.commit()

    async def get_default(self, user_id: str) -> str | None:
        async with self._session_factory() as session:
            stmt = select(UserPersonaPreference.default_persona_id).where(
                UserPersonaPreference.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
