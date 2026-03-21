# Phase 3B-2: PersonaPlex TTS Integration — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Depends on:** Phase 3B-1 (persona engine + emotion detection), Phase 3A (voice pipeline)

## Overview

Add a PersonaPlex TTS engine client to the Nobla Agent backend. PersonaPlex is a self-hosted 7B parameter voice model that supports voice prompt conditioning (custom voice character) and text prompt conditioning (persona attributes). This integration provides premium voice quality as an alternative to the default Fish Speech / CosyVoice2 engines.

**Scope:** HTTP client for an external PersonaPlex server + Docker Compose deployment sample. Half-duplex only — full-duplex (listen + speak simultaneously) is deferred to a future sub-project as it requires changes to the WebSocket protocol, Flutter audio layer, and pipeline state machine.

## Architecture

PersonaPlexTTS is a new `TTSEngine` subclass that communicates with an external PersonaPlex server via HTTP. The server can be deployed locally (Docker with GPU) or on cloud GPU providers (RunPod, Vast.ai). Nobla does not manage the Docker lifecycle — users deploy PersonaPlex separately and provide the server URL.

The existing pipeline fallback chain (`_resolve_tts()`) handles unavailability automatically: if PersonaPlex is down or unconfigured, the pipeline falls back to CosyVoice/Fish Speech.

## File Layout

### New Files

| File | Responsibility |
|------|---------------|
| `backend/nobla/voice/tts/personaplex.py` | PersonaPlexTTS engine — HTTP client |
| `docker/personaplex/docker-compose.yml` | Sample Docker Compose for PersonaPlex deployment |
| `backend/tests/test_personaplex.py` | Unit tests for PersonaPlexTTS |

### Modified Files

| File | Changes |
|------|---------|
| `backend/nobla/config/settings.py` | Add `PersonaPlexSettings` class + `personaplex` field on `Settings` |
| `backend/nobla/gateway/app.py` | Register PersonaPlexTTS engine in lifespan if enabled |

### Estimated Scope

- New code: ~150 lines across 2 source files
- Tests: ~80 lines
- Docker Compose: ~30 lines
- Modified code: ~15 lines across 2 existing files

## PersonaPlexSettings

Added to `config/settings.py`:

```python
class PersonaPlexSettings(BaseModel):
    enabled: bool = False
    server_url: str = "http://localhost:8880"
    timeout: float = 30.0
    voice_prompts_dir: str = "backend/nobla/voice/models/voice_prompts"
    cpu_offload: bool = False
```

Added to `Settings` class as `personaplex: PersonaPlexSettings`.

**Defaults:** Disabled by default. Users enable by setting `NOBLA_PERSONAPLEX_ENABLED=true` and providing the server URL.

## PersonaPlexTTS Engine

### Class Design

```python
class PersonaPlexTTS(TTSEngine):
    """PersonaPlex 7B TTS engine — HTTP client for external server."""

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        voice_prompts_dir: str | None = None,
        cpu_offload: bool = False,
    ) -> None: ...

    @property
    def name(self) -> str:
        return "personaplex"

    async def is_available(self) -> bool:
        """GET /health on the PersonaPlex server. Returns False on timeout/error."""

    async def synthesize(self, text: str, voice_id: str = "default") -> AsyncIterator[bytes]:
        """POST /synthesize with text + voice/text prompts. Streams audio chunks."""

    async def get_voices(self) -> list[VoiceInfo]:
        """GET /voices on the PersonaPlex server."""
```

### Voice Prompt Resolution

The `voice_id` parameter maps to a voice prompt file:
- `"default"` → no voice prompt (server uses its default voice)
- `"professional.wav"` → file at `{voice_prompts_dir}/professional.wav`
- `"path:/absolute/path/to/voice.wav"` → absolute path (for advanced users)

The resolved file is sent to the PersonaPlex server as part of the synthesis request. If the file doesn't exist, the engine logs a warning and falls back to the server's default voice.

### Text Prompt Conditioning

The `synthesize()` method accepts persona context through the persona system's existing `voice_config` dict. The voice handler (modified in Phase 3B-1) already passes `persona_ctx.voice_config` when selecting the TTS engine. The PersonaPlex engine extracts text prompt fields from voice_config:

```python
voice_config = {
    "engine": "personaplex",
    "voice_prompt": "professional.wav",
    "text_prompt": {
        "personality": "formal and authoritative",
        "style": "concise, structured",
    }
}
```

If `text_prompt` is not in voice_config, the engine synthesizes without text conditioning.

### PersonaPlex Server API Contract

What the PersonaPlex server is expected to provide:

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `GET` | `/health` | — | `{"status": "ok"}` |
| `GET` | `/voices` | — | `[{"id": "default", "name": "Default", "language": "en"}]` |
| `POST` | `/synthesize` | JSON body (see below) | Streaming audio bytes (`audio/wav` or `audio/opus`) |

**Synthesize request body:**
```json
{
    "text": "Hello, how can I help you?",
    "voice_prompt_path": "/path/to/voice.wav",
    "text_prompt": {
        "personality": "formal and authoritative",
        "style": "concise"
    },
    "cpu_offload": false
}
```

`voice_prompt_path` and `text_prompt` are both optional. The server uses defaults when omitted.

### Error Handling

- **Server unreachable:** `is_available()` returns `False`. Pipeline fallback kicks in.
- **Synthesis timeout:** `httpx.TimeoutException` caught, logged, raises to trigger fallback.
- **Voice prompt file missing:** Warning logged, synthesis proceeds without voice prompt.
- **Server error (5xx):** Logged, raises to trigger fallback.
- **Invalid response:** Logged, raises to trigger fallback.

All errors are non-fatal at the engine level — the pipeline's `_resolve_tts()` fallback handles engine failures gracefully.

## App Lifespan Integration

In `gateway/app.py` lifespan, after existing TTS engine initialization:

```python
if settings.personaplex.enabled:
    from nobla.voice.tts.personaplex import PersonaPlexTTS
    personaplex_engine = PersonaPlexTTS(
        server_url=settings.personaplex.server_url,
        timeout=settings.personaplex.timeout,
        voice_prompts_dir=settings.personaplex.voice_prompts_dir,
        cpu_offload=settings.personaplex.cpu_offload,
    )
    tts_engines["personaplex"] = personaplex_engine
```

This registers PersonaPlex alongside Fish Speech and CosyVoice in the TTS engine dict. The pipeline's `_resolve_tts()` can then select it by name.

## Docker Compose Sample

```yaml
# docker/personaplex/docker-compose.yml
services:
  personaplex:
    image: personaplex/personaplex-7b:latest
    ports:
      - "8880:8880"
    volumes:
      - ./voice_prompts:/data/voice_prompts
    environment:
      - MODEL_PATH=/models/personaplex-7b-v1
      - CPU_OFFLOAD=false
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Provided as a reference. Users copy and adapt for their deployment (local Docker, RunPod, Vast.ai).

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Server communication | HTTP client to external endpoint | Loose coupling, works with local Docker and cloud GPU providers |
| Docker management | Sample docker-compose.yml only | DevOps concern, not application code |
| Full-duplex | Deferred (half-duplex only) | Requires WebSocket protocol changes, Flutter audio mixing — separate sub-project |
| Voice prompt storage | Local filesystem | Simple, no DB overhead for static audio files. Upload UI is Phase 3B-3 |
| Fallback | Existing pipeline `_resolve_tts()` | Already handles engine unavailability with graceful degradation |
