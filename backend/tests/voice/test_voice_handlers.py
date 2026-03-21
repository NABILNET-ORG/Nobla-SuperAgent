"""Tests for voice WebSocket RPC handlers.

Covers:
  - Method registration in the global registry
  - voice.start — create session, replace existing session
  - voice.stop  — end session, no-session error
  - voice.audio — full pipeline round-trip, no-session error
  - voice.config — update session config mid-session
  - Pipeline-unavailable guard across all handlers
"""
from __future__ import annotations

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.gateway.websocket import ConnectionState, _method_registry

# Importing voice_handlers registers the four rpc methods as a side-effect.
import nobla.gateway.voice_handlers as vh  # noqa: F401
from nobla.gateway.voice_handlers import (
    get_voice_pipeline,
    handle_voice_audio,
    handle_voice_config,
    handle_voice_start,
    handle_voice_stop,
    set_voice_pipeline,
)
from nobla.voice.models import Transcript, VADMode, VoiceConfig, VoiceSession, VoiceState
from nobla.voice.pipeline import PipelineResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(connection_id: str = "test-conn") -> ConnectionState:
    state = ConnectionState()
    state.connection_id = connection_id
    state.user_id = "user-1"
    return state


def _make_pipeline(session: VoiceSession | None = None) -> MagicMock:
    """Build a MagicMock that looks like VoicePipeline."""
    pipeline = MagicMock()
    pipeline.get_session = MagicMock(return_value=session)
    pipeline.create_session = MagicMock(return_value=session or _make_session())
    pipeline.end_session = MagicMock()
    pipeline.process_segment = AsyncMock(
        return_value=PipelineResult(
            transcript=Transcript(text="hello", language="en", confidence=0.95),
            response_text="Hi there!",
            audio_chunks=[b"chunk1", b"chunk2"],
        )
    )
    return pipeline


def _make_session(connection_id: str = "test-conn") -> VoiceSession:
    return VoiceSession(
        connection_id=connection_id,
        config=VoiceConfig(),
        state=VoiceState.IDLE,
    )


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_voice_start_registered():
    assert "voice.start" in _method_registry


def test_voice_stop_registered():
    assert "voice.stop" in _method_registry


def test_voice_audio_registered():
    assert "voice.audio" in _method_registry


def test_voice_config_registered():
    assert "voice.config" in _method_registry


# ---------------------------------------------------------------------------
# voice.start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_start_creates_session():
    pipeline = _make_pipeline(session=None)
    # First call returns None (no existing), second returns the new session.
    pipeline.get_session = MagicMock(return_value=None)

    set_voice_pipeline(pipeline)
    state = _make_state()

    result = await handle_voice_start(
        {"vad_mode": "auto_detect", "tts_engine": "fish_speech"},
        state,
    )

    assert result["status"] == "started"
    assert result["vad_mode"] == "auto_detect"
    assert result["tts_engine"] == "fish_speech"
    pipeline.create_session.assert_called_once_with(
        connection_id="test-conn",
        config=VoiceConfig(vad_mode=VADMode.AUTO_DETECT, tts_engine="fish_speech"),
        persona_id=None,
    )


@pytest.mark.asyncio
async def test_voice_start_replaces_existing_session():
    """voice.start on a connection that already has a session ends the old one."""
    existing_session = _make_session()
    pipeline = _make_pipeline(session=existing_session)

    set_voice_pipeline(pipeline)
    state = _make_state()

    result = await handle_voice_start({}, state)

    # Old session must be ended before the new one is created.
    pipeline.end_session.assert_called_once_with("test-conn")
    pipeline.create_session.assert_called_once()
    assert result["status"] == "started"


@pytest.mark.asyncio
async def test_voice_start_no_pipeline():
    set_voice_pipeline(None)
    result = await handle_voice_start({}, _make_state())
    assert "error" in result
    assert result["error"]["code"] == -32012


@pytest.mark.asyncio
async def test_voice_start_defaults():
    """Omitted params should default to push_to_talk / cosyvoice."""
    pipeline = _make_pipeline(session=None)
    pipeline.get_session = MagicMock(return_value=None)
    set_voice_pipeline(pipeline)

    result = await handle_voice_start({}, _make_state())

    assert result["vad_mode"] == VADMode.PUSH_TO_TALK.value
    assert result["tts_engine"] == "cosyvoice"


