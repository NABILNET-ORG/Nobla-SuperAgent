"""Tests for PersonaPlex TTS integration."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from nobla.config.settings import PersonaPlexSettings, Settings


class TestPersonaPlexSettings:
    def test_defaults(self):
        s = PersonaPlexSettings()
        assert s.enabled is False
        assert s.server_url == "http://localhost:8880"
        assert s.timeout == 30.0
        assert s.cpu_offload is False

    def test_settings_has_personaplex(self):
        settings = Settings()
        assert hasattr(settings, "personaplex")
        assert isinstance(settings.personaplex, PersonaPlexSettings)
        assert settings.personaplex.enabled is False


class TestPersonaPlexTTS:
    @pytest.fixture
    def engine(self, tmp_path):
        from nobla.voice.tts.personaplex import PersonaPlexTTS

        return PersonaPlexTTS(
            server_url="http://localhost:8880",
            timeout=5.0,
            voice_prompts_dir=str(tmp_path),
        )

    def test_name(self, engine):
        assert engine.name == "personaplex"

    async def test_is_available_when_server_up(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            assert await engine.is_available() is True

    async def test_is_available_when_server_down(self, engine):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("refused"),
        ):
            assert await engine.is_available() is False

    async def test_get_voices(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "default", "name": "Default", "language": "en"}
        ]
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            voices = await engine.get_voices()
            assert len(voices) == 1
            assert voices[0].id == "default"

    async def test_synthesize_streams_audio(self, engine):
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter(**kwargs):
            for c in chunks:
                yield c

        mock_response.aiter_bytes = mock_aiter
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.stream", return_value=mock_response):
            result = []
            async for chunk in engine.synthesize("Hello world"):
                result.append(chunk)
            assert result == chunks

    async def test_synthesize_with_voice_prompt(self, engine, tmp_path):
        # Create a fake voice prompt file
        prompt_file = tmp_path / "custom.wav"
        prompt_file.write_bytes(b"fake_audio")

        chunks = [b"audio_data"]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter(**kwargs):
            for c in chunks:
                yield c

        mock_response.aiter_bytes = mock_aiter
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.stream", return_value=mock_response):
            result = []
            async for chunk in engine.synthesize("Hello", voice_id="custom.wav"):
                result.append(chunk)
            assert result == chunks

    async def test_synthesize_missing_voice_prompt_uses_default(self, engine):
        chunks = [b"audio"]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter(**kwargs):
            for c in chunks:
                yield c

        mock_response.aiter_bytes = mock_aiter
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.stream", return_value=mock_response):
            result = []
            async for chunk in engine.synthesize(
                "Hello", voice_id="nonexistent.wav"
            ):
                result.append(chunk)
            assert result == chunks  # still works, just no voice prompt

    async def test_is_available_caches_briefly(self, engine):
        """Health check should not hit server on every call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_get:
            assert await engine.is_available() is True
            assert await engine.is_available() is True
            # Only one actual HTTP call due to brief caching
            assert mock_get.await_count == 1
