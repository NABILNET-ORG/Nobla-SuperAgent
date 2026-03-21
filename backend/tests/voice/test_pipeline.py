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

        result = await pipeline.process_segment(session, b"\x00" * 32000)

        stt.transcribe.assert_awaited_once()
        router.route.assert_awaited_once()
        call_messages = router.route.call_args[0][0]
        assert any("hello world" in msg.content for msg in call_messages)

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