# ---------------------------------------------------------------------------
# voice.stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_stop_ends_session():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    result = await handle_voice_stop({}, _make_state())

    assert result["status"] == "stopped"
    pipeline.end_session.assert_called_once_with("test-conn")


@pytest.mark.asyncio
async def test_voice_stop_no_session_returns_error():
    pipeline = _make_pipeline(session=None)
    set_voice_pipeline(pipeline)

    result = await handle_voice_stop({}, _make_state())

    assert "error" in result
    assert result["error"]["code"] == -32011
    pipeline.end_session.assert_not_called()


@pytest.mark.asyncio
async def test_voice_stop_no_pipeline():
    set_voice_pipeline(None)
    result = await handle_voice_stop({}, _make_state())
    assert "error" in result
    assert result["error"]["code"] == -32012


# ---------------------------------------------------------------------------
# voice.audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_audio_full_round_trip():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    raw_audio = b"\x00" * 320
    encoded = base64.b64encode(raw_audio).decode()

    result = await handle_voice_audio({"data": encoded}, _make_state())

    pipeline.process_segment.assert_awaited_once_with(session, raw_audio)

    assert result["transcript"]["text"] == "hello"
    assert result["transcript"]["language"] == "en"
    assert result["transcript"]["confidence"] == pytest.approx(0.95)
    assert result["transcript"]["is_final"] is True
    assert result["response"]["text"] == "Hi there!"
    assert len(result["audio"]) == 2
    # Verify chunks are valid base64 that decode back to originals.
    assert base64.b64decode(result["audio"][0]) == b"chunk1"
    assert base64.b64decode(result["audio"][1]) == b"chunk2"


@pytest.mark.asyncio
async def test_voice_audio_no_session_returns_error():
    pipeline = _make_pipeline(session=None)
    set_voice_pipeline(pipeline)

    encoded = base64.b64encode(b"\x00" * 32).decode()
    result = await handle_voice_audio({"data": encoded}, _make_state())

    assert "error" in result
    assert result["error"]["code"] == -32011
    pipeline.process_segment.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_audio_no_pipeline():
    set_voice_pipeline(None)
    encoded = base64.b64encode(b"\x00" * 32).decode()
    result = await handle_voice_audio({"data": encoded}, _make_state())
    assert "error" in result
    assert result["error"]["code"] == -32012


# ---------------------------------------------------------------------------
# voice.config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_config_updates_vad_mode():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    result = await handle_voice_config({"vad_mode": "auto_detect"}, _make_state())

    assert result["status"] == "updated"
    assert session.config.vad_mode == VADMode.AUTO_DETECT


@pytest.mark.asyncio
async def test_voice_config_updates_tts_engine():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    result = await handle_voice_config({"tts_engine": "fish_speech"}, _make_state())

    assert result["status"] == "updated"
    assert session.config.tts_engine == "fish_speech"


@pytest.mark.asyncio
async def test_voice_config_updates_persona_id():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    result = await handle_voice_config({"persona_id": "persona-42"}, _make_state())

    assert result["status"] == "updated"
    assert session.persona_id == "persona-42"


@pytest.mark.asyncio
async def test_voice_config_returns_full_config():
    session = _make_session()
    pipeline = _make_pipeline(session=session)
    set_voice_pipeline(pipeline)

    result = await handle_voice_config({}, _make_state())

    assert "config" in result
    assert "vad_mode" in result["config"]
    assert "tts_engine" in result["config"]


@pytest.mark.asyncio
async def test_voice_config_no_session_returns_error():
    pipeline = _make_pipeline(session=None)
    set_voice_pipeline(pipeline)

    result = await handle_voice_config({"vad_mode": "auto_detect"}, _make_state())

    assert "error" in result
    assert result["error"]["code"] == -32011


@pytest.mark.asyncio
async def test_voice_config_no_pipeline():
    set_voice_pipeline(None)
    result = await handle_voice_config({"vad_mode": "auto_detect"}, _make_state())
    assert "error" in result
    assert result["error"]["code"] == -32012


# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------


def test_set_get_voice_pipeline_roundtrip():
    pipeline = _make_pipeline()
    set_voice_pipeline(pipeline)
    assert get_voice_pipeline() is pipeline


def test_set_voice_pipeline_none():
    set_voice_pipeline(None)
    assert get_voice_pipeline() is None
