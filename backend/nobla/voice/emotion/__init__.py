"""Emotion detection subpackage — Hume AI + local wav2vec2 fallback."""
from nobla.voice.emotion.base import EmotionEngine
from nobla.voice.emotion.detector import EmotionDetector

__all__ = ["EmotionEngine", "EmotionDetector"]
