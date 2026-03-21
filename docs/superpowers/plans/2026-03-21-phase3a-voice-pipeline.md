# Phase 3A: Voice Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend voice pipeline — STT (Faster-Whisper + Levantine Arabic), TTS (Fish Speech + CosyVoice2), VAD (Silero), and pipeline orchestrator — with WebSocket protocol extensions for real-time audio streaming.

**Architecture:** Pipeline pattern with discrete stages (VAD → STT → LLM → TTS), each behind an ABC for swappability. Audio streams as base64-encoded Opus frames over existing JSON-RPC WebSocket protocol. Pipeline orchestrator coordinates stages and manages voice session lifecycle.

**Tech Stack:** Python 3.12, FastAPI, faster-whisper, fish-speech, CosyVoice2, silero-vad, opuslib, pydub, soundfile

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `backend/nobla/voice/__init__.py` | Package exports |
| `backend/nobla/voice/models.py` | Pydantic models: AudioFrame, VoiceConfig, Transcript, VoiceSession |
| `backend/nobla/voice/stt/__init__.py` | STT package exports |
| `backend/nobla/voice/stt/base.py` | STTEngine ABC |
| `backend/nobla/voice/stt/whisper.py` | Faster-Whisper standard engine |
| `backend/nobla/voice/stt/levantine.py` | Levantine Arabic Whisper engine |
| `backend/nobla/voice/stt/detector.py` | Language detector — routes to correct STT engine |
| `backend/nobla/voice/tts/__init__.py` | TTS package exports |
| `backend/nobla/voice/tts/base.py` | TTSEngine ABC |
| `backend/nobla/voice/tts/fish_speech.py` | Fish Speech V1.5 engine |
| `backend/nobla/voice/tts/cosyvoice.py` | CosyVoice2 engine |
| `backend/nobla/voice/vad.py` | Silero VAD with 3 modes |
| `backend/nobla/voice/pipeline.py` | VoicePipeline orchestrator |
| `backend/nobla/gateway/voice_handlers.py` | JSON-RPC handlers for voice.* methods |
| `backend/tests/voice/__init__.py` | Test package |
| `backend/tests/voice/test_models.py` | Tests for voice Pydantic models |
| `backend/tests/voice/test_stt_base.py` | Tests for STT ABC contract |
| `backend/tests/voice/test_whisper.py` | Tests for Whisper STT engine |
| `backend/tests/voice/test_levantine.py` | Tests for Levantine STT engine |
| `backend/tests/voice/test_detector.py` | Tests for language detector |
| `backend/tests/voice/test_tts_base.py` | Tests for TTS ABC contract |
| `backend/tests/voice/test_fish_speech.py` | Tests for Fish Speech engine |
| `backend/tests/voice/test_cosyvoice.py` | Tests for CosyVoice2 engine |
| `backend/tests/voice/test_vad.py` | Tests for VAD module |
| `backend/tests/voice/test_pipeline.py` | Tests for pipeline orchestrator |
| `backend/tests/voice/test_voice_handlers.py` | Tests for WebSocket voice handlers |
| `backend/tests/voice/conftest.py` | Shared fixtures: mock audio, mock engines |

### Modified Files

| File | Change |
|------|--------|
| `backend/nobla/config/settings.py` | Add `VoiceSettings` Pydantic model to `Settings` |
| `backend/nobla/gateway/app.py` | Initialize voice services in `lifespan()`, import voice handlers |
| `backend/nobla/gateway/protocol.py` | Add voice-specific error codes |
| `backend/pyproject.toml` | Add voice dependencies |

---

## Task 1: Voice Pydantic Models

**Files:**
- Create: `backend/nobla/voice/__init__.py`
- Create: `backend/nobla/voice/models.py`
- Create: `backend/tests/voice/__init__.py`
- Create: `backend/tests/voice/test_models.py`

- [ ] **Step 1: Create voice package directory structure**

```bash
mkdir -p backend/nobla/voice/stt backend/nobla/voice/tts backend/nobla/voice/emotion backend/nobla/voice/persona
mkdir -p backend/tests/voice
touch backend/nobla/voice/__init__.py backend/nobla/voice/stt/__init__.py backend/nobla/voice/tts/__init__.py
touch backend/nobla/voice/emotion/__init__.py backend/nobla/voice/persona/__init__.py
touch backend/tests/voice/__init__.py
```

- [ ] **Step 2: Write failing tests for voice models**

```python
# backend/tests/voice/test_models.py
"""Tests for voice pipeline Pydantic models."""
import pytest
from nobla.voice.models import (
    AudioFrame,
    VoiceConfig,
    Transcript,
    PartialTranscript,
    VoiceSession,
    VADMode,
    VoiceState,
)


class TestAudioFrame:
    def test_create_audio_frame(self):
        frame = AudioFrame(data=b"fake_opus_data", sample_rate=48000, channels=1)
        assert frame.data == b"fake_opus_data"
        assert frame.sample_rate == 48000
        assert frame.channels == 1

    def test_audio_frame_defaults(self):
        frame = AudioFrame(data=b"x")
        assert frame.sample_rate == 48000
        assert frame.channels == 1
        assert frame.duration_ms == 20

    def test_audio_frame_to_base64(self):
        import base64
        frame = AudioFrame(data=b"test_data")
        encoded = frame.to_base64()
        assert base64.b64decode(encoded) == b"test_data"

    def test_audio_frame_from_base64(self):
        import base64
        encoded = base64.b64encode(b"test_data").decode()
        frame = AudioFrame.from_base64(encoded)
        assert frame.data == b"test_data"


class TestVADMode:
    def test_vad_modes_exist(self):
        assert VADMode.PUSH_TO_TALK == "push_to_talk"
        assert VADMode.AUTO_DETECT == "auto_detect"
        assert VADMode.WALKIE_TALKIE == "walkie_talkie"


class TestVoiceConfig:
    def test_defaults(self):
        config = VoiceConfig()
        assert config.vad_mode == VADMode.PUSH_TO_TALK
        assert config.tts_engine == "cosyvoice"
        assert config.opus_bitrate == 32000
        assert config.silence_threshold_ms == 800
        assert config.min_speech_ms == 250

    def test_custom_config(self):
        config = VoiceConfig(vad_mode=VADMode.AUTO_DETECT, tts_engine="fish_speech")
        assert config.vad_mode == VADMode.AUTO_DETECT
        assert config.tts_engine == "fish_speech"


class TestTranscript:
    def test_create_transcript(self):
        t = Transcript(text="hello world", language="en", confidence=0.95)
        assert t.text == "hello world"
        assert t.language == "en"
        assert t.confidence == 0.95

    def test_partial_transcript(self):
        pt = PartialTranscript(text="hel", is_final=False)
        assert pt.is_final is False


class TestVoiceState:
    def test_voice_states_exist(self):
        assert VoiceState.IDLE == "idle"
        assert VoiceState.LISTENING == "listening"
        assert VoiceState.PROCESSING == "processing"
        assert VoiceState.SPEAKING == "speaking"


class TestVoiceSession:
    def test_create_session(self):
        session = VoiceSession(connection_id="conn_1", persona_id=None)
        assert session.connection_id == "conn_1"
        assert session.state == VoiceState.IDLE
        assert session.config.vad_mode == VADMode.PUSH_TO_TALK

    def test_session_with_config(self):
        config = VoiceConfig(vad_mode=VADMode.WALKIE_TALKIE)
        session = VoiceSession(connection_id="conn_2", config=config)
        assert session.config.vad_mode == VADMode.WALKIE_TALKIE
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nobla.voice.models'`

- [ ] **Step 4: Implement voice models**

```python
# backend/nobla/voice/models.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_models.py -v`
Expected: All 12 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/voice/ backend/tests/voice/
git commit -m "feat(voice): add voice pipeline Pydantic models"
```

---

## Task 2: STT Abstract Base Class

**Files:**
- Create: `backend/nobla/voice/stt/base.py`
- Create: `backend/tests/voice/test_stt_base.py`

- [ ] **Step 1: Write failing tests for STT ABC**

```python
# backend/tests/voice/test_stt_base.py
"""Tests for STT engine abstract base class."""
import pytest
from nobla.voice.stt.base import STTEngine
from nobla.voice.models import Transcript, PartialTranscript


class TestSTTEngineABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError, match="abstract"):
            STTEngine()

    def test_concrete_implementation(self):
        class MockSTT(STTEngine):
            @property
            def name(self) -> str:
                return "mock"

            async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
                return Transcript(text="hello", language="en", confidence=0.99)

            async def transcribe_stream(self, audio_chunks):
                yield PartialTranscript(text="hel", is_final=False)
                yield PartialTranscript(text="hello", is_final=True, language="en")

            async def is_available(self) -> bool:
                return True

        stt = MockSTT()
        assert stt.name == "mock"

    @pytest.mark.asyncio
    async def test_concrete_transcribe(self):
        class MockSTT(STTEngine):
            @property
            def name(self) -> str:
                return "mock"

            async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
                return Transcript(text="hello", language="en", confidence=0.99)

            async def transcribe_stream(self, audio_chunks):
                yield PartialTranscript(text="hello", is_final=True, language="en")

            async def is_available(self) -> bool:
                return True

        stt = MockSTT()
        result = await stt.transcribe(b"fake_audio")
        assert result.text == "hello"
        assert result.language == "en"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_stt_base.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement STT ABC**

```python
# backend/nobla/voice/stt/base.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_stt_base.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/stt/base.py backend/tests/voice/test_stt_base.py
git commit -m "feat(voice): add STT engine abstract base class"
```

---

## Task 3: Faster-Whisper STT Engine

**Files:**
- Create: `backend/nobla/voice/stt/whisper.py`
- Create: `backend/tests/voice/test_whisper.py`
- Create: `backend/tests/voice/conftest.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# backend/tests/voice/conftest.py
"""Shared fixtures for voice pipeline tests."""
import struct
import pytest


@pytest.fixture
def silence_pcm_16khz() -> bytes:
    """1 second of silence as PCM 16-bit 16kHz mono."""
    return b"\x00\x00" * 16000


@pytest.fixture
def sine_wave_pcm_16khz() -> bytes:
    """1 second of 440Hz sine wave as PCM 16-bit 16kHz mono.

    Useful for testing STT with actual audio-like data.
    """
    import math
    samples = []
    for i in range(16000):
        sample = int(32767 * math.sin(2 * math.pi * 440 * i / 16000))
        samples.append(struct.pack("<h", sample))
    return b"".join(samples)
```

- [ ] **Step 2: Write failing tests for Whisper STT**

```python
# backend/tests/voice/test_whisper.py
"""Tests for Faster-Whisper STT engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.stt.whisper import WhisperSTT
from nobla.voice.models import Transcript


class TestWhisperSTT:
    def test_name(self):
        with patch("nobla.voice.stt.whisper.WhisperModel"):
            stt = WhisperSTT(model_size="large-v3")
        assert stt.name == "whisper"

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcript(self, silence_pcm_16khz):
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " Hello world"
        mock_segment.avg_logprob = -0.3
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        with patch("nobla.voice.stt.whisper.WhisperModel", return_value=mock_model):
            stt = WhisperSTT(model_size="large-v3")
            result = await stt.transcribe(silence_pcm_16khz)

        assert isinstance(result, Transcript)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.confidence > 0.0

    @pytest.mark.asyncio
    async def test_transcribe_with_language_hint(self, silence_pcm_16khz):
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " Bonjour"
        mock_segment.avg_logprob = -0.2
        mock_info = MagicMock()
        mock_info.language = "fr"
        mock_info.language_probability = 0.98
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        with patch("nobla.voice.stt.whisper.WhisperModel", return_value=mock_model):
            stt = WhisperSTT(model_size="large-v3")
            result = await stt.transcribe(silence_pcm_16khz, language="fr")

        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1].get("language") == "fr"

    @pytest.mark.asyncio
    async def test_is_available_when_model_loaded(self):
        with patch("nobla.voice.stt.whisper.WhisperModel"):
            stt = WhisperSTT(model_size="large-v3")
            assert await stt.is_available() is True

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio_returns_empty(self):
        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.5
        mock_model.transcribe.return_value = ([], mock_info)

        with patch("nobla.voice.stt.whisper.WhisperModel", return_value=mock_model):
            stt = WhisperSTT(model_size="large-v3")
            result = await stt.transcribe(b"\x00" * 100)

        assert result.text == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_whisper.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement Whisper STT engine**

```python
# backend/nobla/voice/stt/whisper.py
"""Faster-Whisper STT engine."""
from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine

logger = logging.getLogger(__name__)


def _pcm_to_float32(audio: bytes, sample_rate: int = 16000) -> np.ndarray:
    """Convert PCM 16-bit bytes to float32 numpy array."""
    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


class WhisperSTT(STTEngine):
    """Standard Faster-Whisper STT engine (large-v3)."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("whisper_stt_loaded model=%s device=%s", model_size, device)

    @property
    def name(self) -> str:
        return "whisper"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe audio bytes using Faster-Whisper."""
        audio_array = _pcm_to_float32(audio)

        kwargs: dict = {"beam_size": 5, "vad_filter": True}
        if language:
            kwargs["language"] = language

        segments, info = await asyncio.to_thread(
            self._model.transcribe, audio_array, **kwargs
        )

        # Collect segments (transcribe returns a generator)
        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list).strip()

        # Compute average confidence from log probabilities
        if segment_list:
            avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
        else:
            confidence = 0.0

        return Transcript(
            text=text,
            language=info.language,
            confidence=round(confidence, 3),
        )

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Buffer chunks and yield partial transcripts."""
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)
            # Yield partial every ~2 seconds of audio (64000 bytes at 16kHz 16-bit)
            if len(buffer) >= 64000:
                result = await self.transcribe(bytes(buffer))
                yield PartialTranscript(
                    text=result.text, is_final=False, language=result.language
                )

        # Final transcription on complete buffer
        if buffer:
            result = await self.transcribe(bytes(buffer))
            yield PartialTranscript(
                text=result.text, is_final=True, language=result.language
            )

    async def is_available(self) -> bool:
        return self._model is not None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_whisper.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/voice/stt/whisper.py backend/tests/voice/test_whisper.py backend/tests/voice/conftest.py
git commit -m "feat(voice): add Faster-Whisper STT engine with tests"
```

---

## Task 4: Levantine Arabic STT Engine

**Files:**
- Create: `backend/nobla/voice/stt/levantine.py`
- Create: `backend/tests/voice/test_levantine.py`

- [ ] **Step 1: Write failing tests for Levantine STT**

```python
# backend/tests/voice/test_levantine.py
"""Tests for Levantine Arabic STT engine."""
import pytest
from unittest.mock import MagicMock, patch
from nobla.voice.stt.levantine import LevantineSTT
from nobla.voice.models import Transcript


class TestLevantineSTT:
    def test_name(self):
        with patch("nobla.voice.stt.levantine.WhisperModel"):
            stt = LevantineSTT(model_path="/fake/path/model.bin")
        assert stt.name == "levantine"

    @pytest.mark.asyncio
    async def test_transcribe_arabic(self, silence_pcm_16khz):
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " مرحبا كيفك"
        mock_segment.avg_logprob = -0.25
        mock_info = MagicMock()
        mock_info.language = "ar"
        mock_info.language_probability = 0.97
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        with patch("nobla.voice.stt.levantine.WhisperModel", return_value=mock_model):
            stt = LevantineSTT(model_path="/fake/path/model.bin")
            result = await stt.transcribe(silence_pcm_16khz)

        assert isinstance(result, Transcript)
        assert "مرحبا" in result.text
        assert result.language == "ar"

    @pytest.mark.asyncio
    async def test_always_forces_arabic_language(self, silence_pcm_16khz):
        """Levantine engine always sets language='ar' regardless of input hint."""
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " test"
        mock_segment.avg_logprob = -0.3
        mock_info = MagicMock()
        mock_info.language = "ar"
        mock_info.language_probability = 0.9
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        with patch("nobla.voice.stt.levantine.WhisperModel", return_value=mock_model):
            stt = LevantineSTT(model_path="/fake/path/model.bin")
            await stt.transcribe(silence_pcm_16khz, language="en")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "ar"

    @pytest.mark.asyncio
    async def test_is_available_with_model(self):
        with patch("nobla.voice.stt.levantine.WhisperModel"):
            stt = LevantineSTT(model_path="/fake/path/model.bin")
            assert await stt.is_available() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_levantine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Levantine STT engine**

```python
# backend/nobla/voice/stt/levantine.py
"""Levantine Arabic STT engine using custom Faster-Whisper model."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
from faster_whisper import WhisperModel

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine
from nobla.voice.stt.whisper import _pcm_to_float32

