# Phase 3B-1: Persona Engine + Emotion Detection — Design Spec

**Date:** 2026-03-21
**Status:** Approved (2 review rounds, all issues resolved)
**Depends on:** Phase 3A (voice pipeline), Phase 1 (auth/gateway), Phase 2 (brain/router)

## Overview

Phase 3B-1 adds a persona system and emotion detection engine to Nobla Agent. Personas shape LLM behavior (personality, language style, rules) and TTS voice selection. Emotion detection analyzes user voice to adapt responses to mood. Both work together: persona defines *who* the agent is, emotion provides *contextual awareness* of the user's state.

This is the first of three Phase 3B sub-projects:
- **3B-1** (this spec): Persona engine + emotion detection (backend)
- **3B-2**: PersonaPlex premium TTS integration (backend)
- **3B-3**: Flutter persona UI (avatar, selector, voice settings)

## Architecture: Approach 2 — Top-Level Persona Module

Persona is a first-class top-level module (`nobla/persona/`) alongside `voice/`, `brain/`, `memory/`. Emotion detection lives under `voice/emotion/` since it's audio analysis. They communicate through a shared service function — no event bus, no tight coupling.

**Rationale:** Persona affects the entire system (LLM prompts, TTS voice selection, future Flutter UI), not just voice. Keeping it at the top level matches the target project structure and avoids crowding `voice/`.

## File Layout

### New Files

```
backend/nobla/
├── persona/
│   ├── __init__.py          # Package exports
│   ├── models.py            # Persona (SQLAlchemy), EmotionResult, PersonaContext (Pydantic)
│   ├── presets.py            # Professional, Friendly, Military as dataclasses
│   ├── repository.py         # Async CRUD + UserPersonaPreference table
│   ├── manager.py            # Load presets, resolve session/user persona, clone
│   ├── prompt.py             # Build system prompt string from persona + emotion
│   └── service.py            # resolve_and_route() shared service function
├── voice/
│   ├── emotion/
│   │   ├── __init__.py       # Package exports
│   │   ├── base.py           # Abstract EmotionEngine
│   │   ├── hume.py           # Hume AI REST client
│   │   ├── local.py          # wav2vec2 classifier (HuggingFace)
│   │   └── detector.py       # Fallback chain + 30s cache + confidence threshold
├── db/migrations/versions/
│   └── 002_phase3b_persona_tables.py  # Alembic migration for personas + user_persona_preferences
```

### Modified Files

- `gateway/persona_routes.py` (new route file) — CRUD + preference endpoints
- `gateway/voice_handlers.py` — call `resolve_and_route()` for voice path, add `set_persona_manager()` / `get_persona_manager()` accessors
- `gateway/websocket.py` — call `resolve_and_route()` for text path in `chat.send` handler, add persona manager accessors
- `gateway/app.py` — register persona APIRouter, initialize PersonaManager in lifespan
- `brain/router.py` — accept `system_prompt_extra: str` and `temperature_bias: float` parameters
- `brain/base_provider.py` — add `default_temperature: float` attribute (per-provider)
- `config/settings.py` — add `PersonaSettings` section
- `voice/pipeline.py` — return `EmotionResult` alongside transcribed text

### Estimated Scope

- New code: ~550-650 lines across 11 new files
- Modified code: ~100-150 lines across 4 existing files
- Total touch surface: ~700-800 lines
- Largest new file: `repository.py` at ~120 lines (well under 750-line limit)

## Data Model

### Persona (SQLAlchemy)

```python
class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False))  # PK, matches existing User model pattern
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))  # FK to users
    name: Mapped[str]                         # 1-100 chars, unique per user_id
    personality: Mapped[str]                  # 1-1000 chars, natural language description
    language_style: Mapped[str]               # 1-500 chars, e.g. "formal, concise, structured"
    voice_config: Mapped[dict | None]         # JSONB, e.g. {"engine": "fish_speech", "voice": "alloy", "speed": 1.0}
    background: Mapped[str | None]            # Backstory/expertise context

    # Hybrid rules: plain text + typed system fields
    rules: Mapped[list[str]]                  # JSONB array, max 20 rules, each max 500 chars
    temperature_bias: Mapped[float | None]    # -0.5 to +0.5, applied relative to provider default
    max_response_length: Mapped[int | None]   # 50-4096 tokens

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**Note:** `is_builtin` is NOT a DB column — builtins are never stored in DB. The Pydantic response schema includes `is_builtin: bool` which is set to `True` when serializing presets from memory and `False` for DB rows.

**Key decisions:**
- UUID columns use `str` with `mapped_column(UUID(as_uuid=False))` to match the existing `User` model pattern from Phase 1
- `voice_config` as JSONB instead of a plain `voice_id` string — holds engine-specific settings, extensible
- `temperature_bias` instead of absolute `temperature` — consistent persona behavior across LLM providers (router applies `provider_default + bias`, clamped to valid range)
- `forbidden_topics` dropped — overlaps with natural language rules, not worth the typed field
- No `avatar_url` — that's Phase 3B-3 scope, add via migration when Flutter needs it

### UserPersonaPreference (SQLAlchemy)

```python
class UserPersonaPreference(Base):
    __tablename__ = "user_persona_preferences"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False))         # PK, FK to users
    default_persona_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))  # FK to personas (or builtin UUID)
