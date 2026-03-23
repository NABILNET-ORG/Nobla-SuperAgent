"""Integration tests for the full voice pipeline round-trip.

Covers the complete path: voice.start -> voice.audio -> voice.stop
using lightweight mock STT/TTS engines and a mock LLM router, exercising
the real VoicePipeline orchestrator and the real RPC handler functions.
"""
from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import pytest
from unittest.mock import AsyncMock, MagicMock

from nobla.brain.base_provider import LLMMessage, LLMResponse
from nobla.gateway.voice_handlers import (
    handle_voice_start,
    handle_voice_stop,
    handle_voice_audio,
    set_voice_pipeline,
)
from nobla.gateway.websocket import set_router
from nobla.voice.models import PartialTranscript, Transcript, VoiceConfig, VADMode
from nobla.voice.pipeline import VoicePipeline
from nobla.voice.stt.base import STTEngine
from nobla.voice.tts.base import TTSEngine, VoiceInfo


# ---------------------------------------------------------------------------
# Minimal concrete mock engines
# ---------------------------------------------------------------------------


class MockSTT(STTEngine):
    """Minimal STT engine that always returns a fixed transcript."""

    @property
    def name(self) -> str:
        return "test_whisper"

    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        return Transcript(text="integration test", language="en", confidence=0.99)

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[PartialTranscript]:
        # Not used in handler-level integration tests but required by the ABC.
        yield PartialTranscript(text="integration test", is_final=True)  # type: ignore[misc]

    async def is_available(self) -> bool:
        return True


class MockTTS(TTSEngine):
    """Minimal TTS engine that yields two fixed audio byte chunks."""

    @property
    def name(self) -> str:
        return "test_tts"

    async def synthesize(
        self, text: str, voice_id: str = "default"
    ) -> AsyncIterator[bytes]:
        yield b"tts_chunk_1"
        yield b"tts_chunk_2"

    async def get_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="default", name="Test Voice", language="en")]

    async def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_router() -> AsyncMock:
    """Return a mock LLM router whose .route() returns a fixed LLMResponse."""
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=LLMResponse(
            content="Integration test response",
            model="test-model",
            tokens_input=5,
            tokens_output=4,
            cost_usd=0.0,
            latency_ms=10,
        )
    )
    return router


def _make_state(connection_id: str = "conn_integration", user_id: str = "user_1") -> MagicMock:
    """Return a minimal ConnectionState stand-in."""
    state = MagicMock()
    state.connection_id = connection_id
    state.user_id = user_id
    return state


def _encode_audio(raw: bytes) -> str:
    """Base64-encode raw PCM bytes the same way a real client would."""
    return base64.b64encode(raw).decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_pipeline():
    """Ensure the module-level pipeline and router are cleared after every test."""
    yield
    set_voice_pipeline(None)  # type: ignore[arg-type]
    set_router(None)  # type: ignore[arg-type]


@pytest.fixture
def pipeline() -> VoicePipeline:
    """Build and register an integrated VoicePipeline with mock engines."""
    mock_router = _make_llm_router()
    p = VoicePipeline(
        stt_engine=MockSTT(),
        tts_engines={"test_tts": MockTTS()},
        llm_router=mock_router,
    )
    set_voice_pipeline(p)
    # Phase 3B: voice handler fallback path uses get_router() from websocket module
    set_router(mock_router)
    return p


# ---------------------------------------------------------------------------
# Tests: full round-trip
# ---------------------------------------------------------------------------


