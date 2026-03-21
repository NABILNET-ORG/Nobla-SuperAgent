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
