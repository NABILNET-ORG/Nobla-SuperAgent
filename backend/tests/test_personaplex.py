"""Tests for PersonaPlex TTS integration."""
import pytest
from nobla.config.settings import PersonaPlexSettings, Settings


class TestPersonaPlexSettings:
    def test_defaults(self):
        s = PersonaPlexSettings()
        assert s.enabled is False
        assert s.server_url == "http://localhost:8880"
        assert s.timeout == 30.0
        assert s.cpu_offload is False

    def test_settings_has_personaplex(self):
        settings = Settings()
        assert hasattr(settings, "personaplex")
        assert isinstance(settings.personaplex, PersonaPlexSettings)
        assert settings.personaplex.enabled is False
