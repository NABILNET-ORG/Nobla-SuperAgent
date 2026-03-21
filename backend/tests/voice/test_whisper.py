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
