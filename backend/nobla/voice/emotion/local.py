"""Local wav2vec2-based emotion classifier — free, runs on CPU."""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)

# Map model labels to our 6-emotion vocabulary.
EMOTION_MAP: dict[str, str] = {
    "angry": "frustrated",
    "disgust": "frustrated",
    "fear": "anxious",
    "happy": "happy",
    "sad": "sad",
    "surprise": "curious",
    "neutral": "neutral",
    "calm": "neutral",
}

VALID_EMOTIONS = frozenset({"happy", "sad", "frustrated", "curious", "neutral", "anxious"})


class LocalEmotionEngine(EmotionEngine):
    """HuggingFace wav2vec2 emotion classifier."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._processor = None
        self._loaded = False

    async def is_available(self) -> bool:
        if not self._loaded:
            try:
                self._load_model()
            except Exception:
                logger.warning("Local emotion model unavailable", exc_info=True)
                return False
        return True

    def _load_model(self) -> None:
        """Lazy-load model on first use."""
        if self._loaded:
            return
        try:
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
            self._processor = Wav2Vec2Processor.from_pretrained(self._model_name)
            self._model = Wav2Vec2ForSequenceClassification.from_pretrained(self._model_name)
            self._loaded = True
            logger.info("Local emotion model loaded: %s", self._model_name)
        except Exception:
            logger.error("Failed to load emotion model %s", self._model_name, exc_info=True)
            raise

    def _classify(self, audio: bytes) -> tuple[str, float, str | None]:
        """Run classification, return (emotion, confidence, secondary)."""
        import torch

        self._load_model()
        audio_array = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        inputs = self._processor(audio_array, sampling_rate=16000, return_tensors="pt")

        with torch.no_grad():
            logits = self._model(**inputs).logits

        probs = torch.nn.functional.softmax(logits, dim=-1)[0]
        sorted_indices = torch.argsort(probs, descending=True)

        labels = self._model.config.id2label
        top_label = labels[sorted_indices[0].item()]
        top_conf = probs[sorted_indices[0]].item()
        second_label = labels[sorted_indices[1].item()] if len(sorted_indices) > 1 else None

        primary = EMOTION_MAP.get(top_label, "neutral")
        secondary = EMOTION_MAP.get(second_label, None) if second_label else None

        return primary, top_conf, secondary

    async def detect(self, audio: bytes) -> EmotionResult:
        primary, confidence, secondary = self._classify(audio)
        return EmotionResult(
            emotion=primary,
            confidence=round(confidence, 2),
            secondary=secondary,
            source="local",
        )