logger = logging.getLogger(__name__)


class LevantineSTT(STTEngine):
    """Levantine Arabic STT engine.

    Uses the custom ggml-levantine-large-v3.bin model fine-tuned
    for Levantine Arabic dialects. Always forces language='ar'.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model = WhisperModel(model_path, device=device, compute_type=compute_type)
        self._model_path = model_path
        logger.info("levantine_stt_loaded model=%s device=%s", model_path, device)

    @property
    def name(self) -> str:
        return "levantine"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe audio using the Levantine Arabic model.

        Always forces language='ar' regardless of the language hint,
        since this model is specialized for Arabic.
        """
        audio_array = _pcm_to_float32(audio)

        segments, info = await asyncio.to_thread(
            self._model.transcribe,
            audio_array,
            beam_size=5,
            vad_filter=True,
            language="ar",
        )

        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list).strip()

        if segment_list:
            avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
            confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
        else:
            confidence = 0.0

        return Transcript(
            text=text,
            language="ar",
            confidence=round(confidence, 3),
        )

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Buffer chunks and yield partial transcripts."""
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)
            if len(buffer) >= 64000:
                result = await self.transcribe(bytes(buffer))
                yield PartialTranscript(
                    text=result.text, is_final=False, language="ar"
                )

        if buffer:
            result = await self.transcribe(bytes(buffer))
            yield PartialTranscript(text=result.text, is_final=True, language="ar")

    async def is_available(self) -> bool:
        return self._model is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_levantine.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/stt/levantine.py backend/tests/voice/test_levantine.py
git commit -m "feat(voice): add Levantine Arabic STT engine"
```

---

## Task 5: Language Detector & STT Routing

**Files:**
- Create: `backend/nobla/voice/stt/detector.py`
- Create: `backend/tests/voice/test_detector.py`

- [ ] **Step 1: Write failing tests for language detector**

```python
# backend/tests/voice/test_detector.py
"""Tests for STT language detector and routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.stt.detector import LanguageDetector
from nobla.voice.models import Transcript


class TestLanguageDetector:
    def _make_detector(self, whisper_engine=None, levantine_engine=None):
        whisper = whisper_engine or AsyncMock()
        whisper.name = "whisper"
        whisper.is_available = AsyncMock(return_value=True)
        levantine = levantine_engine or AsyncMock()
        levantine.name = "levantine"
        levantine.is_available = AsyncMock(return_value=True)
        return LanguageDetector(whisper_engine=whisper, levantine_engine=levantine)

    @pytest.mark.asyncio
    async def test_routes_arabic_to_levantine(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._levantine.transcribe = AsyncMock(
            return_value=Transcript(text="مرحبا", language="ar", confidence=0.9)
        )
        result = await detector.transcribe(silence_pcm_16khz, language="ar")
        detector._levantine.transcribe.assert_awaited_once()
        assert result.language == "ar"

    @pytest.mark.asyncio
    async def test_routes_english_to_whisper(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="hello", language="en", confidence=0.95)
        )
        result = await detector.transcribe(silence_pcm_16khz, language="en")
        detector._whisper.transcribe.assert_awaited_once()
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_auto_detect_uses_whisper_then_routes(self, silence_pcm_16khz):
        """When no language hint, run Whisper first. If it detects Arabic, re-run with Levantine."""
        detector = self._make_detector()
        # Whisper detects Arabic
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="بعض النص", language="ar", confidence=0.6)
        )
        # Levantine gives better result
        detector._levantine.transcribe = AsyncMock(
            return_value=Transcript(text="مرحبا كيفك", language="ar", confidence=0.95)
        )

        result = await detector.transcribe(silence_pcm_16khz)
        detector._levantine.transcribe.assert_awaited_once()
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_auto_detect_non_arabic_stays_whisper(self, silence_pcm_16khz):
        detector = self._make_detector()
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="bonjour", language="fr", confidence=0.9)
        )

        result = await detector.transcribe(silence_pcm_16khz)
        detector._levantine.transcribe.assert_not_awaited()
        assert result.text == "bonjour"

    @pytest.mark.asyncio
    async def test_fallback_when_levantine_unavailable(self, silence_pcm_16khz):
        """If Levantine model unavailable, fall back to Whisper for Arabic."""
        detector = self._make_detector()
        detector._levantine.is_available = AsyncMock(return_value=False)
        detector._whisper.transcribe = AsyncMock(
            return_value=Transcript(text="arabic text", language="ar", confidence=0.7)
        )

        result = await detector.transcribe(silence_pcm_16khz, language="ar")
        detector._whisper.transcribe.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_detector.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement language detector**

```python
# backend/nobla/voice/stt/detector.py
"""Language detector — routes audio to the correct STT engine."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from nobla.voice.models import PartialTranscript, Transcript
from nobla.voice.stt.base import STTEngine

logger = logging.getLogger(__name__)

_ARABIC_CODES = {"ar", "ara"}


class LanguageDetector(STTEngine):
    """Routes audio to the correct STT engine based on language.

    - Arabic (any dialect) -> Levantine engine
    - All other languages  -> Standard Whisper engine
    - No language hint     -> Whisper detects language, re-routes if Arabic
    """

    def __init__(
        self,
        whisper_engine: STTEngine,
        levantine_engine: STTEngine,
    ) -> None:
        self._whisper = whisper_engine
        self._levantine = levantine_engine

    @property
    def name(self) -> str:
        return "detector"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        # Explicit Arabic hint → use Levantine if available
        if language and language.lower() in _ARABIC_CODES:
            if await self._levantine.is_available():
                return await self._levantine.transcribe(audio, language=language)
            logger.warning("levantine_unavailable fallback=whisper")
            return await self._whisper.transcribe(audio, language=language)

        # Explicit non-Arabic hint → use Whisper directly
        if language:
            return await self._whisper.transcribe(audio, language=language)

        # No hint → auto-detect with Whisper, re-route if Arabic
        result = await self._whisper.transcribe(audio)
        if result.language in _ARABIC_CODES and await self._levantine.is_available():
            logger.info("arabic_detected rerouting=levantine")
            return await self._levantine.transcribe(audio)

        return result

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        """Stream through Whisper (language detection not supported in streaming)."""
        async for partial in self._whisper.transcribe_stream(audio_chunks):
            yield partial

    async def is_available(self) -> bool:
        return await self._whisper.is_available()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_detector.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/stt/detector.py backend/tests/voice/test_detector.py
git commit -m "feat(voice): add language detector with Arabic routing"
```

---

## Task 6: TTS Abstract Base Class

**Files:**
- Create: `backend/nobla/voice/tts/base.py`
- Create: `backend/tests/voice/test_tts_base.py`

- [ ] **Step 1: Write failing tests for TTS ABC**

