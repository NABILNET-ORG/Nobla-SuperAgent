"""Levantine Arabic STT engine using custom Faster-Whisper model."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
from faster_whisper import WhisperModel

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine
from nobla.voice.stt.whisper import _pcm_to_float32

logger = logging.getLogger(__name__)


class LevantineSTT(STTEngine):
    """Levantine Arabic STT engine.

    Uses the custom ggml-levantine-large-v3.bin model fine-tuned
    for Levantine Arabic dialects. Always forces language='ar'.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model = WhisperModel(model_path, device=device, compute_type=compute_type)
        self._model_path = model_path
        logger.info("levantine_stt_loaded model=%s device=%s", model_path, device)

    @property
    def name(self) -> str:
        return "levantine"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe audio using the Levantine Arabic model.

        Always forces language='ar' regardless of the language hint,
        since this model is specialized for Arabic.
        """
        audio_array = _pcm_to_float32(audio)

        segments, info = await asyncio.to_thread(
            self._model.transcribe,
            audio_array,
            beam_size=5,
            vad_filter=True,
            language="ar",
        )

        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list).strip()

        if segment_list:
            avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
        else:
            confidence = 0.0

        return Transcript(
            text=text,
            language="ar",
            confidence=round(confidence, 3),
        )

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Buffer chunks and yield partial transcripts."""
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)
            if len(buffer) >= 64000:
                result = await self.transcribe(bytes(buffer))
                buffer.clear()
                yield PartialTranscript(
                    text=result.text, is_final=False, language="ar"
                )

        if buffer:
            result = await self.transcribe(bytes(buffer))
            yield PartialTranscript(text=result.text, is_final=True, language="ar")

    async def is_available(self) -> bool:
        return self._model is not None
