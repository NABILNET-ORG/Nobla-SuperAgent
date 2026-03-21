# backend/tests/test_persona_manager.py
"""Tests for persona manager — resolve, clone, session tracking."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.persona.manager import PersonaManager
from nobla.persona.presets import PROFESSIONAL_ID, FRIENDLY_ID


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_default.return_value = None
    repo.get.return_value = None
    return repo


@pytest.fixture
def manager(mock_repo):
    return PersonaManager(repo=mock_repo)


class TestPersonaManager:
    @pytest.mark.asyncio
    async def test_resolve_defaults_to_professional(self, manager):
        result = await manager.resolve("session-1", "user-1")
        assert result.id == PROFESSIONAL_ID
        assert result.name == "Professional"

    @pytest.mark.asyncio
    async def test_resolve_session_override(self, manager):
        manager.set_session_persona("session-1", FRIENDLY_ID)
        result = await manager.resolve("session-1", "user-1")
        assert result.id == FRIENDLY_ID

    @pytest.mark.asyncio
    async def test_resolve_user_default(self, manager, mock_repo):
        mock_repo.get_default.return_value = FRIENDLY_ID
        result = await manager.resolve("session-1", "user-1")
        assert result.id == FRIENDLY_ID

    @pytest.mark.asyncio
    async def test_session_override_beats_user_default(self, manager, mock_repo):
        mock_repo.get_default.return_value = FRIENDLY_ID
        from nobla.persona.presets import MILITARY_ID
        manager.set_session_persona("session-1", MILITARY_ID)
        result = await manager.resolve("session-1", "user-1")
        assert result.id == MILITARY_ID

    def test_clear_session(self, manager):
        manager.set_session_persona("session-1", FRIENDLY_ID)
        manager.clear_session("session-1")
        # After clearing, no session override exists
        assert manager._session_personas.get("session-1") is None

    @pytest.mark.asyncio
    async def test_resolve_custom_persona_from_db(self, manager, mock_repo):
        mock_db_persona = MagicMock()
        mock_db_persona.id = "custom-id"
        mock_db_persona.name = "Custom"
        mock_repo.get.return_value = mock_db_persona
        mock_repo.get_default.return_value = "custom-id"
        result = await manager.resolve("session-1", "user-1")
        assert result.id == "custom-id"

    @pytest.mark.asyncio
    async def test_resolve_falls_back_on_db_error(self, manager, mock_repo):
        mock_repo.get_default.side_effect = Exception("DB down")
        result = await manager.resolve("session-1", "user-1")
        assert result.id == PROFESSIONAL_ID  # fallback

    @pytest.mark.asyncio
    async def test_get_persona_checks_presets_first(self, manager):
        result = await manager.get_persona(PROFESSIONAL_ID)
        assert result is not None
        assert result.name == "Professional"

    @pytest.mark.asyncio
    async def test_list_for_user(self, manager, mock_repo):
        mock_repo.list_by_user.return_value = []
        result = await manager.list_for_user("user-1")
        # Should include 3 presets even with no DB personas
        assert len(result) == 3
