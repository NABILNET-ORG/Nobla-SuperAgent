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
