# backend/tests/test_persona_routes.py
"""Tests for persona REST API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from nobla.gateway.persona_routes import create_persona_router
from nobla.persona.presets import PROFESSIONAL_ID


@pytest.fixture
def mock_manager():
    mgr = AsyncMock()
    mgr.list_for_user = AsyncMock(return_value=[])
    mgr.get_persona = AsyncMock(return_value=None)
    return mgr


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def app(mock_manager, mock_repo):
    app = FastAPI()
    router = create_persona_router(mock_manager, mock_repo)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestPersonaRoutes:
    def test_list_personas(self, client, mock_manager):
        from nobla.persona.presets import PRESETS
        mock_manager.list_for_user.return_value = list(PRESETS.values())
        resp = client.get("/api/personas", headers={"X-User-Id": "user-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_create_persona(self, client, mock_repo):
        mock_persona = MagicMock()
        mock_persona.id = "new-id"
        mock_persona.name = "Custom"
        mock_persona.personality = "test"
        mock_persona.language_style = "test"
        mock_persona.background = None
        mock_persona.voice_config = None
        mock_persona.rules = []
        mock_persona.temperature_bias = None
        mock_persona.max_response_length = None
        mock_persona.created_at = "2026-03-21"
        mock_persona.updated_at = "2026-03-21"
        mock_repo.create.return_value = mock_persona
        resp = client.post(
            "/api/personas",
            json={
                "name": "Custom",
                "personality": "test",
                "language_style": "test",
            },
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 201

    def test_delete_builtin_rejected(self, client, mock_manager, mock_repo):
        from nobla.persona.presets import get_preset_by_id
        mock_manager.get_persona.return_value = get_preset_by_id(PROFESSIONAL_ID)
        resp = client.delete(
            f"/api/personas/{PROFESSIONAL_ID}",
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 403

    def test_get_preference(self, client, mock_repo):
        mock_repo.get_default.return_value = None
        resp = client.get(
            "/api/user/persona-preference",
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 200

    def test_set_preference(self, client, mock_repo):
        resp = client.put(
            "/api/user/persona-preference",
            json={"default_persona_id": PROFESSIONAL_ID},
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 200
        mock_repo.set_default.assert_awaited_once()
