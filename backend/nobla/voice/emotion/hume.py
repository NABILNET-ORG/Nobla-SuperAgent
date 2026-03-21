"""Hume AI REST API client for emotion detection."""
from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)

# Map Hume emotion names to our 6-emotion vocabulary.
_HUME_MAP: dict[str, str] = {
    "joy": "happy",
    "amusement": "happy",
    "excitement": "happy",
    "sadness": "sad",
    "grief": "sad",
    "disappointment": "sad",
    "anger": "frustrated",
    "contempt": "frustrated",
    "annoyance": "frustrated",
    "interest": "curious",
    "surprise (positive)": "curious",
    "curiosity": "curious",
    "anxiety": "anxious",
    "fear": "anxious",
    "nervousness": "anxious",
}

_HUME_API_URL = "https://api.hume.ai/v0/batch/jobs"


class HumeEmotionEngine(EmotionEngine):
    """Hume AI prosody-based emotion detection."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    async def is_available(self) -> bool:
        return self._api_key is not None

    async def _call_api(self, audio: bytes) -> dict[str, Any]:
        """Send audio to Hume AI and return raw response."""
        encoded = base64.b64encode(audio).decode()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _HUME_API_URL,
                headers={
                    "X-Hume-Api-Key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "models": {"prosody": {}},
                    "data": [{"content": encoded, "content_type": "audio/wav"}],
                },
            )
            resp.raise_for_status()
            return resp.json()

    def _parse_response(self, data: dict[str, Any]) -> EmotionResult:
        """Extract top emotions from Hume API response."""
        try:
            emotions_list = (
                data["results"]["predictions"][0]["models"]["prosody"]
                ["grouped_predictions"][0]["predictions"][0]["emotions"]
            )
        except (KeyError, IndexError):
            return EmotionResult(
                emotion="neutral", confidence=0.0, source="hume"
            )

        sorted_emotions = sorted(emotions_list, key=lambda e: e["score"], reverse=True)
        top = sorted_emotions[0]
        second = sorted_emotions[1] if len(sorted_emotions) > 1 else None

        primary = _HUME_MAP.get(top["name"].lower(), "neutral")
        secondary = _HUME_MAP.get(second["name"].lower(), None) if second else None

        return EmotionResult(
            emotion=primary,
            confidence=round(top["score"], 2),
            secondary=secondary,
            source="hume",
        )

    async def detect(self, audio: bytes) -> EmotionResult:
        try:
            response = await self._call_api(audio)
            return self._parse_response(response)
        except Exception:
            logger.warning("Hume AI request failed", exc_info=True)
            raise