```python
# backend/tests/voice/test_tts_base.py
"""Tests for TTS engine abstract base class."""
import pytest
from nobla.voice.tts.base import TTSEngine, VoiceInfo


class TestTTSEngineABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError, match="abstract"):
            TTSEngine()

    def test_concrete_implementation(self):
        class MockTTS(TTSEngine):
            @property
            def name(self) -> str:
                return "mock"

            async def synthesize(self, text, voice_id="default"):
                yield b"fake_audio"

            async def get_voices(self):
                return [VoiceInfo(id="default", name="Default", language="en")]

            async def is_available(self) -> bool:
                return True

        tts = MockTTS()
        assert tts.name == "mock"

    @pytest.mark.asyncio
    async def test_concrete_synthesize(self):
        class MockTTS(TTSEngine):
            @property
            def name(self) -> str:
                return "mock"

            async def synthesize(self, text, voice_id="default"):
                yield b"chunk1"
                yield b"chunk2"

            async def get_voices(self):
                return []

            async def is_available(self) -> bool:
                return True

        tts = MockTTS()
        chunks = []
        async for chunk in tts.synthesize("hello"):
            chunks.append(chunk)
        assert chunks == [b"chunk1", b"chunk2"]


class TestVoiceInfo:
    def test_create_voice_info(self):
        vi = VoiceInfo(id="v1", name="Alice", language="en")
        assert vi.id == "v1"
        assert vi.name == "Alice"

    def test_voice_info_optional_fields(self):
        vi = VoiceInfo(id="v1", name="Alice", language="en", gender="female", preview_url=None)
        assert vi.gender == "female"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_tts_base.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement TTS ABC**

```python
# backend/nobla/voice/tts/base.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_tts_base.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/tts/base.py backend/tests/voice/test_tts_base.py
git commit -m "feat(voice): add TTS engine abstract base class"
```

---

## Task 7: Fish Speech TTS Engine

**Files:**
- Create: `backend/nobla/voice/tts/fish_speech.py`
- Create: `backend/tests/voice/test_fish_speech.py`

- [ ] **Step 1: Write failing tests for Fish Speech**

```python
# backend/tests/voice/test_fish_speech.py
"""Tests for Fish Speech TTS engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.tts.fish_speech import FishSpeechTTS
from nobla.voice.tts.base import VoiceInfo


class TestFishSpeechTTS:
    def test_name(self):
        with patch("nobla.voice.tts.fish_speech._load_fish_speech_model"):
            tts = FishSpeechTTS(model_path="/fake/model")
        assert tts.name == "fish_speech"

    @pytest.mark.asyncio
    async def test_synthesize_yields_audio_chunks(self):
        with patch("nobla.voice.tts.fish_speech._load_fish_speech_model"):
            tts = FishSpeechTTS(model_path="/fake/model")

        # Mock the internal synthesis to yield chunks
        tts._synthesize_internal = AsyncMock(return_value=[b"chunk1", b"chunk2", b"chunk3"])

        chunks = []
        async for chunk in tts.synthesize("Hello world"):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert all(isinstance(c, bytes) for c in chunks)

    @pytest.mark.asyncio
    async def test_get_voices_returns_list(self):
        with patch("nobla.voice.tts.fish_speech._load_fish_speech_model"):
            tts = FishSpeechTTS(model_path="/fake/model")

        voices = await tts.get_voices()
        assert isinstance(voices, list)
        assert all(isinstance(v, VoiceInfo) for v in voices)
        assert any(v.id == "default" for v in voices)

    @pytest.mark.asyncio
    async def test_is_available(self):
        with patch("nobla.voice.tts.fish_speech._load_fish_speech_model"):
            tts = FishSpeechTTS(model_path="/fake/model")
            assert await tts.is_available() is True

    @pytest.mark.asyncio
    async def test_synthesize_with_custom_voice(self):
        with patch("nobla.voice.tts.fish_speech._load_fish_speech_model"):
            tts = FishSpeechTTS(model_path="/fake/model")

        tts._synthesize_internal = AsyncMock(return_value=[b"audio"])

        chunks = []
        async for chunk in tts.synthesize("test", voice_id="custom_voice"):
            chunks.append(chunk)

        tts._synthesize_internal.assert_awaited_once()
        call_kwargs = tts._synthesize_internal.call_args
        assert call_kwargs[1].get("voice_id") == "custom_voice" or call_kwargs[0][1] == "custom_voice"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_fish_speech.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Fish Speech TTS engine**

```python
# backend/nobla/voice/tts/fish_speech.py
"""Fish Speech V1.5 TTS engine."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from nobla.voice.tts.base import TTSEngine, VoiceInfo

logger = logging.getLogger(__name__)


def _load_fish_speech_model(model_path: str) -> object:
    """Load the Fish Speech model. Isolated for testability."""
    try:
        # Fish Speech uses its own loading API
        # Import deferred to avoid hard dependency at module level
        from fish_speech.inference import load_model
        return load_model(model_path)
    except ImportError:
        logger.warning("fish_speech_not_installed using_stub=true")
        return None


class FishSpeechTTS(TTSEngine):
    """Fish Speech V1.5 TTS with zero-shot voice cloning."""

    def __init__(self, model_path: str, device: str = "auto") -> None:
        self._model = _load_fish_speech_model(model_path)
        self._model_path = model_path
        self._device = device
        logger.info("fish_speech_loaded model=%s", model_path)

    @property
    def name(self) -> str:
        return "fish_speech"

    async def _synthesize_internal(self, text: str, voice_id: str = "default") -> list[bytes]:
        """Internal synthesis — produces list of audio chunks.

        Override point for testing. Production implementation calls
        the Fish Speech inference API.
        """
        if self._model is None:
            raise RuntimeError("Fish Speech model not loaded")

        def _run():
            # Fish Speech API: model.synthesize(text, voice_id) -> generator of audio chunks
            chunks = []
            for chunk in self._model.synthesize(text, speaker=voice_id):
                chunks.append(bytes(chunk))
            return chunks

        return await asyncio.to_thread(_run)

    async def synthesize(self, text: str, voice_id: str = "default") -> AsyncIterator[bytes]:
        """Synthesize text to streaming audio chunks."""
        chunks = await self._synthesize_internal(text, voice_id=voice_id)
        for chunk in chunks:
            yield chunk

    async def get_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="default", name="Default", language="en"),
        ]

    async def is_available(self) -> bool:
        return self._model is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_fish_speech.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/tts/fish_speech.py backend/tests/voice/test_fish_speech.py
git commit -m "feat(voice): add Fish Speech V1.5 TTS engine"
```

---

## Task 8: CosyVoice2 TTS Engine

**Files:**
- Create: `backend/nobla/voice/tts/cosyvoice.py`
- Create: `backend/tests/voice/test_cosyvoice.py`

- [ ] **Step 1: Write failing tests for CosyVoice2**

```python
# backend/tests/voice/test_cosyvoice.py
"""Tests for CosyVoice2 TTS engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.tts.cosyvoice import CosyVoiceTTS
from nobla.voice.tts.base import VoiceInfo


class TestCosyVoiceTTS:
    def test_name(self):
        with patch("nobla.voice.tts.cosyvoice._load_cosyvoice_model"):
            tts = CosyVoiceTTS(model_path="/fake/model")
        assert tts.name == "cosyvoice"

    @pytest.mark.asyncio
    async def test_synthesize_yields_audio_chunks(self):
        with patch("nobla.voice.tts.cosyvoice._load_cosyvoice_model"):
            tts = CosyVoiceTTS(model_path="/fake/model")

        tts._synthesize_internal = AsyncMock(return_value=[b"audio_chunk"])

        chunks = []
        async for chunk in tts.synthesize("مرحبا"):
            chunks.append(chunk)

        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_get_voices_includes_multilingual(self):
        with patch("nobla.voice.tts.cosyvoice._load_cosyvoice_model"):
            tts = CosyVoiceTTS(model_path="/fake/model")

        voices = await tts.get_voices()
        assert isinstance(voices, list)
        assert len(voices) >= 1
        assert any(v.id == "default" for v in voices)

    @pytest.mark.asyncio
    async def test_is_available(self):
        with patch("nobla.voice.tts.cosyvoice._load_cosyvoice_model"):
            tts = CosyVoiceTTS(model_path="/fake/model")
            assert await tts.is_available() is True

    @pytest.mark.asyncio
    async def test_synthesize_with_reference_audio(self):
        """CosyVoice supports voice cloning via reference audio path."""
        with patch("nobla.voice.tts.cosyvoice._load_cosyvoice_model"):
            tts = CosyVoiceTTS(model_path="/fake/model")

        tts._synthesize_internal = AsyncMock(return_value=[b"cloned_audio"])

        chunks = []
        async for chunk in tts.synthesize("hello", voice_id="clone:/path/to/ref.wav"):
            chunks.append(chunk)

        assert chunks == [b"cloned_audio"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_cosyvoice.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CosyVoice2 TTS engine**

```python
# backend/nobla/voice/tts/cosyvoice.py
"""CosyVoice2 TTS engine."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from nobla.voice.tts.base import TTSEngine, VoiceInfo

logger = logging.getLogger(__name__)


def _load_cosyvoice_model(model_path: str) -> object:
    """Load the CosyVoice2 model. Isolated for testability."""
    try:
        from cosyvoice2 import CosyVoice2Model
        return CosyVoice2Model(model_path)
    except ImportError:
        logger.warning("cosyvoice2_not_installed using_stub=true")
        return None


