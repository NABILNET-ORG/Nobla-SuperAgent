"""Voice Activity Detection using Silero VAD."""
from __future__ import annotations

import logging
from collections.abc import Sequence

import torch

from nobla.voice.models import VADMode

logger = logging.getLogger(__name__)

# 30ms frame at 16kHz, 16-bit mono = 960 bytes
_FRAME_BYTES = 960
_SAMPLE_RATE = 16000


def _load_silero_vad() -> torch.nn.Module:
    """Load Silero VAD model."""
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    return model


class VoiceActivityDetector:
    """VAD with three modes: push-to-talk, auto-detect, walkie-talkie.

    Push-to-talk and walkie-talkie: buffer all audio between start/stop.
    Auto-detect: use Silero to find speech boundaries automatically.
    """

    def __init__(
        self,
        mode: VADMode = VADMode.PUSH_TO_TALK,
        silence_threshold_ms: int = 800,
        min_speech_ms: int = 250,
    ) -> None:
        self._mode = mode
        self._silence_threshold_ms = silence_threshold_ms
        self._min_speech_ms = min_speech_ms
        # Lazy-load: only auto-detect mode needs the Silero model
        self._vad_model = _load_silero_vad() if mode == VADMode.AUTO_DETECT else None

        self._buffer = bytearray()
        self._speech_buffer = bytearray()  # accumulates actual speech frames
        self._segments: list[bytes] = []
        self._is_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._active = False

    @property
    def mode(self) -> VADMode:
        return self._mode

    def start(self) -> None:
        """Begin a VAD session."""
        self._active = True
        self._buffer = bytearray()
        self._speech_buffer = bytearray()
        self._segments = []
        self._is_speech = False
        self._silence_frames = 0
        self._speech_frames = 0

    def feed(self, audio_chunk: bytes) -> None:
        """Feed an audio chunk to the VAD."""
        if not self._active:
            return

        if self._mode in (VADMode.PUSH_TO_TALK, VADMode.WALKIE_TALKIE):
            self._buffer.extend(audio_chunk)
            return

        self._buffer.extend(audio_chunk)
        self._process_auto_detect()

    def _process_auto_detect(self) -> None:
        """Process buffered audio with Silero VAD for speech boundary detection."""
        frames_per_silence = int(self._silence_threshold_ms / 30)
        frames_per_min_speech = int(self._min_speech_ms / 30)

        while len(self._buffer) >= _FRAME_BYTES:
            frame = bytes(self._buffer[:_FRAME_BYTES])
            del self._buffer[:_FRAME_BYTES]

            import numpy as np
            audio_float = (
                torch.from_numpy(
                    np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
                )
            )

            prob = self._vad_model(audio_float, _SAMPLE_RATE).item()

            if prob > 0.5:
                self._is_speech = True
                self._speech_frames += 1
                self._silence_frames = 0
                self._speech_buffer.extend(frame)
            elif self._is_speech:
                self._silence_frames += 1

                if self._silence_frames >= frames_per_silence:
                    if self._speech_frames >= frames_per_min_speech:
                        self._segments.append(bytes(self._speech_buffer))
                    self._is_speech = False
                    self._speech_frames = 0
                    self._silence_frames = 0
                    self._speech_buffer = bytearray()

    def get_segments(self) -> list[bytes]:
        """Get completed speech segments (auto-detect mode only)."""
        segments = self._segments[:]
        self._segments = []
        return segments

    def stop(self) -> list[bytes]:
        """Stop the VAD session and return any remaining audio."""
        self._active = False

        if self._mode in (VADMode.PUSH_TO_TALK, VADMode.WALKIE_TALKIE):
            if self._buffer:
                return [bytes(self._buffer)]
            return []

        remaining = self.get_segments()
        if self._buffer and self._is_speech:
            remaining.append(bytes(self._buffer))
        return remaining

    def reset(self) -> None:
        """Clear all buffers and state."""
        self._buffer = bytearray()
        self._speech_buffer = bytearray()
        self._segments = []
        self._is_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
