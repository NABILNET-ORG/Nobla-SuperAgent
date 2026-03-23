# backend/tests/test_prompt_builder.py
"""Tests for persona prompt builder."""
import pytest
from nobla.persona.prompt import PromptBuilder
from nobla.persona.presets import get_preset
from nobla.persona.models import EmotionResult, PersonaContext


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()

    def test_build_basic_persona(self):
        preset = get_preset("professional")
        ctx = self.builder.build(preset, emotion=None)
        assert isinstance(ctx, PersonaContext)
        assert "Professional" in ctx.system_prompt_addition
        assert "formal, concise" in ctx.system_prompt_addition
        assert ctx.persona_id == preset.id
        assert ctx.temperature_bias == 0.0

    def test_build_includes_rules(self):
        preset = get_preset("military")
        ctx = self.builder.build(preset, emotion=None)
        assert "Lead with the bottom line" in ctx.system_prompt_addition

    def test_build_with_emotion(self):
        preset = get_preset("friendly")
        emotion = EmotionResult(
            emotion="frustrated", confidence=0.82, source="hume"
        )
        ctx = self.builder.build(preset, emotion=emotion)
        assert "frustrated" in ctx.system_prompt_addition
        assert "0.82" in ctx.system_prompt_addition

    def test_build_skips_low_confidence_emotion(self):
        preset = get_preset("professional")
        emotion = EmotionResult(
            emotion="happy", confidence=0.3, source="local"
        )
        ctx = self.builder.build(preset, emotion=emotion)
        assert "happy" not in ctx.system_prompt_addition

    def test_build_includes_max_response_length(self):
        preset = get_preset("professional")
        # Use a mock-like object with max_response_length set
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="Custom",
            personality="test",
            language_style="test",
            background="test",
            max_response_length=500,
        )
        ctx = self.builder.build(custom, emotion=None)
        assert "500" in ctx.system_prompt_addition

    def test_build_skips_none_background(self):
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="NoBg",
            personality="test",
            language_style="test",
            background="",
        )
        ctx = self.builder.build(custom, emotion=None)
        assert "Background:" not in ctx.system_prompt_addition

    def test_voice_config_passed_through(self):
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="VoiceTest",
            personality="test",
            language_style="test",
            background="test",
            voice_config={"engine": "fish_speech", "voice": "alloy"},
        )
        ctx = self.builder.build(custom, emotion=None)
        assert ctx.voice_config == {"engine": "fish_speech", "voice": "alloy"}
