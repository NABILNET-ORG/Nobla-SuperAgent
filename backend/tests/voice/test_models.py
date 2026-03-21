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
