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


class TestHumeEmotionEngine:
    @pytest.mark.asyncio
    async def test_is_available_without_key(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine
        engine = HumeEmotionEngine(api_key=None)
        assert await engine.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_with_key(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine
        engine = HumeEmotionEngine(api_key="test-key")
        assert await engine.is_available() is True

    @pytest.mark.asyncio
    async def test_detect_calls_api(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine

        engine = HumeEmotionEngine(api_key="test-key")
        mock_response = {
            "results": {
                "predictions": [{
                    "models": {
                        "prosody": {
                            "grouped_predictions": [{
                                "predictions": [{
                                    "emotions": [
                                        {"name": "Joy", "score": 0.85},
                                        {"name": "Interest", "score": 0.6},
                                        {"name": "Sadness", "score": 0.1},
                                    ]
                                }]
                            }]
                        }
                    }
                }]
            }
        }
        with patch.object(engine, "_call_api", return_value=mock_response):
            result = await engine.detect(b"fake_audio")
            assert result.source == "hume"
            assert result.emotion == "happy"
            assert result.confidence > 0