```

Single row per user. Stores persistent default persona preference so new conversations start with the user's chosen persona rather than always falling back to Professional.

### EmotionResult (Pydantic)

```python
class EmotionResult(BaseModel):
    emotion: str          # "happy", "sad", "frustrated", "curious", "neutral", "anxious"
    confidence: float     # 0.0-1.0
    secondary: str | None # Second strongest emotion
    source: str           # "hume" or "local"
```

Lightweight value object. Not persisted to DB — ephemeral per voice session.

### PersonaContext (Pydantic)

```python
class PersonaContext(BaseModel):
    persona_id: str
    persona_name: str
    system_prompt_addition: str   # Pre-built string for LLM
    temperature_bias: float | None
    voice_config: dict | None
```

Assembled output from `prompt_builder.build()`. Used by the voice handler to select TTS voice via `voice_config`, and by `resolve_and_route()` for `system_prompt_addition` and `temperature_bias`. This is the return type of `PromptBuilder.build()` — callers destructure it rather than accessing persona fields directly.

## Bundled Presets

Three presets defined as Python dataclasses in `persona/presets.py`. Loaded into memory on startup, always available even if DB is empty.

### Professional (default)
- **Personality:** "Expert assistant focused on clarity and efficiency"
- **Style:** "formal, concise, structured"
- **Rules:** "Use bullet points for lists", "Cite sources when available", "Avoid colloquialisms"
- **Temperature bias:** 0.0 (provider default)
- **Voice config:** None (system default TTS)

### Friendly
- **Personality:** "Warm conversational companion, encouraging and approachable"
- **Style:** "casual, warm, uses analogies"
- **Rules:** "Match the user's energy level", "Use simple language", "Encourage questions"
- **Temperature bias:** +0.2 (slightly more creative)
- **Voice config:** None (system default TTS)

### Military
- **Personality:** "Direct, mission-focused tactical advisor"
- **Style:** "terse, action-oriented, uses military terminology"
- **Rules:** "Lead with the bottom line", "Use short sentences", "No hedging or filler"
- **Temperature bias:** -0.3 (more deterministic)
- **Voice config:** None (system default TTS)

**Loading behavior:**
- `PersonaManager.__init__()` loads presets into an in-memory dict keyed by a stable UUID (hardcoded per preset)
- CRUD API returns presets alongside DB personas in list responses
- Delete/update requests on builtins are rejected with 403
- Clone endpoint copies a preset into DB as an editable custom persona with `is_builtin=False`

**Name collision protection:** On create/update, the repository rejects persona names that match any builtin name (case-insensitive).

## Emotion Detection

### Architecture

Two engines behind an abstract interface with automatic fallback:

```
Audio chunk → EmotionDetector.detect(audio_bytes)
           → Try Hume AI (cloud, ~$0.003/req)
           → If unavailable/no API key → local wav2vec2 classifier (CPU)
           → Returns EmotionResult(emotion, confidence, secondary, source)
