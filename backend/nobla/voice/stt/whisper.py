"""Faster-Whisper STT engine."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
from faster_whisper import WhisperModel

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine

logger = logging.getLogger(__name__)


def _pcm_to_float32(audio: bytes, sample_rate: int = 16000) -> np.ndarray:
    """Convert PCM 16-bit bytes to float32 numpy array."""
    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


class WhisperSTT(STTEngine):
    """Standard Faster-Whisper STT engine (large-v3)."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("whisper_stt_loaded model=%s device=%s", model_size, device)

    @property
    def name(self) -> str:
        return "whisper"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe audio bytes using Faster-Whisper."""
        audio_array = _pcm_to_float32(audio)

        kwargs: dict = {"beam_size": 5, "vad_filter": True}
        if language:
            kwargs["language"] = language

        segments, info = await asyncio.to_thread(
            self._model.transcribe, audio_array, **kwargs
        )

        # Collect segments (transcribe returns a generator)
        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list).strip()

        # Compute average confidence from log probabilities
        if segment_list:
            avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
        else:
            confidence = 0.0

        return Transcript(
            text=text,
            language=info.language,
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
                yield PartialTranscript(
                    text=result.text, is_final=False, language=result.language
                )

        if buffer:
            result = await self.transcribe(bytes(buffer))
            yield PartialTranscript(
                text=result.text, is_final=True, language=result.language
            )

    async def is_available(self) -> bool:
        return self._model is not None
