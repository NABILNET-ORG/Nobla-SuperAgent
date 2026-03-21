"""Abstract base class for Text-to-Speech engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class VoiceInfo(BaseModel):
    """Metadata about an available voice."""

    id: str
    name: str
    language: str
    gender: str | None = None
    preview_url: str | None = None


class TTSEngine(ABC):
    """Abstract TTS engine. All TTS implementations inherit from this."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine identifier (e.g. 'fish_speech', 'cosyvoice')."""

    @abstractmethod
    async def synthesize(
        self, text: str, voice_id: str = "default"
    ) -> AsyncIterator[bytes]:
        """Synthesize text to an audio byte stream.

        Args:
            text: Text to synthesize.
            voice_id: Engine-specific voice identifier.

        Yields:
            Audio byte chunks (Opus-encoded or PCM).
        """
        yield  # pragma: no cover

    @abstractmethod
    async def get_voices(self) -> list[VoiceInfo]:
        """List available voices for this engine."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this engine is ready."""
