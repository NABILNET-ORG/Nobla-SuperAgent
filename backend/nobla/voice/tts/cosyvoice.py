"""CosyVoice2 TTS engine."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from nobla.voice.tts.base import TTSEngine, VoiceInfo

logger = logging.getLogger(__name__)


def _load_cosyvoice_model(model_path: str) -> object:
    """Load the CosyVoice2 model. Isolated for testability."""
    try:
        from cosyvoice2 import CosyVoice2Model
        return CosyVoice2Model(model_path)
    except ImportError:
        logger.warning("cosyvoice2_not_installed using_stub=true")
        return None


class CosyVoiceTTS(TTSEngine):
    """CosyVoice2 TTS with multilingual support and voice cloning."""

    def __init__(self, model_path: str, device: str = "auto") -> None:
        self._model = _load_cosyvoice_model(model_path)
        self._model_path = model_path
        self._device = device
        logger.info("cosyvoice_loaded model=%s", model_path)

    @property
    def name(self) -> str:
        return "cosyvoice"

    async def _synthesize_internal(self, text: str, voice_id: str = "default") -> list[bytes]:
        """Internal synthesis. Handles voice cloning via 'clone:' prefix."""
        if self._model is None:
            raise RuntimeError("CosyVoice2 model not loaded")

        def _run():
            if voice_id.startswith("clone:"):
                ref_audio_path = voice_id[len("clone:"):]
                return list(self._model.synthesize(text, reference_audio=ref_audio_path))
            return list(self._model.synthesize(text, speaker=voice_id))

        return await asyncio.to_thread(_run)

    async def synthesize(self, text: str, voice_id: str = "default") -> AsyncIterator[bytes]:
        """Synthesize text to streaming audio chunks."""
        chunks = await self._synthesize_internal(text, voice_id=voice_id)
        for chunk in chunks:
            yield chunk

    async def get_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="default", name="Default", language="multi"),
            VoiceInfo(id="arabic", name="Arabic", language="ar"),
        ]

    async def is_available(self) -> bool:
        return self._model is not None
