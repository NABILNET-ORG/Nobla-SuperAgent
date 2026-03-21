"""Tests for persona models, schemas, and configuration."""
import pytest
from nobla.config.settings import PersonaSettings, Settings


class TestPersonaSettings:
    def test_default_values(self):
        s = PersonaSettings()
        assert s.hume_api_key is None
        assert s.emotion_enabled is True
        assert s.emotion_cache_ttl == 30
        assert s.emotion_confidence_threshold == 0.5
        assert s.default_persona == "professional"

    def test_settings_has_persona_field(self):
        settings = Settings()
        assert hasattr(settings, "persona")
        assert isinstance(settings.persona, PersonaSettings)
