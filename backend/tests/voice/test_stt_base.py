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
