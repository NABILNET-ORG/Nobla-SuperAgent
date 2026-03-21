"""Abstract base class for Speech-to-Text engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from nobla.voice.models import Transcript, PartialTranscript


class STTEngine(ABC):
    """Abstract STT engine. All STT implementations inherit from this."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine identifier (e.g. 'whisper', 'levantine')."""

    @abstractmethod
    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe a complete audio segment to text.

        Args:
            audio: Raw audio bytes (PCM 16kHz mono or Opus-decoded).
            language: Optional language hint. None = auto-detect.

        Returns:
            Final transcription with language and confidence.
        """

    @abstractmethod
    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Stream partial transcription results as audio arrives.

        Args:
            audio_chunks: Async iterator of audio byte chunks.

        Yields:
            Partial transcription results. Last one has is_final=True.
        """
        yield  # pragma: no cover

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this engine is ready (model loaded, service reachable)."""
