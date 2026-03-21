"""Pydantic models for the voice pipeline."""
from __future__ import annotations

import base64
from enum import Enum

from pydantic import BaseModel, Field


class VADMode(str, Enum):
    """Voice activity detection modes."""

    PUSH_TO_TALK = "push_to_talk"
    AUTO_DETECT = "auto_detect"
    WALKIE_TALKIE = "walkie_talkie"


class VoiceState(str, Enum):
    """Voice pipeline states."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class AudioFrame(BaseModel):
    """A single audio frame (typically 20ms of Opus-encoded audio)."""

    data: bytes
    sample_rate: int = 48000
    channels: int = 1
    duration_ms: int = 20

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode()

    @classmethod
    def from_base64(
        cls, encoded: str, sample_rate: int = 48000, channels: int = 1
    ) -> AudioFrame:
        return cls(data=base64.b64decode(encoded), sample_rate=sample_rate, channels=channels)


class VoiceConfig(BaseModel):
    """Configuration for a voice session."""

    vad_mode: VADMode = VADMode.PUSH_TO_TALK
    tts_engine: str = "cosyvoice"
    opus_bitrate: int = 32000
    silence_threshold_ms: int = 800
    min_speech_ms: int = 250


class Transcript(BaseModel):
    """Final transcription result from STT."""

    text: str
    language: str
    confidence: float = Field(ge=0.0, le=1.0)


class PartialTranscript(BaseModel):
    """Partial (streaming) transcription result."""

    text: str
    is_final: bool = False
    language: str | None = None


class VoiceSession(BaseModel):
    """Tracks state for an active voice session."""

    connection_id: str
    persona_id: str | None = None
    state: VoiceState = VoiceState.IDLE
    config: VoiceConfig = Field(default_factory=VoiceConfig)