class TestFullRoundTrip:
    """Tests that exercise the complete voice.start -> voice.audio -> voice.stop flow."""

    @pytest.mark.asyncio
    async def test_start_audio_stop_flow(self, pipeline: VoicePipeline) -> None:
        """Happy-path: start session, process audio, stop session."""
        state = _make_state("conn_round_trip")

        # 1. Start session
        start_result = await handle_voice_start(
            {"vad_mode": "push_to_talk", "tts_engine": "test_tts"}, state
        )
        assert start_result["status"] == "started"
        assert start_result["vad_mode"] == "push_to_talk"
        assert start_result["tts_engine"] == "test_tts"

        # 2. Send audio
        fake_pcm = b"\x00\x01\x02\x03" * 8000  # ~128 KB of dummy PCM
        audio_result = await handle_voice_audio({"data": _encode_audio(fake_pcm)}, state)

        assert "error" not in audio_result

        # Transcript section
        transcript = audio_result["transcript"]
        assert transcript["text"] == "integration test"
        assert transcript["language"] == "en"
        assert transcript["confidence"] == pytest.approx(0.99)
        assert transcript["is_final"] is True

        # LLM response section
        assert audio_result["response"]["text"] == "Integration test response"

        # TTS audio section — two chunks expected from MockTTS
        audio_chunks = audio_result["audio"]
        assert len(audio_chunks) == 2
        assert base64.b64decode(audio_chunks[0]) == b"tts_chunk_1"
        assert base64.b64decode(audio_chunks[1]) == b"tts_chunk_2"

        # 3. Stop session
        stop_result = await handle_voice_stop({}, state)
        assert stop_result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_multiple_audio_exchanges(self, pipeline: VoicePipeline) -> None:
        """Multiple audio segments in a single session all succeed."""
        state = _make_state("conn_multi")

        await handle_voice_start({"tts_engine": "test_tts"}, state)

        for _ in range(3):
            result = await handle_voice_audio(
                {"data": _encode_audio(b"\x00" * 3200)}, state
            )
            assert "error" not in result
            assert result["transcript"]["text"] == "integration test"
            assert result["response"]["text"] == "Integration test response"
            assert len(result["audio"]) == 2

        stop_result = await handle_voice_stop({}, state)
        assert stop_result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_restart_session_without_explicit_stop(self, pipeline: VoicePipeline) -> None:
        """Calling voice.start again replaces the existing session cleanly."""
        state = _make_state("conn_restart")

        first = await handle_voice_start({"tts_engine": "test_tts"}, state)
        assert first["status"] == "started"

        # Start again without stopping — the handler should replace the session.
        second = await handle_voice_start({"tts_engine": "test_tts"}, state)
        assert second["status"] == "started"

        # Session should still be functional after the implicit restart.
        result = await handle_voice_audio(
            {"data": _encode_audio(b"\x00" * 3200)}, state
        )
        assert "error" not in result
        assert result["transcript"]["text"] == "integration test"

        await handle_voice_stop({}, state)

    @pytest.mark.asyncio
    async def test_vad_mode_default_is_push_to_talk(self, pipeline: VoicePipeline) -> None:
        """Omitting vad_mode in params defaults to push_to_talk."""
        state = _make_state("conn_vad_default")

        result = await handle_voice_start({"tts_engine": "test_tts"}, state)
        assert result["vad_mode"] == VADMode.PUSH_TO_TALK.value

        await handle_voice_stop({}, state)

    @pytest.mark.asyncio
    async def test_audio_base64_is_properly_round_tripped(self, pipeline: VoicePipeline) -> None:
        """Verify every TTS chunk is valid base64 that decodes to bytes."""
        state = _make_state("conn_b64")

        await handle_voice_start({"tts_engine": "test_tts"}, state)
        result = await handle_voice_audio(
            {"data": _encode_audio(b"\xff\xfe" * 1000)}, state
        )

        for chunk_b64 in result["audio"]:
            decoded = base64.b64decode(chunk_b64)
            assert isinstance(decoded, bytes)
            assert len(decoded) > 0

        await handle_voice_stop({}, state)


# ---------------------------------------------------------------------------
# Tests: error / edge cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    """Verify inline error objects are returned for invalid state transitions."""

    @pytest.mark.asyncio
    async def test_audio_without_start_returns_error(self, pipeline: VoicePipeline) -> None:
        """Sending audio without an active session returns an inline error."""
        state = _make_state("conn_no_session")
        result = await handle_voice_audio({"data": _encode_audio(b"\x00" * 100)}, state)
        assert "error" in result
        assert result["error"]["code"] == -32011

    @pytest.mark.asyncio
    async def test_stop_without_start_returns_error(self, pipeline: VoicePipeline) -> None:
        """Stopping with no active session returns an inline error."""
        state = _make_state("conn_no_start")
        result = await handle_voice_stop({}, state)
        assert "error" in result
        assert result["error"]["code"] == -32011

    @pytest.mark.asyncio
    async def test_handlers_with_no_pipeline_return_error(self) -> None:
        """All handlers return an inline error when no pipeline is registered."""
        # _reset_pipeline autouse fixture cleared the pipeline; don't register one.
        state = _make_state("conn_no_pipeline")

        for handler, params in [
            (handle_voice_start, {"tts_engine": "test_tts"}),
            (handle_voice_stop, {}),
            (handle_voice_audio, {"data": _encode_audio(b"\x00" * 100)}),
        ]:
            result = await handler(params, state)  # type: ignore[operator]
            assert "error" in result
            assert result["error"]["code"] == -32012

    @pytest.mark.asyncio
    async def test_independent_connections_are_isolated(self, pipeline: VoicePipeline) -> None:
        """Two different connection IDs maintain independent sessions."""
        state_a = _make_state("conn_a")
        state_b = _make_state("conn_b")

        await handle_voice_start({"tts_engine": "test_tts"}, state_a)
        # conn_b has no session yet — audio should fail for it.
        error = await handle_voice_audio(
            {"data": _encode_audio(b"\x00" * 100)}, state_b
        )
        assert "error" in error
        assert error["error"]["code"] == -32011

        # conn_a should still work fine.
        ok = await handle_voice_audio(
            {"data": _encode_audio(b"\x00" * 100)}, state_a
        )
        assert "error" not in ok

        await handle_voice_stop({}, state_a)
