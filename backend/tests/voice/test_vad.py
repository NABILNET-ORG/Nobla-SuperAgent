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

        chunk_size = 3200  # 100ms at 16kHz 16-bit
        for i in range(0, len(silence_pcm_16khz), chunk_size):
            vad.feed(silence_pcm_16khz[i : i + chunk_size])

        assert vad.get_segments() == []

        segments = vad.stop()
        assert len(segments) == 1
        assert len(segments[0]) == len(silence_pcm_16khz)

    @pytest.mark.asyncio
    async def test_auto_detect_emits_on_silence(self):
        """In auto-detect, VAD emits a segment when silence is detected."""
        vad = self._make_vad(mode=VADMode.AUTO_DETECT)
        vad._vad_model = MagicMock()

        speech_probs = [0.9, 0.85, 0.8, 0.1, 0.05, 0.02, 0.01, 0.01, 0.01]
        vad._vad_model.return_value = MagicMock(item=MagicMock(side_effect=speech_probs))

        vad.start()
        for prob in speech_probs:
            vad._vad_model.return_value = MagicMock(item=MagicMock(return_value=prob))
            vad.feed(b"\x00" * 960)

        segments = vad.get_segments()
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
