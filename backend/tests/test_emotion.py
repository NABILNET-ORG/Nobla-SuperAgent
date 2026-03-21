"""Tests for emotion detection engines."""
import time

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


class TestEmotionDetector:
    @pytest.mark.asyncio
    async def test_uses_hume_when_available(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result.source == "hume"
        local.detect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_local(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.side_effect = Exception("API down")
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.return_value = EmotionResult(
            emotion="neutral", confidence=0.6, source="local"
        )
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result.source == "local"

    @pytest.mark.asyncio
    async def test_returns_none_when_both_fail(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = False
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.side_effect = Exception("Model error")
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result is None

    @pytest.mark.asyncio
    async def test_caches_per_session(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        r1 = await detector.detect("session-1", b"audio")
        r2 = await detector.detect("session-1", b"audio")
        assert r1 == r2
        # detect called only once due to cache
        assert hume.detect.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=0)

        await detector.detect("session-1", b"audio")
        await detector.detect("session-1", b"audio")
        assert hume.detect.await_count == 2  # no caching with ttl=0

    def test_clear_session(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        detector._cache["session-1"] = (time.time(), MagicMock())
        detector.clear_session("session-1")
        assert "session-1" not in detector._cache
