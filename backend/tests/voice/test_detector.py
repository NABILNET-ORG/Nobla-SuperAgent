"""Tests for STT language detector and routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.stt.detector import LanguageDetector
from nobla.voice.models import Transcript


class TestLanguageDetector:
    def _make_detector(self, whisper_engine=None, levantine_engine=None):
        whisper = whisper_engine or AsyncMock()
        whisper.name = "whisper"
        whisper.is_available = AsyncMock(return_value=True)
        levantine = levantine_engine or AsyncMock()
        levantine.name = "levantine"
        levantine.is_available = AsyncMock(return_value=True)
        return LanguageDetector(whisper_engine=whisper, levantine_engine=levantine)

    @pytest.mark.asyncio
    async def test_routes_arabic_to_levantine(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._levantine.transcribe = AsyncMock(
            return_value=Transcript(text="مرحبا", language="ar", confidence=0.9)
        )
        result = await detector.transcribe(silence_pcm_16khz, language="ar")
        detector._levantine.transcribe.assert_awaited_once()
        assert result.language == "ar"

    @pytest.mark.asyncio
    async def test_routes_english_to_whisper(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="hello", language="en", confidence=0.95)
        )
        result = await detector.transcribe(silence_pcm_16khz, language="en")
        detector._whisper.transcribe.assert_awaited_once()
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_auto_detect_uses_whisper_then_routes(self, silence_pcm_16khz):
        """When no language hint, run Whisper first. If it detects Arabic, re-run with Levantine."""
        detector = self._make_detector()
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="بعض النص", language="ar", confidence=0.6)
        )
        detector._levantine.transcribe = AsyncMock(
            return_value=Transcript(text="مرحبا كيفك", language="ar", confidence=0.95)
        )

        result = await detector.transcribe(silence_pcm_16khz)
        detector._levantine.transcribe.assert_awaited_once()
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_auto_detect_non_arabic_stays_whisper(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="bonjour", language="fr", confidence=0.9)
        )

        result = await detector.transcribe(silence_pcm_16khz)
        detector._levantine.transcribe.assert_not_awaited()
        assert result.text == "bonjour"

    @pytest.mark.asyncio
    async def test_fallback_when_levantine_unavailable(self, silence_pcm_16khz):
        """If Levantine model unavailable, fall back to Whisper for Arabic."""
        detector = self._make_detector()
        detector._levantine.is_available = AsyncMock(return_value=False)
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="arabic text", language="ar", confidence=0.7)
        )

        result = await detector.transcribe(silence_pcm_16khz, language="ar")
        detector._whisper.transcribe.assert_awaited_once()
