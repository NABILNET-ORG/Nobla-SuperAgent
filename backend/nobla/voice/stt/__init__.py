"""Speech-to-Text engines."""
from nobla.voice.stt.base import STTEngine
from nobla.voice.stt.detector import LanguageDetector

__all__ = ["STTEngine", "LanguageDetector"]