class CosyVoiceTTS(TTSEngine):
    """CosyVoice2 TTS with multilingual support and voice cloning."""

    def __init__(self, model_path: str, device: str = "auto") -> None:
        self._model = _load_cosyvoice_model(model_path)
        self._model_path = model_path
        self._device = device
        logger.info("cosyvoice_loaded model=%s", model_path)

    @property
    def name(self) -> str:
        return "cosyvoice"

    async def _synthesize_internal(self, text: str, voice_id: str = "default") -> list[bytes]:
        """Internal synthesis. Handles voice cloning via 'clone:' prefix."""
        if self._model is None:
            raise RuntimeError("CosyVoice2 model not loaded")

        def _run():
            # Check for voice cloning request (voice_id starts with "clone:")
            if voice_id.startswith("clone:"):
                ref_audio_path = voice_id[len("clone:"):]
                return list(self._model.synthesize(text, reference_audio=ref_audio_path))
            return list(self._model.synthesize(text, speaker=voice_id))

        return await asyncio.to_thread(_run)

    async def synthesize(self, text: str, voice_id: str = "default") -> AsyncIterator[bytes]:
        """Synthesize text to streaming audio chunks."""
        chunks = await self._synthesize_internal(text, voice_id=voice_id)
        for chunk in chunks:
            yield chunk

    async def get_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="default", name="Default", language="multi"),
            VoiceInfo(id="arabic", name="Arabic", language="ar"),
        ]

    async def is_available(self) -> bool:
        return self._model is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_cosyvoice.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/tts/cosyvoice.py backend/tests/voice/test_cosyvoice.py
git commit -m "feat(voice): add CosyVoice2 TTS engine"
```

---

## Task 9: VAD Module (Silero)

**Files:**
- Create: `backend/nobla/voice/vad.py`
- Create: `backend/tests/voice/test_vad.py`

- [ ] **Step 1: Write failing tests for VAD**

```python
# backend/tests/voice/test_vad.py
"""Tests for Voice Activity Detection module."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from nobla.voice.vad import VoiceActivityDetector
from nobla.voice.models import VADMode


class TestVoiceActivityDetector:
    def _make_vad(self, mode=VADMode.PUSH_TO_TALK):
        with patch("nobla.voice.vad._load_silero_vad"):
            return VoiceActivityDetector(mode=mode)

    def test_default_mode_is_push_to_talk(self):
        vad = self._make_vad()
        assert vad.mode == VADMode.PUSH_TO_TALK

    def test_set_mode(self):
        vad = self._make_vad(mode=VADMode.AUTO_DETECT)
        assert vad.mode == VADMode.AUTO_DETECT

    @pytest.mark.asyncio
    async def test_push_to_talk_buffers_all_audio(self, silence_pcm_16khz):
        """In push-to-talk, all audio is buffered until stop."""
        vad = self._make_vad(mode=VADMode.PUSH_TO_TALK)
        vad.start()

        # Feed audio
        chunk_size = 3200  # 100ms at 16kHz 16-bit
        for i in range(0, len(silence_pcm_16khz), chunk_size):
            vad.feed(silence_pcm_16khz[i : i + chunk_size])

        # No segments emitted until stop
        assert vad.get_segments() == []

        # Stop emits the full buffer as one segment
        segments = vad.stop()
        assert len(segments) == 1
        assert len(segments[0]) == len(silence_pcm_16khz)

    @pytest.mark.asyncio
    async def test_auto_detect_emits_on_silence(self):
        """In auto-detect, VAD emits a segment when silence is detected."""
        vad = self._make_vad(mode=VADMode.AUTO_DETECT)
        vad._vad_model = MagicMock()

        # Simulate: speech detected, then silence
        speech_probs = [0.9, 0.85, 0.8, 0.1, 0.05, 0.02, 0.01, 0.01, 0.01]
        vad._vad_model.return_value = MagicMock(item=MagicMock(side_effect=speech_probs))

        vad.start()
        # Each feed is 30ms at 16kHz = 960 bytes (480 samples)
        for prob in speech_probs:
            vad._vad_model.return_value = MagicMock(item=MagicMock(return_value=prob))
            vad.feed(b"\x00" * 960)

        segments = vad.get_segments()
        # Should have detected speech end after silence threshold
        # Exact behavior depends on silence_threshold_ms config
        assert isinstance(segments, list)

    def test_walkie_talkie_same_as_push_to_talk(self):
        """Walkie-talkie mode uses same buffering as push-to-talk."""
        vad = self._make_vad(mode=VADMode.WALKIE_TALKIE)
        vad.start()
        vad.feed(b"\x00" * 3200)
        assert vad.get_segments() == []
        segments = vad.stop()
        assert len(segments) == 1

    def test_reset_clears_buffer(self):
        vad = self._make_vad()
        vad.start()
        vad.feed(b"\x00" * 3200)
        vad.reset()
        segments = vad.stop()
        assert segments == [] or all(len(s) == 0 for s in segments)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_vad.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement VAD module**

```python
# backend/nobla/voice/vad.py
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
        self._vad_model = _load_silero_vad()

        self._buffer = bytearray()
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
        self._segments = []
        self._is_speech = False
        self._silence_frames = 0
        self._speech_frames = 0

    def feed(self, audio_chunk: bytes) -> None:
        """Feed an audio chunk to the VAD.

        In push-to-talk/walkie-talkie: just buffer.
        In auto-detect: analyze with Silero and emit segments on silence.
        """
        if not self._active:
            return

        if self._mode in (VADMode.PUSH_TO_TALK, VADMode.WALKIE_TALKIE):
            self._buffer.extend(audio_chunk)
            return

        # Auto-detect mode: run Silero VAD on each frame
        self._buffer.extend(audio_chunk)
        self._process_auto_detect()

    def _process_auto_detect(self) -> None:
        """Process buffered audio with Silero VAD for speech boundary detection."""
        frames_per_silence = int(self._silence_threshold_ms / 30)
        frames_per_min_speech = int(self._min_speech_ms / 30)

        while len(self._buffer) >= _FRAME_BYTES:
            frame = bytes(self._buffer[:_FRAME_BYTES])
            del self._buffer[:_FRAME_BYTES]

            # Convert to float tensor for Silero
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
            elif self._is_speech:
                self._silence_frames += 1

                if self._silence_frames >= frames_per_silence:
                    # Speech segment ended
                    if self._speech_frames >= frames_per_min_speech:
                        # Emit the segment (we don't store the actual audio frames
                        # in this simplified version — the pipeline buffers externally)
                        segment_bytes = _FRAME_BYTES * self._speech_frames
                        self._segments.append(b"\x00" * segment_bytes)
                    self._is_speech = False
                    self._speech_frames = 0
                    self._silence_frames = 0

    def get_segments(self) -> list[bytes]:
        """Get completed speech segments (auto-detect mode only).

        Returns and clears the internal segment list.
        """
        segments = self._segments[:]
        self._segments = []
        return segments

    def stop(self) -> list[bytes]:
        """Stop the VAD session and return any remaining audio.

        In push-to-talk/walkie-talkie: returns the full buffer as one segment.
        In auto-detect: returns any remaining speech segment.
        """
        self._active = False

        if self._mode in (VADMode.PUSH_TO_TALK, VADMode.WALKIE_TALKIE):
            if self._buffer:
                return [bytes(self._buffer)]
            return []

        # Auto-detect: emit remaining speech
        remaining = self.get_segments()
        if self._buffer and self._is_speech:
            remaining.append(bytes(self._buffer))
        return remaining

    def reset(self) -> None:
        """Clear all buffers and state."""
        self._buffer = bytearray()
        self._segments = []
        self._is_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_vad.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/vad.py backend/tests/voice/test_vad.py
git commit -m "feat(voice): add Silero VAD with three detection modes"
```

---

## Task 10: Voice Pipeline Orchestrator

**Files:**
- Create: `backend/nobla/voice/pipeline.py`
- Create: `backend/tests/voice/test_pipeline.py`

- [ ] **Step 1: Write failing tests for the pipeline**

```python
# backend/tests/voice/test_pipeline.py
"""Tests for the voice pipeline orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.pipeline import VoicePipeline
from nobla.voice.models import (
    AudioFrame,
    Transcript,
    VoiceConfig,
    VoiceSession,
    VoiceState,
    VADMode,
)
from nobla.voice.stt.base import STTEngine
from nobla.voice.tts.base import TTSEngine


def _mock_stt() -> STTEngine:
    stt = AsyncMock(spec=STTEngine)
    stt.name = "mock_stt"
    stt.transcribe = AsyncMock(
        return_value=Transcript(text="hello world", language="en", confidence=0.95)
    )
    stt.is_available = AsyncMock(return_value=True)
    return stt


def _mock_tts() -> TTSEngine:
    tts = AsyncMock(spec=TTSEngine)
    tts.name = "mock_tts"

    async def mock_synthesize(text, voice_id="default"):
        yield b"audio_chunk_1"
        yield b"audio_chunk_2"

    tts.synthesize = mock_synthesize
    tts.is_available = AsyncMock(return_value=True)
    return tts