```

### Engines

**Hume AI** (`voice/emotion/hume.py`):
- REST API client with API key auth
- Handles rate limits and transient failures gracefully
- Returns detailed emotion probabilities, mapped to our 6-emotion vocabulary

**Local model** (`voice/emotion/local.py`):
- HuggingFace wav2vec2-based emotion classifier
- Loaded once on startup, runs on CPU
- ~80% accuracy, zero cost, no external dependency

**Fallback chain** (`voice/emotion/detector.py`):
- Hume AI available + API key configured → use Hume
- Hume unavailable/fails → use local model
- Both fail → return `None` (persona prompt skips mood line entirely)

### Caching & Thresholds

- **Cache per session, re-detect every 30 seconds** — cache key is `connection_id`, stored in a plain `dict` (not Redis), TTL 30s. Emotions don't shift per-word, reduces API calls and compute
- **Confidence threshold: 0.5** — below this, return `emotion: "neutral"` to avoid noisy prompt injection
- **6-emotion vocabulary:** happy, sad, frustrated, curious, neutral, anxious — both engines map to this common set

### Graceful Degradation

- No Hume API key → local model only (free, no config needed)
- No GPU → local model runs on CPU (slower but functional)
- Both engines fail → emotion is `None`, persona works without mood context
- Emotion detection can be disabled per-user via settings (future: `UserPersonaPreference.emotion_enabled`)

## Persona Manager

### Responsibilities

`PersonaManager` (`persona/manager.py`):
- Holds presets in-memory, queries DB via repository for user personas
- `resolve(session_id, user_id) -> Persona` — resolution chain: session override → user default → Professional
- `get_persona(persona_id) -> Persona | None` — lookup by ID (checks presets first, then DB)
- `list_for_user(user_id) -> list[Persona]` — presets + user's custom personas
- `clone_preset(persona_id, user_id) -> Persona` — copies into DB, sets `is_builtin=False`, appends "(Copy)" to name. On name collision, appends numeric suffix: "(Copy 2)", "(Copy 3)", etc.
- `set_session_persona(session_id, persona_id)` — per-conversation override (in-memory, ephemeral)

### Session Tracking

In-memory dict: `session_id → persona_id`. Ephemeral — lost on restart, which is correct since voice sessions don't survive restarts either. Persistent preference is handled by `UserPersonaPreference` in DB.

**Cleanup on disconnect:** The gateway calls `persona_manager.clear_session(session_id)` when a WebSocket disconnects (alongside the existing `ConnectionManager.disconnect()` call). This prevents session persona entries from leaking until restart.

### DB-Unreachable Fallback

If PostgreSQL is unreachable during persona resolution (e.g., `get_persona()` or `list_for_user()` fails), the manager falls back to in-memory presets only. The user gets the Professional default rather than an error. A warning is logged for monitoring.

## Prompt Builder

`prompt.py` assembles a system prompt addition from persona + optional emotion:

```
You are {persona.name}. {persona.personality}

Communication style: {persona.language_style}
Background: {persona.background}

Rules:
- {rule_1}
- {rule_2}
- ...

[if emotion detected and confidence >= 0.5]
User's current mood: {emotion.emotion} (confidence: {emotion.confidence})
Adapt your response accordingly.

[if max_response_length set]
Keep responses under {max_response_length} tokens.
```

Returns a plain string. The brain/router prepends it to whatever model-specific system prompt it already uses. The router doesn't know about personas — it just receives extra prompt text and an optional temperature bias.

`get_temperature_bias(persona) -> float | None` — separate method for the router to apply `provider_default + bias`, clamped to each provider's valid range.

## Configuration

### PersonaSettings (added to `config/settings.py`)

```python
class PersonaSettings(BaseModel):
    hume_api_key: str | None = None           # Hume AI API key, None = local-only
    emotion_enabled: bool = True              # Global emotion detection toggle
    emotion_cache_ttl: int = 30               # Seconds between re-detection
    emotion_confidence_threshold: float = 0.5 # Below this → "neutral"
    default_persona: str = "professional"     # Fallback preset name
    local_emotion_model: str = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
```

Loaded from environment variables with `NOBLA_PERSONA_` prefix, following the existing `Settings` pattern in `config/settings.py`.

### Lifespan Initialization

In `gateway/app.py`'s existing `lifespan()` async context manager:

```python
# During startup (alongside existing router, pipeline init)
persona_manager = PersonaManager(db_session_factory, settings.persona)
prompt_builder = PromptBuilder()
emotion_detector = EmotionDetector(settings.persona)

# Wire into handler modules (follows existing set_X/get_X pattern)
set_persona_manager(persona_manager)
set_prompt_builder(prompt_builder)
voice_handlers.set_emotion_detector(emotion_detector)

# Register persona API routes
app.include_router(persona_router)  # from gateway/persona_routes.py
```

The local wav2vec2 emotion model is downloaded from HuggingFace on first startup if not cached. This should be noted in deployment/setup docs.

## Integration: Shared Service Function

Both voice and text paths use a shared function instead of middleware (middleware can't distinguish voice from text before processing).

### Dependency Injection

Follows the existing codebase pattern of module-level `set_X()` / `get_X()` accessors (see `websocket.py` lines 134-205, `voice_handlers.py` lines 22-33). The `resolve_and_route()` function fetches its own dependencies internally via these accessors rather than taking them as parameters:

```python
# In persona/service.py

async def resolve_and_route(
    messages: list[LLMMessage],
    session_id: str,
    user_id: str,
    emotion: EmotionResult | None = None,
) -> LLMResponse:
    persona_manager = get_persona_manager()
    prompt_builder = get_prompt_builder()
    brain_router = get_router()

    persona = persona_manager.resolve(session_id, user_id)
    prompt_extra = prompt_builder.build(persona, emotion)
    return await brain_router.route(
        messages,
        system_prompt_extra=prompt_extra,
        temperature_bias=persona.temperature_bias,
    )
