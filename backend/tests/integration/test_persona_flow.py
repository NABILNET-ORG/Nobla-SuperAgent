# backend/tests/integration/test_persona_flow.py
"""Integration tests for the full persona flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.persona.manager import PersonaManager
from nobla.persona.prompt import PromptBuilder
from nobla.persona.presets import PROFESSIONAL_ID, FRIENDLY_ID
from nobla.persona.models import EmotionResult
from nobla.voice.emotion.detector import EmotionDetector
from nobla.voice.emotion.base import EmotionEngine


class TestPersonaFlow:
    """Test the full resolve -> prompt -> emotion flow."""

    @pytest.mark.asyncio
    async def test_full_text_chat_flow(self):
        """Text chat: resolve persona, build prompt, no emotion."""
        repo = AsyncMock()
        repo.get_default.return_value = FRIENDLY_ID
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        persona = await manager.resolve("session-1", "user-1")
        ctx = builder.build(persona, emotion=None)

        assert "Friendly" in ctx.system_prompt_addition
        assert "casual, warm" in ctx.system_prompt_addition
        assert ctx.temperature_bias == 0.2
        assert "mood" not in ctx.system_prompt_addition.lower()

    @pytest.mark.asyncio
    async def test_full_voice_flow_with_emotion(self):
        """Voice chat: resolve persona, detect emotion, build prompt."""
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        persona = await manager.resolve("session-1", "user-1")
        emotion = EmotionResult(
            emotion="frustrated",
            confidence=0.82,
            secondary="anxious",
            source="hume",
        )
        ctx = builder.build(persona, emotion=emotion)

        assert "Professional" in ctx.system_prompt_addition
        assert "frustrated" in ctx.system_prompt_addition
        assert "0.82" in ctx.system_prompt_addition

    @pytest.mark.asyncio
    async def test_session_persona_switch(self):
        """Switch persona mid-conversation."""
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        # Start with default (Professional)
        p1 = await manager.resolve("session-1", "user-1")
        assert p1.name == "Professional"

        # Switch to Military
        from nobla.persona.presets import MILITARY_ID
        manager.set_session_persona("session-1", MILITARY_ID)
        p2 = await manager.resolve("session-1", "user-1")
        assert p2.name == "Military"

        ctx = builder.build(p2, emotion=None)
        assert "terse, action-oriented" in ctx.system_prompt_addition

    @pytest.mark.asyncio
    async def test_emotion_fallback_chain(self):
        """Hume fails -> local succeeds."""
        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.side_effect = Exception("API timeout")

        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.return_value = EmotionResult(
            emotion="curious", confidence=0.65, source="local"
        )

        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        result = await detector.detect("conn-1", b"audio_data")

        assert result is not None
        assert result.emotion == "curious"
        assert result.source == "local"

    @pytest.mark.asyncio
    async def test_emotion_both_fail_gracefully(self):
        """Both engines fail -> None, persona works without emotion."""
        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = False
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = False

        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        result = await detector.detect("conn-1", b"audio_data")
        assert result is None

        # Persona still works without emotion
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()
        persona = await manager.resolve("session-1", "user-1")
        ctx = builder.build(persona, emotion=None)
        assert "Professional" in ctx.system_prompt_addition
        assert "mood" not in ctx.system_prompt_addition.lower()
