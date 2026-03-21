"""JSON-RPC handlers for voice pipeline operations.

Registers voice.start, voice.stop, voice.audio, and voice.config methods
with the WebSocket dispatcher. Import this module during app startup to
activate the handlers.
"""
from __future__ import annotations

import base64
import logging

from nobla.gateway.websocket import ConnectionState, rpc_method
from nobla.voice.models import VADMode, VoiceConfig
from nobla.voice.pipeline import VoicePipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level pipeline accessor (set during app lifespan)
# ---------------------------------------------------------------------------

_pipeline: VoicePipeline | None = None


def set_voice_pipeline(pipeline: VoicePipeline) -> None:
    """Register the shared VoicePipeline instance used by all handlers."""
    global _pipeline
    _pipeline = pipeline


def get_voice_pipeline() -> VoicePipeline | None:
    """Return the currently registered VoicePipeline, or None if not set."""
    return _pipeline


# ---------------------------------------------------------------------------
# RPC Handlers
# ---------------------------------------------------------------------------


@rpc_method("voice.start")
async def handle_voice_start(params: dict, state: ConnectionState) -> dict:
    """Start a voice session for the current connection.

    If a session already exists it is replaced cleanly so the client can
    restart without an explicit voice.stop first.

    Params:
        vad_mode    (str, optional) — "push_to_talk" | "auto_detect" | "walkie_talkie"
        tts_engine  (str, optional) — TTS engine name, default "cosyvoice"
        persona_id  (str, optional) — persona to use for TTS voice
    """
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice engine unavailable"}}

    # Replace any existing session so the client can restart cleanly.
    if _pipeline.get_session(state.connection_id):
        _pipeline.end_session(state.connection_id)

    config = VoiceConfig(
        vad_mode=VADMode(params.get("vad_mode", VADMode.PUSH_TO_TALK.value)),
        tts_engine=params.get("tts_engine", "cosyvoice"),
    )
    _pipeline.create_session(
        connection_id=state.connection_id,
        config=config,
        persona_id=params.get("persona_id"),
    )

    return {
        "status": "started",
        "vad_mode": config.vad_mode.value,
        "tts_engine": config.tts_engine,
    }


@rpc_method("voice.stop")
async def handle_voice_stop(params: dict, state: ConnectionState) -> dict:
    """End the active voice session for the current connection.

    Returns an inline error object (not a raised exception) when there is no
    session to stop, so the client can handle it gracefully.
    """
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice engine unavailable"}}

    if not _pipeline.get_session(state.connection_id):
        return {"error": {"code": -32011, "message": "No active voice session"}}

    _pipeline.end_session(state.connection_id)
    return {"status": "stopped"}


@rpc_method("voice.audio")
async def handle_voice_audio(params: dict, state: ConnectionState) -> dict:
    """Process a base64-encoded audio segment through the full voice pipeline.

    Params:
        data  (str, required) — base64-encoded raw PCM audio bytes

    Returns a dict containing:
        transcript — STT result (text, language, confidence, is_final)
        response   — LLM reply (text)
        audio      — list of base64-encoded TTS audio chunks
    """
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice engine unavailable"}}

    session = _pipeline.get_session(state.connection_id)
    if not session:
        return {"error": {"code": -32011, "message": "No active voice session"}}

    if "data" not in params:
        return {"error": {"code": -32602, "message": "Missing required 'data' param"}}

    try:
        audio_data = base64.b64decode(params["data"])
    except Exception:
        return {"error": {"code": -32602, "message": "Invalid base64 audio data"}}

    try:
        # Step 1: STT + emotion detection (pipeline)
        transcript, emotion_result = await _pipeline.transcribe_and_detect(
            session, audio_data
        )

        # Step 2: Persona-aware LLM routing (service)
        from nobla.persona.service import resolve_and_route, get_persona_manager
        from nobla.brain.base_provider import LLMMessage

        llm_messages = [LLMMessage(role="user", content=transcript.text)]

        if get_persona_manager() is not None:
            response, persona_ctx = await resolve_and_route(
                messages=llm_messages,
                session_id=state.connection_id,
                user_id=state.user_id or "",
                emotion=emotion_result,
            )
        else:
            from nobla.gateway.websocket import get_router
            router = get_router()
            response = await router.route(llm_messages)
            persona_ctx = None

        # Step 3: TTS with persona voice_config
        tts_engine_name = session.config.tts_engine
        if persona_ctx and persona_ctx.voice_config:
            tts_engine_name = persona_ctx.voice_config.get(
                "engine", session.config.tts_engine
            )
        tts_engine = await _pipeline._resolve_tts(tts_engine_name)
        audio_chunks: list[bytes] = []
        async for chunk in tts_engine.synthesize(response.content):
            audio_chunks.append(chunk)

    except Exception as exc:
        logger.exception("voice_audio_processing_failed connection=%s", state.connection_id)
        return {"error": {"code": -32012, "message": f"Voice processing failed: {exc}"}}

    audio_b64 = [base64.b64encode(chunk).decode() for chunk in audio_chunks]

    return {
        "transcript": {
            "text": transcript.text,
            "language": transcript.language,
            "confidence": transcript.confidence,
            "is_final": True,
        },
        "response": {"text": response.content},
        "audio": audio_b64,
        "emotion": emotion_result.model_dump() if emotion_result else None,
    }


@rpc_method("voice.config")
async def handle_voice_config(params: dict, state: ConnectionState) -> dict:
    """Update voice session configuration without restarting the session.

    Params (all optional — only provided fields are updated):
        vad_mode   (str) — new VAD mode
        tts_engine (str) — new TTS engine name
        persona_id (str) — new persona for TTS voice
    """
    if not _pipeline:
        return {"error": {"code": -32012, "message": "Voice engine unavailable"}}

    session = _pipeline.get_session(state.connection_id)
    if not session:
        return {"error": {"code": -32011, "message": "No active voice session"}}

    if "vad_mode" in params:
        session.config.vad_mode = VADMode(params["vad_mode"])
    if "tts_engine" in params:
        session.config.tts_engine = params["tts_engine"]
    if "persona_id" in params:
        session.persona_id = params["persona_id"]

    return {"status": "updated", "config": session.config.model_dump()}