```

The function accepts pre-built `LLMMessage` list (constructed by the handler, as today) rather than raw text. This keeps message construction in the handler where it belongs — the service only adds persona context.

Handler modules (`websocket.py`, `voice_handlers.py`) call `resolve_and_route(text, sid, uid, emotion)` with no dependency arguments needed.

### Router Integration (brain/router.py)

The `LLMRouter.route()` method is modified to accept two new kwargs:

- **`system_prompt_extra: str`** — prepended as a system-role `LLMMessage` at position 0 of the messages list, before forwarding to the provider. This follows the same pattern as the existing memory system prompt injection in `websocket.py`.
- **`temperature_bias: float`** — applied as `kwargs["temperature"] = clamp(provider.default_temperature + bias, 0.0, 2.0)` before calling `provider.generate()`.

`BaseLLMProvider` gains a `default_temperature: float` class attribute (e.g., OpenAI=1.0, Claude=1.0, Gemini=1.0, Ollama=0.8). Each provider subclass can override this. The router reads it before applying the bias.

### Route Registration (gateway/app.py)

`gateway/persona_routes.py` exports an `APIRouter` with `prefix="/api"` and `tags=["personas"]`. It is registered in `app.py` via `app.include_router(persona_router)` alongside the existing `rest_router`.

### Voice Path

```
Audio → voice/pipeline.py (VAD → STT → emotion detection)
     → returns: { transcribed_text, emotion_result }
     → gateway voice handler calls resolve_and_route(text, sid, uid, emotion_result)
     → brain/router.route() with persona prompt + temperature bias
     → response → TTS (with persona.voice_config) → audio back to client
```

### Text Path

```
Text message → gateway text handler
            → calls resolve_and_route(text, sid, uid)  # emotion=None
            → brain/router.route() with persona prompt + temperature bias (no mood line)
            → response back to client
```

## REST API

### Persona CRUD

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/personas` | List presets + user's custom personas |
| `POST` | `/api/personas` | Create custom persona |
| `GET` | `/api/personas/{id}` | Get single persona |
| `PUT` | `/api/personas/{id}` | Update (rejects builtins with 403) |
| `DELETE` | `/api/personas/{id}` | Delete (rejects builtins with 403) |
| `POST` | `/api/personas/{id}/clone` | Clone as editable copy |

### User Preference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/user/persona-preference` | Get user's default persona |
| `PUT` | `/api/user/persona-preference` | Set user's default persona |

Separated from `/api/personas/{id}` to avoid route conflicts (FastAPI would capture "persona-preference" as an `{id}` parameter).

### Validation Rules

- `name`: required, 1-100 chars, unique per user, cannot match builtin names (case-insensitive)
- `personality`: required, 1-1000 chars
- `language_style`: required, 1-500 chars
- `rules`: max 20 rules, each max 500 chars
- `temperature_bias`: -0.5 to +0.5
- `max_response_length`: 50 to 4096 tokens
- `voice_config`: optional, validated per known engine (`fish_speech`, `cosyvoice`). Unknown engine names are accepted with a warning log (forward-compatible with Phase 3B-2 PersonaPlex)

### Auth

All endpoints require JWT auth (Phase 1). Users can only CRUD their own personas. Presets are read-only for all users. Clone works on builtins and user's own personas.

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Emotion detection | Hume AI + local fallback | Graceful degradation principle; cloud quality when available, free local when not |
| Persona storage | Local-only, no marketplace fields | YAGNI — marketplace is Phase 6, requirements will evolve, migrations are cheap |
| Rules system | Hybrid (plain text + typed fields) | Plain text for flexibility, typed fields (temperature_bias, max_response_length) for system-level knobs |
| Pre-built personas | Bundled in code, not DB | Always available even with empty DB; clone to customize |
| Emotion → persona | System prompt injection | Lets LLM decide adaptation using persona rules; keeps emotion module decoupled |
| Temperature | Relative bias, not absolute | Consistent behavior across LLM providers (router applies provider_default + bias) |
| Integration point | Shared service function in handler layer | Works for both voice (with emotion) and text (without); simpler than middleware |
| Persona module location | Top-level `nobla/persona/` | Persona affects system-wide behavior, not just voice |
| Default persona storage | Separate `UserPersonaPreference` table | Doesn't touch User model from Phase 1; extensible for future preferences |
| Route design | `/api/user/persona-preference` separate from `/api/personas/{id}` | Avoids FastAPI route conflict; cleaner REST semantics |
