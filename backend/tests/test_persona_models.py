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


from unittest.mock import AsyncMock


class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_route_with_system_prompt_extra(self):
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage, LLMResponse

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.0
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.generate.return_value = LLMResponse(
            content="hello", model="test", tokens_input=10,
            tokens_output=5, cost_usd=0.0, latency_ms=100,
        )

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        result = await router.route(
            messages,
            system_prompt_extra="You are Professional.",
            temperature_bias=-0.3,
        )

        # Verify system_prompt_extra was prepended
        call_args = mock_provider.generate.call_args
        sent_messages = call_args[0][0]
        assert sent_messages[0].role == "system"
        assert "Professional" in sent_messages[0].content
        # Verify temperature_bias was applied
        sent_kwargs = call_args[1]
        assert sent_kwargs["temperature"] == pytest.approx(0.7)  # 1.0 + (-0.3)

    @pytest.mark.asyncio
    async def test_route_without_persona_kwargs(self):
        """Verify backward compatibility — no persona kwargs works as before."""
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage, LLMResponse

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.0
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.generate.return_value = LLMResponse(
            content="hello", model="test", tokens_input=10,
            tokens_output=5, cost_usd=0.0, latency_ms=100,
        )

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        result = await router.route(messages)

        # No system message prepended
        call_args = mock_provider.generate.call_args
        sent_messages = call_args[0][0]
        assert sent_messages[0].role == "user"
        # No temperature kwarg
        assert "temperature" not in call_args[1]

    @pytest.mark.asyncio
    async def test_stream_route_with_persona_kwargs(self):
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage

        async def fake_stream(msgs, **kw):
            yield "chunk"

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.0
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.stream = lambda msgs, **kw: fake_stream(msgs, **kw)
        # Store call args manually since stream is not AsyncMock
        captured = {}

        original_stream = mock_provider.stream

        def capturing_stream(msgs, **kw):
            captured["messages"] = msgs
            captured["kwargs"] = kw
            return original_stream(msgs, **kw)

        mock_provider.stream = capturing_stream

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        name, stream_iter = await router.stream_route(
            messages,
            system_prompt_extra="You are Friendly.",
            temperature_bias=0.2,
        )

        assert name == "test"
        assert captured["messages"][0].role == "system"
        assert "Friendly" in captured["messages"][0].content
        assert captured["kwargs"]["temperature"] == pytest.approx(1.2)

    @pytest.mark.asyncio
    async def test_temperature_bias_clamped(self):
        """Verify temperature is clamped to [0.0, 2.0]."""
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage, LLMResponse

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.8
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.generate.return_value = LLMResponse(
            content="hello", model="test", tokens_input=10,
            tokens_output=5, cost_usd=0.0, latency_ms=100,
        )

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        # 1.8 + 0.5 = 2.3, should be clamped to 2.0
        await router.route(messages, temperature_bias=0.5)
        call_args = mock_provider.generate.call_args
        assert call_args[1]["temperature"] == pytest.approx(2.0)

        # 1.8 + (-2.5) = -0.7, should be clamped to 0.0
        await router.route(messages, temperature_bias=-2.5)
        call_args = mock_provider.generate.call_args
        assert call_args[1]["temperature"] == pytest.approx(0.0)
