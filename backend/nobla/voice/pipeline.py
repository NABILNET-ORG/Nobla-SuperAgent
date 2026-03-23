"""Voice pipeline orchestrator — routes audio through STT -> LLM -> TTS."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nobla.brain.base_provider import LLMMessage
from nobla.voice.models import Transcript, VoiceConfig, VoiceSession, VoiceState
from nobla.voice.stt.base import STTEngine
from nobla.voice.tts.base import TTSEngine

if TYPE_CHECKING:
    from nobla.persona.models import EmotionResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of processing a voice segment through the full pipeline."""

    transcript: Transcript
    response_text: str
    audio_chunks: list[bytes] = field(default_factory=list)
    emotion_result: EmotionResult | None = None


class VoicePipeline:
    """Orchestrates voice processing: audio -> STT -> LLM -> TTS -> audio."""

    def __init__(
        self,
        stt_engine: STTEngine,
        tts_engines: dict[str, TTSEngine],
        llm_router: object,
        emotion_detector=None,
    ) -> None:
        self._stt = stt_engine
        self._tts_engines = tts_engines
        self._router = llm_router
        self._sessions: dict[str, VoiceSession] = {}
        self._emotion_detector = emotion_detector

    def create_session(
        self,
        connection_id: str,
        config: VoiceConfig | None = None,
        persona_id: str | None = None,
    ) -> VoiceSession:
        """Create a new voice session for a connection."""
        session = VoiceSession(
            connection_id=connection_id,
            config=config or VoiceConfig(),
            persona_id=persona_id,
        )
        self._sessions[connection_id] = session
        logger.info(
            "voice_session_created connection=%s vad=%s tts=%s",
            connection_id,
            session.config.vad_mode,
            session.config.tts_engine,
        )
        return session

    def get_session(self, connection_id: str) -> VoiceSession | None:
        return self._sessions.get(connection_id)

    def end_session(self, connection_id: str) -> None:
        session = self._sessions.pop(connection_id, None)
        if session:
            logger.info("voice_session_ended connection=%s", connection_id)

    async def transcribe_and_detect(
        self, session: VoiceSession, audio: bytes
    ) -> tuple[Transcript, EmotionResult | None]:
        """STT + emotion detection only. Handler controls LLM routing.

        Used by the persona-aware voice handler which needs to inject
        persona context between STT and LLM. Returns transcript and
        optional emotion result without touching LLM or TTS.
        """
        transcript = await self._stt.transcribe(audio)
        logger.info(
            "stt_complete text=%s lang=%s confidence=%.2f",
            transcript.text[:50],
            transcript.language,
            transcript.confidence,
        )

        emotion_result = None
        if self._emotion_detector is not None:
            try:
                emotion_result = await self._emotion_detector.detect(
                    session.connection_id, audio
                )
            except Exception:
                logger.warning("emotion_detection_failed", exc_info=True)

        return transcript, emotion_result

    async def process_segment(
        self,
        session: VoiceSession,
        audio: bytes,
        conversation_messages: list[LLMMessage] | None = None,
    ) -> PipelineResult:
        """Process a complete audio segment through the full pipeline."""
        session.state = VoiceState.PROCESSING

        # 1. STT
        transcript = await self._stt.transcribe(audio)
        logger.info(
            "stt_complete text=%s lang=%s confidence=%.2f",
            transcript.text[:50],
            transcript.language,
            transcript.confidence,
        )

        # 2. Build messages for LLM
        messages = list(conversation_messages or [])
        messages.append(LLMMessage(role="user", content=transcript.text))

        # Route through LLM
        response = await self._router.route(messages)
        response_text = response.content
        logger.info("llm_complete model=%s", response.model)

        # 3. TTS
        session.state = VoiceState.SPEAKING
        tts_engine = await self._resolve_tts(session.config.tts_engine)
        audio_chunks: list[bytes] = []
        async for chunk in tts_engine.synthesize(response_text):
            audio_chunks.append(chunk)

        session.state = VoiceState.IDLE
        logger.info("tts_complete engine=%s chunks=%d", tts_engine.name, len(audio_chunks))

        return PipelineResult(
            transcript=transcript,
            response_text=response_text,
            audio_chunks=audio_chunks,
        )

    async def _resolve_tts(self, engine_name: str) -> TTSEngine:
        """Resolve TTS engine by name, falling back if unavailable."""
        engine = self._tts_engines.get(engine_name)
        if engine and await engine.is_available():
            return engine

        logger.warning("tts_unavailable engine=%s trying_fallback", engine_name)
        for name, fallback in self._tts_engines.items():
            if await fallback.is_available():
                logger.info("tts_fallback engine=%s", name)
                return fallback

        raise RuntimeError("No TTS engine available")
