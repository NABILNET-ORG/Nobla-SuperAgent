"""Fish Speech V1.5 TTS engine."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from nobla.voice.tts.base import TTSEngine, VoiceInfo

logger = logging.getLogger(__name__)


def _load_fish_speech_model(model_path: str) -> object:
    """Load the Fish Speech model. Isolated for testability."""
    try:
        from fish_speech.inference import load_model
        return load_model(model_path)
    except ImportError:
        logger.warning("fish_speech_not_installed using_stub=true")
        return None


class FishSpeechTTS(TTSEngine):
    """Fish Speech V1.5 TTS with zero-shot voice cloning."""

    def __init__(self, model_path: str, device: str = "auto") -> None:
        self._model = _load_fish_speech_model(model_path)
        self._model_path = model_path
        self._device = device
        logger.info("fish_speech_loaded model=%s", model_path)

    @property
    def name(self) -> str:
        return "fish_speech"

    async def _synthesize_internal(self, text: str, voice_id: str = "default") -> list[bytes]:
        """Internal synthesis — produces list of audio chunks.

        Override point for testing. Production implementation calls
        the Fish Speech inference API.
        """
        if self._model is None:
            raise RuntimeError("Fish Speech model not loaded")

        def _run():
            chunks = []
            for chunk in self._model.synthesize(text, speaker=voice_id):
                chunks.append(bytes(chunk))
            return chunks

        return await asyncio.to_thread(_run)

    async def synthesize(self, text: str, voice_id: str = "default") -> AsyncIterator[bytes]:
        """Synthesize text to streaming audio chunks."""
        chunks = await self._synthesize_internal(text, voice_id=voice_id)
        for chunk in chunks:
            yield chunk

    async def get_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="default", name="Default", language="en"),
        ]

    async def is_available(self) -> bool:
        return self._model is not None
