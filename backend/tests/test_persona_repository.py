# backend/tests/test_persona_repository.py
"""Tests for persona CRUD repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.persona.repository import PersonaRepository
from nobla.persona.models import PersonaCreate


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    factory = MagicMock()
    factory.return_value = mock_session
    return factory


@pytest.fixture
def repo(mock_session_factory):
    return PersonaRepository(mock_session_factory)


class TestPersonaRepository:
    @pytest.mark.asyncio
    async def test_create_persona(self, repo, mock_session):
        data = PersonaCreate(
            name="TestBot",
            personality="Helpful",
            language_style="casual",
        )
        mock_session.refresh = AsyncMock()
        result = await repo.create("user-123", data)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_rejects_builtin_name(self, repo):
        data = PersonaCreate(
            name="Professional",
            personality="test",
            language_style="test",
        )
        with pytest.raises(ValueError, match="builtin"):
            await repo.create("user-123", data)

    @pytest.mark.asyncio
    async def test_delete_rejects_missing(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.delete("nonexistent", "user-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_default(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        await repo.set_default("user-123", "persona-456")
        mock_session.commit.assert_awaited()
