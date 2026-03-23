# backend/nobla/gateway/persona_routes.py
"""REST API routes for persona CRUD and user preference."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from nobla.persona.manager import PersonaManager
from nobla.persona.models import (
    PersonaCreate,
    PersonaResponse,
    PersonaUpdate,
    PreferenceResponse,
    PreferenceUpdate,
)
from nobla.persona.presets import PresetPersona
from nobla.persona.repository import PersonaRepository


def _to_response(persona) -> PersonaResponse:
    """Convert ORM row or preset to API response."""
    is_builtin = isinstance(persona, PresetPersona)
    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        personality=persona.personality,
        language_style=persona.language_style,
        background=getattr(persona, "background", None),
        voice_config=getattr(persona, "voice_config", None),
        rules=list(persona.rules) if persona.rules else [],
        temperature_bias=getattr(persona, "temperature_bias", None),
        max_response_length=getattr(persona, "max_response_length", None),
        is_builtin=is_builtin,
        created_at=getattr(persona, "created_at", None),
        updated_at=getattr(persona, "updated_at", None),
    )


def create_persona_router(
    manager: PersonaManager, repo: PersonaRepository
) -> APIRouter:
    """Factory: creates the persona APIRouter with injected deps.

    NOTE: Auth uses X-User-Id header as a temporary placeholder.
    TODO: Replace with proper JWT dependency injection via
    Depends(get_current_user) that extracts user_id from the
    Authorization header (Phase 1 auth system).
    """
    router = APIRouter(prefix="/api", tags=["personas"])

    @router.get("/personas", response_model=list[PersonaResponse])
    async def list_personas(x_user_id: str = Header()):
        personas = await manager.list_for_user(x_user_id)
        return [_to_response(p) for p in personas]

    @router.post("/personas", response_model=PersonaResponse, status_code=201)
    async def create_persona(
        data: PersonaCreate, x_user_id: str = Header()
    ):
        try:
            persona = await repo.create(x_user_id, data)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return _to_response(persona)

    @router.get("/personas/{persona_id}", response_model=PersonaResponse)
    async def get_persona(persona_id: str, x_user_id: str = Header()):
        persona = await manager.get_persona(persona_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        return _to_response(persona)

    @router.put("/personas/{persona_id}", response_model=PersonaResponse)
    async def update_persona(
        persona_id: str, data: PersonaUpdate, x_user_id: str = Header()
    ):
        existing = await manager.get_persona(persona_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        if isinstance(existing, PresetPersona):
            raise HTTPException(
                status_code=403, detail="Cannot modify builtin persona"
            )
        try:
            result = await repo.update(persona_id, x_user_id, data)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        return _to_response(result)

    @router.delete("/personas/{persona_id}", status_code=204)
    async def delete_persona(
        persona_id: str, x_user_id: str = Header()
    ):
        existing = await manager.get_persona(persona_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        if isinstance(existing, PresetPersona):
            raise HTTPException(
                status_code=403, detail="Cannot delete builtin persona"
            )
        deleted = await repo.delete(persona_id, x_user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Persona not found")

    @router.post(
        "/personas/{persona_id}/clone",
        response_model=PersonaResponse,
        status_code=201,
    )
    async def clone_persona(
        persona_id: str, x_user_id: str = Header()
    ):
        try:
            cloned = await manager.clone(persona_id, x_user_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _to_response(cloned)

    @router.get(
        "/user/persona-preference", response_model=PreferenceResponse
    )
    async def get_preference(x_user_id: str = Header()):
        default_id = await repo.get_default(x_user_id)
        return PreferenceResponse(default_persona_id=default_id)

    @router.put(
        "/user/persona-preference", response_model=PreferenceResponse
    )
    async def set_preference(
        data: PreferenceUpdate, x_user_id: str = Header()
    ):
        await repo.set_default(x_user_id, data.default_persona_id)
        return PreferenceResponse(
            default_persona_id=data.default_persona_id
        )

    return router