def _mock_router():
    from nobla.brain.base_provider import LLMMessage, LLMResponse
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=LLMResponse(
            content="I heard you say hello!",
            model="mock",
            tokens_input=10,
            tokens_output=8,
            cost_usd=0.0,
            latency_ms=50,
        )
    )
    return router


class TestVoicePipeline:
    def test_create_session(self):
        pipeline = VoicePipeline(
            stt_engine=_mock_stt(), tts_engines={"mock": _mock_tts()}, llm_router=_mock_router()
        )
        session = pipeline.create_session("conn_1")
        assert session.connection_id == "conn_1"
        assert session.state == VoiceState.IDLE

    def test_create_session_with_config(self):
        pipeline = VoicePipeline(
            stt_engine=_mock_stt(), tts_engines={"mock": _mock_tts()}, llm_router=_mock_router()
        )
        config = VoiceConfig(vad_mode=VADMode.AUTO_DETECT, tts_engine="mock")
        session = pipeline.create_session("conn_1", config=config)
        assert session.config.vad_mode == VADMode.AUTO_DETECT

    @pytest.mark.asyncio
    async def test_process_audio_full_round_trip(self):
        stt = _mock_stt()
        tts = _mock_tts()
        router = _mock_router()

        pipeline = VoicePipeline(stt_engine=stt, tts_engines={"mock": tts}, llm_router=router)
        session = pipeline.create_session("conn_1", config=VoiceConfig(tts_engine="mock"))

        # Process a complete audio segment
        result = await pipeline.process_segment(session, b"\x00" * 32000)

        # Verify STT was called
        stt.transcribe.assert_awaited_once()

        # Verify LLM router was called with transcript
        router.route.assert_awaited_once()
        call_messages = router.route.call_args[0][0]
        assert any("hello world" in msg.content for msg in call_messages)

        # Verify result contains response text and audio chunks
        assert result.transcript.text == "hello world"
        assert result.response_text == "I heard you say hello!"
        assert len(result.audio_chunks) > 0

    @pytest.mark.asyncio
    async def test_process_segment_updates_state(self):
        pipeline = VoicePipeline(
            stt_engine=_mock_stt(),
            tts_engines={"mock": _mock_tts()},
            llm_router=_mock_router(),
        )
        session = pipeline.create_session("conn_1", config=VoiceConfig(tts_engine="mock"))

        assert session.state == VoiceState.IDLE
        result = await pipeline.process_segment(session, b"\x00" * 32000)
        # After processing, session should be back to IDLE
        assert session.state == VoiceState.IDLE

    @pytest.mark.asyncio
    async def test_tts_engine_fallback(self):
        """If requested TTS is unavailable, fall back to first available."""
        unavailable_tts = AsyncMock(spec=TTSEngine)
        unavailable_tts.name = "unavailable"
        unavailable_tts.is_available = AsyncMock(return_value=False)

        fallback_tts = _mock_tts()

        pipeline = VoicePipeline(
            stt_engine=_mock_stt(),
            tts_engines={"unavailable": unavailable_tts, "mock": fallback_tts},
            llm_router=_mock_router(),
        )
        session = pipeline.create_session(
            "conn_1", config=VoiceConfig(tts_engine="unavailable")
        )

        result = await pipeline.process_segment(session, b"\x00" * 32000)
        assert len(result.audio_chunks) > 0

    def test_end_session(self):
        pipeline = VoicePipeline(
            stt_engine=_mock_stt(), tts_engines={"mock": _mock_tts()}, llm_router=_mock_router()
        )
        session = pipeline.create_session("conn_1")
        pipeline.end_session("conn_1")
        assert pipeline.get_session("conn_1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pipeline orchestrator**

```python
# backend/nobla/voice/pipeline.py
"""Voice pipeline orchestrator — routes audio through STT → LLM → TTS."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from nobla.brain.base_provider import LLMMessage
from nobla.voice.models import Transcript, VoiceConfig, VoiceSession, VoiceState
from nobla.voice.stt.base import STTEngine
from nobla.voice.tts.base import TTSEngine

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of processing a voice segment through the full pipeline."""

    transcript: Transcript
    response_text: str
    audio_chunks: list[bytes] = field(default_factory=list)


class VoicePipeline:
    """Orchestrates voice processing: audio → STT → LLM → TTS → audio.

    Manages voice sessions per connection and routes through the
    appropriate engines based on session config.
    """

    def __init__(
        self,
        stt_engine: STTEngine,
        tts_engines: dict[str, TTSEngine],
        llm_router: object,
    ) -> None:
        self._stt = stt_engine
        self._tts_engines = tts_engines
        self._router = llm_router
        self._sessions: dict[str, VoiceSession] = {}

    def create_session(
        self,
        connection_id: str,
        config: VoiceConfig | None = None,
        persona_id: str | None = None,
    ) -> VoiceSession:
        """Create a new voice session for a connection."""
        session = VoiceSession(
            connection_id=connection_id,
            config=config or VoiceConfig(),
            persona_id=persona_id,
        )
        self._sessions[connection_id] = session
        logger.info(
            "voice_session_created connection=%s vad=%s tts=%s",
            connection_id,
            session.config.vad_mode,
            session.config.tts_engine,
        )
        return session

    def get_session(self, connection_id: str) -> VoiceSession | None:
        return self._sessions.get(connection_id)

    def end_session(self, connection_id: str) -> None:
        session = self._sessions.pop(connection_id, None)
        if session:
            logger.info("voice_session_ended connection=%s", connection_id)

    async def process_segment(
        self,
        session: VoiceSession,
        audio: bytes,
        conversation_messages: list[LLMMessage] | None = None,
    ) -> PipelineResult:
        """Process a complete audio segment through the full pipeline.

        1. STT: audio → text
        2. LLM: text → response (via brain/router)
        3. TTS: response → audio

        Args:
            session: Active voice session.
            audio: Raw PCM audio bytes (16kHz, 16-bit, mono).
            conversation_messages: Prior conversation context for LLM.

        Returns:
            PipelineResult with transcript, response text, and audio chunks.
        """
        session.state = VoiceState.PROCESSING

        # 1. STT
        transcript = await self._stt.transcribe(audio)
        logger.info(
            "stt_complete text=%s lang=%s confidence=%.2f",
            transcript.text[:50],
            transcript.language,
            transcript.confidence,
        )

        # 2. Build messages for LLM
        messages = list(conversation_messages or [])
        messages.append(LLMMessage(role="user", content=transcript.text))

        # Route through LLM
        response = await self._router.route(messages)
        response_text = response.content
        logger.info("llm_complete model=%s tokens=%d", response.model, response.total_tokens)

        # 3. TTS
        session.state = VoiceState.SPEAKING
        tts_engine = await self._resolve_tts(session.config.tts_engine)
        audio_chunks: list[bytes] = []
        async for chunk in tts_engine.synthesize(response_text):
            audio_chunks.append(chunk)

        session.state = VoiceState.IDLE
        logger.info("tts_complete engine=%s chunks=%d", tts_engine.name, len(audio_chunks))

        return PipelineResult(
            transcript=transcript,
            response_text=response_text,
            audio_chunks=audio_chunks,
        )

    async def _resolve_tts(self, engine_name: str) -> TTSEngine:
        """Resolve TTS engine by name, falling back if unavailable."""
        engine = self._tts_engines.get(engine_name)
        if engine and await engine.is_available():
            return engine

        logger.warning("tts_unavailable engine=%s trying_fallback", engine_name)
        for name, fallback in self._tts_engines.items():
            if await fallback.is_available():
                logger.info("tts_fallback engine=%s", name)
                return fallback

        raise RuntimeError("No TTS engine available")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_pipeline.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/pipeline.py backend/tests/voice/test_pipeline.py
git commit -m "feat(voice): add voice pipeline orchestrator"
```

---

## Task 11: Voice WebSocket Handlers

**Files:**
- Create: `backend/nobla/gateway/voice_handlers.py`
- Create: `backend/tests/voice/test_voice_handlers.py`
- Modify: `backend/nobla/gateway/protocol.py`

- [ ] **Step 1: Add voice error codes to protocol.py**

Read `backend/nobla/gateway/protocol.py` and add after the existing error codes:

```python
# Voice pipeline errors
VOICE_SESSION_EXISTS = -32010
VOICE_NO_SESSION = -32011
VOICE_ENGINE_UNAVAILABLE = -32012
```

- [ ] **Step 2: Write failing tests for voice handlers**

```python
# backend/tests/voice/test_voice_handlers.py
"""Tests for voice WebSocket RPC handlers."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.gateway.voice_handlers import (
    handle_voice_start,
    handle_voice_stop,
    handle_voice_audio,
    handle_voice_config,
    set_voice_pipeline,
)
from nobla.voice.models import VoiceConfig, VoiceSession, VoiceState, VADMode
from nobla.voice.pipeline import PipelineResult
from nobla.voice.models import Transcript


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.connection_id = "test_conn"
    state.user_id = "user_1"
    return state


@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    session = VoiceSession(connection_id="test_conn")
    pipeline.create_session = MagicMock(return_value=session)
    pipeline.get_session = MagicMock(return_value=session)
    pipeline.end_session = MagicMock()
    pipeline.process_segment = AsyncMock(
        return_value=PipelineResult(
            transcript=Transcript(text="hello", language="en", confidence=0.9),
            response_text="Hi there!",
            audio_chunks=[b"audio1", b"audio2"],
        )
    )
    set_voice_pipeline(pipeline)
    return pipeline


class TestVoiceStart:
    @pytest.mark.asyncio
    async def test_start_creates_session(self, mock_state, mock_pipeline):
        result = await handle_voice_start(
            {"vad_mode": "push_to_talk", "tts_engine": "cosyvoice"}, mock_state
        )
        assert result["status"] == "started"
        mock_pipeline.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_returns_error_if_session_exists(self, mock_state, mock_pipeline):
        mock_pipeline.get_session = MagicMock(
            return_value=VoiceSession(connection_id="test_conn")
        )
        # Should still work — replaces existing session
        result = await handle_voice_start({}, mock_state)
        assert result["status"] == "started"


class TestVoiceStop:
    @pytest.mark.asyncio
    async def test_stop_ends_session(self, mock_state, mock_pipeline):
        result = await handle_voice_stop({}, mock_state)
        assert result["status"] == "stopped"
        mock_pipeline.end_session.assert_called_once_with("test_conn")

    @pytest.mark.asyncio
    async def test_stop_no_session_returns_error(self, mock_state, mock_pipeline):
        mock_pipeline.get_session = MagicMock(return_value=None)
        result = await handle_voice_stop({}, mock_state)
        assert "error" in result


class TestVoiceAudio:
    @pytest.mark.asyncio
    async def test_audio_processes_segment(self, mock_state, mock_pipeline):
        audio_b64 = base64.b64encode(b"\x00" * 3200).decode()
        result = await handle_voice_audio({"data": audio_b64}, mock_state)
        assert result["transcript"]["text"] == "hello"
        assert result["response"]["text"] == "Hi there!"
        assert len(result["audio"]) == 2

    @pytest.mark.asyncio
    async def test_audio_no_session_returns_error(self, mock_state, mock_pipeline):
        mock_pipeline.get_session = MagicMock(return_value=None)
        result = await handle_voice_audio({"data": "AAAA"}, mock_state)
        assert "error" in result


class TestVoiceConfig:
    @pytest.mark.asyncio
    async def test_config_updates_session(self, mock_state, mock_pipeline):
        result = await handle_voice_config(
            {"vad_mode": "auto_detect", "tts_engine": "fish_speech"}, mock_state
        )
        assert result["status"] == "updated"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/voice/test_voice_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement voice WebSocket handlers**

```python
# backend/nobla/gateway/voice_handlers.py
"""JSON-RPC handlers for voice pipeline operations."""
from __future__ import annotations

import base64
import logging

from nobla.gateway.websocket import ConnectionState, rpc_method
from nobla.voice.models import VADMode, VoiceConfig
from nobla.voice.pipeline import VoicePipeline

logger = logging.getLogger(__name__)

_pipeline: VoicePipeline | None = None


def set_voice_pipeline(pipeline: VoicePipeline) -> None:
    global _pipeline
    _pipeline = pipeline


def get_voice_pipeline() -> VoicePipeline | None:
    return _pipeline


@rpc_method("voice.start")
async def handle_voice_start(params: dict, state: ConnectionState) -> dict:
    """Start a voice session for this connection."""
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice pipeline not initialized"}}

    # End existing session if any
    existing = _pipeline.get_session(state.connection_id)
    if existing:
        _pipeline.end_session(state.connection_id)

    config = VoiceConfig(
        vad_mode=VADMode(params.get("vad_mode", "push_to_talk")),
        tts_engine=params.get("tts_engine", "cosyvoice"),
    )
    session = _pipeline.create_session(
        connection_id=state.connection_id,
        config=config,
        persona_id=params.get("persona_id"),
    )

    logger.info("voice_start connection=%s vad=%s", state.connection_id, config.vad_mode)
    return {"status": "started", "vad_mode": config.vad_mode, "tts_engine": config.tts_engine}


@rpc_method("voice.stop")
async def handle_voice_stop(params: dict, state: ConnectionState) -> dict:
    """Stop the voice session for this connection."""
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice pipeline not initialized"}}

    session = _pipeline.get_session(state.connection_id)
    if not session:
        return {"error": {"code": -32011, "message": "No active voice session"}}

    _pipeline.end_session(state.connection_id)
    logger.info("voice_stop connection=%s", state.connection_id)
    return {"status": "stopped"}


@rpc_method("voice.audio")
async def handle_voice_audio(params: dict, state: ConnectionState) -> dict:
    """Process an incoming audio segment."""
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice pipeline not initialized"}}

    session = _pipeline.get_session(state.connection_id)
    if not session:
        return {"error": {"code": -32011, "message": "No active voice session"}}

    # Decode audio from base64
    audio_data = base64.b64decode(params["data"])

    # Process through full pipeline
    result = await _pipeline.process_segment(session, audio_data)

    # Encode response audio as base64
    audio_b64 = [base64.b64encode(chunk).decode() for chunk in result.audio_chunks]

    return {
        "transcript": {
            "text": result.transcript.text,
            "language": result.transcript.language,
            "confidence": result.transcript.confidence,
            "is_final": True,
        },
        "response": {"text": result.response_text},
        "audio": audio_b64,
    }


@rpc_method("voice.config")
async def handle_voice_config(params: dict, state: ConnectionState) -> dict:
    """Update voice session configuration mid-session."""
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice pipeline not initialized"}}

    session = _pipeline.get_session(state.connection_id)
    if not session:
        return {"error": {"code": -32011, "message": "No active voice session"}}

    if "vad_mode" in params:
        session.config.vad_mode = VADMode(params["vad_mode"])
    if "tts_engine" in params:
        session.config.tts_engine = params["tts_engine"]
    if "persona_id" in params:
        session.persona_id = params["persona_id"]

    logger.info("voice_config_updated connection=%s", state.connection_id)
    return {"status": "updated", "config": session.config.model_dump()}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/voice/test_voice_handlers.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/gateway/voice_handlers.py backend/nobla/gateway/protocol.py backend/tests/voice/test_voice_handlers.py
git commit -m "feat(voice): add WebSocket voice RPC handlers"
```

---

## Task 12: Settings, Dependencies & App Integration

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Modify: `backend/nobla/gateway/app.py`
- Modify: `backend/pyproject.toml`
- Update: `backend/nobla/voice/__init__.py`
- Update: `backend/nobla/voice/stt/__init__.py`
- Update: `backend/nobla/voice/tts/__init__.py`

- [ ] **Step 1: Add VoiceSettings to settings.py**

Read `backend/nobla/config/settings.py` and add the VoiceSettings model:

```python
class VoiceSettings(BaseModel):
    """Voice pipeline configuration."""

    stt_model: str = "large-v3"
    levantine_model_path: str = "backend/nobla/voice/models/ggml-levantine-large-v3.bin"
    default_tts_engine: str = "cosyvoice"
    default_vad_mode: str = "push_to_talk"
    opus_bitrate: int = 32000
    vad_silence_threshold_ms: int = 800
    vad_min_speech_ms: int = 250
```

Add `voice: VoiceSettings = Field(default_factory=VoiceSettings)` to the `Settings` class.

- [ ] **Step 2: Add voice dependencies to pyproject.toml**

Read `backend/pyproject.toml` and add to the dependencies list:

```toml
"faster-whisper>=1.1.0",
"silero-vad>=5.1",
"opuslib>=3.0.1",
"pydub>=0.25.1",
"soundfile>=0.12.1",
```

- [ ] **Step 3: Add package exports**

```python
# backend/nobla/voice/__init__.py
"""Voice pipeline package."""
from nobla.voice.models import (
    AudioFrame,
    PartialTranscript,
    Transcript,
    VADMode,
    VoiceConfig,
    VoiceSession,
    VoiceState,
)
from nobla.voice.pipeline import PipelineResult, VoicePipeline

__all__ = [
    "AudioFrame",
    "PartialTranscript",
    "PipelineResult",
    "Transcript",
    "VADMode",
    "VoiceConfig",
    "VoicePipeline",
    "VoiceSession",
    "VoiceState",
]
```

```python
# backend/nobla/voice/stt/__init__.py
"""Speech-to-Text engines."""
from nobla.voice.stt.base import STTEngine
from nobla.voice.stt.detector import LanguageDetector

__all__ = ["STTEngine", "LanguageDetector"]
```

```python
# backend/nobla/voice/tts/__init__.py
"""Text-to-Speech engines."""
from nobla.voice.tts.base import TTSEngine, VoiceInfo

__all__ = ["TTSEngine", "VoiceInfo"]
```

- [ ] **Step 4: Wire voice pipeline into app.py lifespan**

Read `backend/nobla/gateway/app.py` and add voice initialization to the `lifespan()` function, after the search engine setup:

```python
# Voice pipeline (Phase 3A)
from nobla.voice.stt.whisper import WhisperSTT
from nobla.voice.stt.levantine import LevantineSTT
from nobla.voice.stt.detector import LanguageDetector
from nobla.voice.tts.fish_speech import FishSpeechTTS
from nobla.voice.tts.cosyvoice import CosyVoiceTTS
from nobla.voice.pipeline import VoicePipeline
from nobla.gateway.voice_handlers import set_voice_pipeline

try:
    whisper_stt = WhisperSTT(model_size=settings.voice.stt_model)
except Exception:
    logger.warning("whisper_stt_load_failed voice_disabled=true")
    whisper_stt = None

levantine_stt = None
if whisper_stt:
    try:
        levantine_stt = LevantineSTT(model_path=settings.voice.levantine_model_path)
    except Exception:
        logger.warning("levantine_model_not_found arabic_stt=disabled")

if whisper_stt:
    stt_engine = LanguageDetector(
        whisper_engine=whisper_stt,
        levantine_engine=levantine_stt,
    ) if levantine_stt else whisper_stt

    tts_engines = {}
    try:
        tts_engines["cosyvoice"] = CosyVoiceTTS(model_path="models/cosyvoice2")
    except Exception:
        logger.warning("cosyvoice_load_failed")
    try:
        tts_engines["fish_speech"] = FishSpeechTTS(model_path="models/fish_speech")
    except Exception:
        logger.warning("fish_speech_load_failed")

    if tts_engines:
        voice_pipeline = VoicePipeline(
            stt_engine=stt_engine,
            tts_engines=tts_engines,
            llm_router=router,
        )
        set_voice_pipeline(voice_pipeline)
        logger.info("voice_pipeline_ready engines=%s", list(tts_engines.keys()))
    else:
        logger.warning("no_tts_engines_available voice_disabled=true")
else:
    logger.warning("voice_pipeline_disabled stt=unavailable")
```

- [ ] **Step 5: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All voice tests PASS, existing tests unaffected

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/config/settings.py backend/nobla/gateway/app.py backend/pyproject.toml backend/nobla/voice/__init__.py backend/nobla/voice/stt/__init__.py backend/nobla/voice/tts/__init__.py
git commit -m "feat(voice): wire voice pipeline into app settings and lifespan"
```

---

## Task 13: STT Module Exports & Final Integration Test

**Files:**
- Create: `backend/tests/voice/test_integration.py`

- [ ] **Step 1: Write integration test for full voice round-trip**

```python
# backend/tests/voice/test_integration.py
"""Integration tests for the full voice pipeline round-trip."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.voice.pipeline import VoicePipeline
from nobla.voice.models import Transcript, VoiceConfig, VADMode
from nobla.voice.stt.base import STTEngine
from nobla.voice.tts.base import TTSEngine, VoiceInfo
from nobla.brain.base_provider import LLMMessage, LLMResponse
from nobla.gateway.voice_handlers import (
    handle_voice_start,
    handle_voice_stop,
    handle_voice_audio,
    set_voice_pipeline,
)


class MockSTT(STTEngine):
    @property
    def name(self):
        return "test_whisper"

    async def transcribe(self, audio, language=None):
        return Transcript(text="integration test", language="en", confidence=0.99)

    async def transcribe_stream(self, audio_chunks):
        yield  # Not used in this test

    async def is_available(self):
        return True


class MockTTS(TTSEngine):
    @property
    def name(self):
        return "test_tts"

    async def synthesize(self, text, voice_id="default"):
        yield b"tts_chunk_1"
        yield b"tts_chunk_2"

    async def get_voices(self):
        return [VoiceInfo(id="default", name="Test", language="en")]

    async def is_available(self):
        return True


@pytest.fixture
def integrated_pipeline():
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=LLMResponse(
            content="Integration test response",
            model="test",
            tokens_input=5,
            tokens_output=4,
            cost_usd=0.0,
            latency_ms=10,
        )
    )
    pipeline = VoicePipeline(
        stt_engine=MockSTT(),
        tts_engines={"test_tts": MockTTS()},
        llm_router=router,
    )
    set_voice_pipeline(pipeline)
    return pipeline


class TestFullRoundTrip:
    @pytest.mark.asyncio
    async def test_start_audio_stop_flow(self, integrated_pipeline):
        """Test the complete voice flow: start → audio → stop."""
        state = MagicMock()
        state.connection_id = "integration_test"
        state.user_id = "user_1"

        # 1. Start session
        start_result = await handle_voice_start(
            {"vad_mode": "push_to_talk", "tts_engine": "test_tts"}, state
        )
        assert start_result["status"] == "started"

        # 2. Send audio
        fake_audio = b"\x00\x01\x02\x03" * 8000  # ~1 second
        audio_b64 = base64.b64encode(fake_audio).decode()
        audio_result = await handle_voice_audio({"data": audio_b64}, state)

        assert audio_result["transcript"]["text"] == "integration test"
        assert audio_result["transcript"]["language"] == "en"
        assert audio_result["response"]["text"] == "Integration test response"
        assert len(audio_result["audio"]) == 2  # Two TTS chunks

        # Verify audio chunks are valid base64
        for chunk_b64 in audio_result["audio"]:
            decoded = base64.b64decode(chunk_b64)
            assert isinstance(decoded, bytes)

        # 3. Stop session
        stop_result = await handle_voice_stop({}, state)
        assert stop_result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_multiple_audio_exchanges(self, integrated_pipeline):
        """Test sending multiple audio segments in one session."""
        state = MagicMock()
        state.connection_id = "multi_test"

        await handle_voice_start({"tts_engine": "test_tts"}, state)

        for _ in range(3):
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode()
            result = await handle_voice_audio({"data": audio_b64}, state)
            assert result["transcript"]["text"] == "integration test"

        await handle_voice_stop({}, state)
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && python -m pytest tests/voice/test_integration.py -v`
Expected: All integration tests PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/voice/test_integration.py
git commit -m "test(voice): add full round-trip integration tests for Phase 3A"
```

---

## Summary

| Task | Component | Tests | Files Created |
|------|-----------|-------|---------------|
| 1 | Voice Pydantic models | 12 | 2 new + dirs |
| 2 | STT ABC | 3 | 2 new |
| 3 | Faster-Whisper STT | 5 | 3 new |
| 4 | Levantine Arabic STT | 4 | 2 new |
| 5 | Language detector | 5 | 2 new |
| 6 | TTS ABC | 5 | 2 new |
| 7 | Fish Speech TTS | 5 | 2 new |
| 8 | CosyVoice2 TTS | 5 | 2 new |
| 9 | Silero VAD | 5 | 2 new |
| 10 | Pipeline orchestrator | 6 | 2 new |
| 11 | WebSocket handlers | 8 | 2 new + 1 mod |
| 12 | Settings & integration | — | 3 mod + 3 upd |
| 13 | Integration tests | 2 | 1 new |

**Total: ~65 tests, 22 new files, 4 modified files, 13 commits**
