"""Tests for emotion detection engines."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nobla.voice.emotion.base import EmotionEngine
from nobla.persona.models import EmotionResult


class TestEmotionEngineInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            EmotionEngine()


class TestLocalEmotionEngine:
    @pytest.mark.asyncio
    async def test_detect_returns_emotion_result(self):
        from nobla.voice.emotion.local import LocalEmotionEngine

        with patch.object(
            LocalEmotionEngine, "_classify", return_value=("happy", 0.75, "curious")
        ):
            engine = LocalEmotionEngine.__new__(LocalEmotionEngine)
            engine._model = MagicMock()
            engine._processor = MagicMock()
            result = await engine.detect(b"fake_audio_bytes")
            assert isinstance(result, EmotionResult)
            assert result.emotion == "happy"
            assert result.source == "local"

    @pytest.mark.asyncio
    async def test_detect_maps_to_vocabulary(self):
        from nobla.voice.emotion.local import LocalEmotionEngine, EMOTION_MAP

        assert "angry" in EMOTION_MAP  # maps to our vocabulary
        assert EMOTION_MAP["angry"] == "frustrated"
