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
