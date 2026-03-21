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
