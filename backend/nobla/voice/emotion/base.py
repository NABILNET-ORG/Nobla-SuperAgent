"""Abstract base class for emotion detection engines."""
from __future__ import annotations

from abc import ABC, abstractmethod

from nobla.persona.models import EmotionResult


class EmotionEngine(ABC):
    """Interface for emotion detection from audio."""

    @abstractmethod
    async def detect(self, audio: bytes) -> EmotionResult:
        """Detect emotion from raw audio bytes."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this engine is ready to process."""
        ...
