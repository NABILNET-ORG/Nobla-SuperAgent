"""Tests for learning REST API handlers."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nobla.gateway.learning_handlers import learning_router


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.submit_feedback = AsyncMock(return_value=None)
    svc.get_feedback_for_conversation = AsyncMock(return_value=[])
    svc.get_feedback_stats = AsyncMock(return_value={"total": 0, "positive": 0, "negative": 0})
    svc.get_patterns = AsyncMock(return_value=[])
    svc.dismiss_pattern = AsyncMock()
    svc.get_macros = AsyncMock(return_value=[])
    svc.promote_to_skill = AsyncMock(return_value=MagicMock(id="skill-1"))
    svc.mark_publishable = AsyncMock(return_value=MagicMock(tier=MagicMock(value="publishable")))
    svc.delete_macro = AsyncMock()
    svc.create_experiment = AsyncMock(return_value=MagicMock(id="exp-1", status=MagicMock(value="running")))
    svc.get_experiments = AsyncMock(return_value=[])
    svc.pause_experiment = AsyncMock()
    svc.get_suggestions = AsyncMock(return_value=[])
    svc.accept_suggestion = AsyncMock(return_value={"wf": "1"})
    svc.dismiss_suggestion = AsyncMock()
    svc.snooze_suggestion = AsyncMock()
    svc.get_settings = MagicMock(return_value={"enabled": True, "proactive_level": "conservative"})
    svc.update_settings = AsyncMock()
    svc.clear_data = AsyncMock()
    return svc

@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.state.learning_service = mock_service
    app.include_router(learning_router)
    return TestClient(app)


class TestFeedbackEndpoints:
    def test_submit_feedback(self, client, mock_service):
        resp = client.post("/api/learning/feedback", json={
            "conversation_id": "c1", "message_id": "m1", "quick_rating": 1,
            "context": {"llm_model": "gemini"},
        })
        assert resp.status_code == 200
        mock_service.submit_feedback.assert_called_once()

    def test_get_feedback_stats(self, client):
        resp = client.get("/api/learning/feedback/stats")
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_get_feedback_by_conversation(self, client):
        resp = client.get("/api/learning/feedback?conversation_id=c1")
        assert resp.status_code == 200

class TestPatternEndpoints:
    def test_list_patterns(self, client):
        resp = client.get("/api/learning/patterns")
        assert resp.status_code == 200

    def test_dismiss_pattern(self, client, mock_service):
        resp = client.post("/api/learning/patterns/pat-1/dismiss")
        assert resp.status_code == 200
        mock_service.dismiss_pattern.assert_called_once_with("pat-1")

class TestMacroEndpoints:
    def test_list_macros(self, client):
        resp = client.get("/api/learning/macros")
        assert resp.status_code == 200

    def test_promote_macro(self, client, mock_service):
        resp = client.post("/api/learning/macros/m1/promote")
        assert resp.status_code == 200

    def test_delete_macro(self, client, mock_service):
        resp = client.delete("/api/learning/macros/m1")
        assert resp.status_code == 200

class TestSuggestionEndpoints:
    def test_accept_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/accept")
        assert resp.status_code == 200

    def test_dismiss_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/dismiss", json={"reason": "irrelevant"})
        assert resp.status_code == 200

    def test_snooze_suggestion(self, client, mock_service):
        resp = client.post("/api/learning/suggestions/s1/snooze", json={"days": 3})
        assert resp.status_code == 200
        mock_service.snooze_suggestion.assert_called_once_with("s1", 3)

class TestSettingsEndpoints:
    def test_get_settings(self, client):
        resp = client.get("/api/learning/settings")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_update_settings(self, client, mock_service):
        resp = client.put("/api/learning/settings", json={"proactive_level": "moderate"})
        assert resp.status_code == 200

    def test_clear_data(self, client, mock_service):
        resp = client.delete("/api/learning/data")
        assert resp.status_code == 200
        mock_service.clear_data.assert_called_once()
