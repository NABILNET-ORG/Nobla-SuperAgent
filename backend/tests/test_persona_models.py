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


from nobla.persona.models import (
    PersonaCreate,
    PersonaResponse,
    PersonaContext,
    EmotionResult,
)


class TestEmotionResult:
    def test_create_valid(self):
        e = EmotionResult(
            emotion="happy", confidence=0.85, secondary="curious", source="hume"
        )
        assert e.emotion == "happy"
        assert e.confidence == 0.85
        assert e.source == "hume"

    def test_neutral_has_no_secondary(self):
        e = EmotionResult(emotion="neutral", confidence=0.3, source="local")
        assert e.secondary is None


class TestPersonaCreate:
    def test_valid_creation(self):
        p = PersonaCreate(
            name="Test Persona",
            personality="Helpful assistant",
            language_style="casual",
            rules=["Be friendly"],
        )
        assert p.name == "Test Persona"
        assert p.temperature_bias is None

    def test_name_too_long(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="x" * 101,
                personality="test",
                language_style="test",
            )

    def test_too_many_rules(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="test",
                personality="test",
                language_style="test",
                rules=["rule"] * 21,
            )

    def test_temperature_bias_out_of_range(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="test",
                personality="test",
                language_style="test",
                temperature_bias=0.8,
            )


class TestPersonaResponse:
    def test_includes_is_builtin(self):
        r = PersonaResponse(
            id="abc-123",
            name="Test",
            personality="test",
            language_style="test",
            is_builtin=True,
            rules=[],
        )
        assert r.is_builtin is True


class TestPersonaContext:
    def test_create(self):
        ctx = PersonaContext(
            persona_id="abc",
            persona_name="Pro",
            system_prompt_addition="You are Pro.",
            temperature_bias=0.1,
            voice_config={"engine": "fish_speech"},
        )
        assert ctx.system_prompt_addition == "You are Pro."


from nobla.persona.presets import PRESETS, get_preset, PROFESSIONAL_ID, FRIENDLY_ID, MILITARY_ID


class TestPresets:
    def test_three_presets_exist(self):
        assert len(PRESETS) == 3

    def test_professional_is_default(self):
        p = get_preset("professional")
        assert p is not None
        assert p.id == PROFESSIONAL_ID
        assert p.is_builtin is True

    def test_friendly_preset(self):
        p = get_preset("friendly")
        assert p is not None
        assert p.temperature_bias == 0.2

    def test_military_preset(self):
        p = get_preset("military")
        assert p is not None
        assert p.temperature_bias == -0.3

    def test_get_by_id(self):
        from nobla.persona.presets import get_preset_by_id
        p = get_preset_by_id(PROFESSIONAL_ID)
        assert p is not None
        assert p.name == "Professional"

    def test_unknown_returns_none(self):
        assert get_preset("nonexistent") is None

    def test_all_presets_are_builtin(self):
        for p in PRESETS.values():
            assert p.is_builtin is True
