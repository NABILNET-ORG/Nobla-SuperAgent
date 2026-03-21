"""Emotion detector with Hume AI -> local fallback and per-session caching."""
from __future__ import annotations

import logging
import time

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)


class EmotionDetector:
    """Fallback chain: Hume AI -> local model -> None."""

    def __init__(
        self,
        hume: EmotionEngine,
        local: EmotionEngine,
        cache_ttl: int = 30,
    ) -> None:
        self._hume = hume
        self._local = local
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, EmotionResult]] = {}

    async def detect(
        self, connection_id: str, audio: bytes
    ) -> EmotionResult | None:
        """Detect emotion with caching and fallback."""
        # Check cache
        if connection_id in self._cache:
            cached_time, cached_result = self._cache[connection_id]
            if time.time() - cached_time < self._cache_ttl:
                return cached_result

        result = await self._detect_uncached(audio)
        if result is not None:
            self._cache[connection_id] = (time.time(), result)
        return result

    async def _detect_uncached(self, audio: bytes) -> EmotionResult | None:
        """Try Hume, fall back to local, return None if both fail."""
        # 1. Try Hume AI
        if await self._hume.is_available():
            try:
                return await self._hume.detect(audio)
            except Exception:
                logger.warning("Hume AI failed, falling back to local")

        # 2. Try local model
        if await self._local.is_available():
            try:
                return await self._local.detect(audio)
            except Exception:
                logger.warning("Local emotion model failed")

        # 3. Both unavailable
        logger.info("No emotion detection available")
        return None

    def clear_session(self, connection_id: str) -> None:
        """Remove cached emotion for a disconnected session."""
        self._cache.pop(connection_id, None)
