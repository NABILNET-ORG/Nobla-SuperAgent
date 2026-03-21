"""Language detector — routes audio to the correct STT engine."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine

logger = logging.getLogger(__name__)

_ARABIC_CODES = {"ar", "ara"}


class LanguageDetector(STTEngine):
    """Routes audio to the correct STT engine based on language.

    - Arabic (any dialect) -> Levantine engine
    - All other languages  -> Standard Whisper engine
    - No language hint     -> Whisper detects language, re-routes if Arabic
    """

    def __init__(
        self,
        whisper_engine: STTEngine,
        levantine_engine: STTEngine,
    ) -> None:
        self._whisper = whisper_engine
        self._levantine = levantine_engine

    @property
    def name(self) -> str:
        return "detector"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        # Explicit Arabic hint -> use Levantine if available
        if language and language.lower() in _ARABIC_CODES:
            if await self._levantine.is_available():
                return await self._levantine.transcribe(audio, language=language)
            logger.warning("levantine_unavailable fallback=whisper")
            return await self._whisper.transcribe(audio, language=language)

        # Explicit non-Arabic hint -> use Whisper directly
        if language:
            return await self._whisper.transcribe(audio, language=language)

        # No hint -> auto-detect with Whisper, re-route if Arabic
        result = await self._whisper.transcribe(audio)
        if result.language in _ARABIC_CODES and await self._levantine.is_available():
            logger.info("arabic_detected rerouting=levantine")
            return await self._levantine.transcribe(audio)

        return result

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Stream through Whisper (language detection not supported in streaming)."""
        async for partial in self._whisper.transcribe_stream(audio_chunks):
            yield partial

    async def is_available(self) -> bool:
        return await self._whisper.is_available()
