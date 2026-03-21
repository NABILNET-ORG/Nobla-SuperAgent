# Phase 3 Design Spec: Voice Pipeline & Persona System

**Date:** 2026-03-21
**Author:** NABILNET.AI
**Status:** Draft
**Scope:** STT, TTS, VAD, emotion detection, persona system, PersonaPlex cloud, Flutter voice UI, avatar
**Depends on:** Phase 2B (LLM router for response generation, WebSocket gateway for streaming)

---

## 1. Overview

Phase 3 adds voice interaction and persona customization to Nobla Agent. Users speak into the Flutter app, audio streams to the backend voice pipeline (STT → LLM → TTS), and audio responses stream back with synchronized avatar animations. Personas define the agent's voice, personality, and behavior. Emotion detection from voice adapts responses to the user's mood.

### Goals
- Real-time voice conversation: speak → hear response with <2s latency target
- Levantine Arabic STT via custom Faster-Whisper model (ggml-levantine-large-v3.bin)
- Two TTS engines (Fish Speech V1.5 + CosyVoice2) behind pluggable interface
- PersonaPlex as opt-in premium cloud TTS (RunPod/Vast.ai endpoint)
- Full emotion detection from voice, feeding into LLM system prompt
- Structured persona system with presets and custom creation
- Rive avatar with real-time lip-sync and emotion-driven expressions
- Three VAD modes: push-to-talk, auto-detect, walkie-talkie

### Non-Goals (Phase 3)
- Local PersonaPlex GPU deployment (cloud-only)
- Persona marketplace (Phase 6+)
- Background voice mode / always-on listening (deferred)
- Voice cloning fine-tuning UI (users provide reference audio, no training workflow)

---

## 2. Architecture: Pipeline Pattern

Voice processing uses a chain of discrete stages, each its own submodule with an abstract base class. A pipeline orchestrator routes audio through stages and manages the session lifecycle. This mirrors how `brain/router.py` handles LLM providers.

### 2.1 Backend Module Structure

```
backend/nobla/voice/
├── __init__.py
├── pipeline.py          # VoicePipeline orchestrator — routes audio through stages
├── models.py            # Pydantic models: AudioFrame, VoiceConfig, PersonaConfig, EmotionResult
│
├── stt/
│   ├── __init__.py
│   ├── base.py          # STTEngine ABC — transcribe(audio) -> Transcript
│   ├── whisper.py       # Faster-Whisper standard engine (large-v3)
│   ├── levantine.py     # Levantine Arabic engine (wraps whisper with custom model)
│   └── detector.py      # Language detector — routes to correct STT engine
│
├── tts/
│   ├── __init__.py
│   ├── base.py          # TTSEngine ABC — synthesize(text, voice) -> AudioStream
│   ├── fish_speech.py   # Fish Speech V1.5 engine
│   ├── cosyvoice.py     # CosyVoice2 engine
│   └── personaplex.py   # PersonaPlex cloud client (RunPod/Vast.ai endpoint)
│
├── emotion/
│   ├── __init__.py
│   ├── base.py          # EmotionDetector ABC — detect(audio) -> EmotionResult
│   ├── hume.py          # Hume AI integration
│   └── open_source.py   # wav2vec2 + custom classifier fallback
│
├── vad.py               # Silero VAD — detects speech start/end, supports 3 modes
│
└── persona/
    ├── __init__.py
    ├── models.py         # Persona DB models (SQLAlchemy)
    ├── repository.py     # Persona CRUD operations
    ├── manager.py        # Persona loading, switching, defaults
    └── presets.py        # Built-in personas (Professional, Friendly, Military)
```

**Design rationale:**
- Each stage has an ABC so engines are swappable (e.g., swap Fish Speech for CosyVoice2)
- PersonaPlex lives in `tts/` because in our cloud-only architecture it takes text + voice prompt and returns audio — functionally a TTS engine. Full-duplex streaming is handled at the pipeline level.
- VAD is a single file (not a directory) — one implementation (Silero) with mode configuration. YAGNI.
- Persona is separate from voice processing — it defines *what* voice/personality to use, not *how* to process audio. Persona also affects LLM system prompts and avatar selection.

---

## 3. Voice Pipeline Data Flow

```
┌─────────────────── FLUTTER APP ───────────────────┐
│  Mic → Opus encode → WebSocket frames             │
│  WebSocket frames → Opus decode → Speaker + Avatar │
└──────────────────────┬────────────────▲────────────┘
                       │                │
                 opus frames      opus frames
                       │                │
┌──────────────────────▼────────────────┴────────────┐
│              GATEWAY (websocket.py)                 │
│  New RPC methods:                                  │
│    voice.start   — begin voice session             │
│    voice.stop    — end voice session               │
│    voice.audio   — incoming audio chunk            │
│    voice.config  — set persona, TTS engine, VAD    │
└──────────────────────┬────────────────▲────────────┘
                       │                │
┌──────────────────────▼────────────────┴────────────┐
│              VOICE PIPELINE (pipeline.py)           │
│                                                    │
│  1. VAD: audio chunks → speech segments            │
│     Buffers until speech end detected              │
│                                                    │
│  2. STT: speech segment → Transcript               │
│     detector.py picks engine:                      │
│       Arabic detected → levantine.py               │
│       Other language  → whisper.py                 │
│                                                    │
│  3. EMOTION (parallel with STT):                   │
│     speech segment → EmotionResult                 │
│     {joy: 0.1, sadness: 0.7, anger: 0.05, ...}    │
│                                                    │
│  4. LLM (reuse brain/router.py):                   │
│     Transcript + EmotionResult + Persona →         │
│     system prompt with emotion context →           │
│     LLM streaming response                        │
│                                                    │
│  5. TTS: response text chunks → audio stream       │
│     Engine selected by persona config              │
│     Streams Opus frames back via WebSocket         │
└────────────────────────────────────────────────────┘
```

### 3.1 Key Pipeline Behaviors

**Parallel STT + Emotion:** STT and emotion detection run concurrently on the same audio segment via `asyncio.gather()`. Emotion result is available by the time STT completes.

**Incremental TTS:** As LLM tokens stream in, the pipeline buffers until a sentence boundary (period, question mark, exclamation). Each complete sentence is sent to TTS immediately — don't wait for the full response. This reduces perceived latency.

**VAD modes:**
- **Push-to-talk (default):** Buffer audio while button held. On release, send full segment to STT.
- **Auto-detect:** Silero VAD continuously monitors audio stream. On speech-start, begin buffering. On silence >800ms, send segment to STT.
- **Walkie-talkie:** First tap starts recording, second tap stops. Segment sent to STT on stop.

**Interrupt handling:** In auto-detect mode, if the user speaks while TTS audio is playing, the pipeline cancels the current TTS stream and starts a new STT cycle. Server sends `voice.state: "listening"` to signal Flutter to stop playback.

### 3.2 Audio Format

- **Codec:** Opus (RFC 6716)
- **Sample rate:** 48kHz (Opus native), downsampled to 16kHz for STT
- **Channels:** Mono
- **Bitrate:** 32kbps (voice-optimized)
- **Frame size:** 20ms (960 samples at 48kHz)
- **Transport:** Base64-encoded Opus frames inside JSON-RPC messages

Base64 adds ~33% overhead but keeps the protocol pure JSON-RPC — no mixed binary/text WebSocket frames. At 32kbps this means ~5.3KB/s vs 4KB/s raw. Acceptable trade-off for protocol simplicity. Can upgrade to binary frames in a future optimization pass.

---

## 4. STT Engine Design

### 4.1 Abstract Base

```python
class STTEngine(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, language: str | None = None) -> Transcript:
        """Transcribe audio bytes to text."""

    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[PartialTranscript]:
        """Stream partial transcription results."""
```

### 4.2 Language Detection & Routing

`detector.py` uses a two-stage approach:
1. **Fast pre-detection:** Use `langdetect` or `fasttext` on any available text context (conversation history language). If the user has been chatting in Arabic, assume Arabic for STT.
2. **Audio-based detection:** If no text context, run the first 3 seconds of audio through Faster-Whisper's built-in language detection.

Routing:
- Arabic (any dialect) → `levantine.py` (loads `ggml-levantine-large-v3.bin`)
- All other languages → `whisper.py` (loads standard `large-v3` model)

### 4.3 Levantine Model Integration

The custom model (`ggml-levantine-large-v3.bin`, 2.9GB) is a Faster-Whisper model fine-tuned for Levantine Arabic. It loads via the same `faster-whisper` API as the standard model — only the model path differs.

```python
class LevantineSTT(STTEngine):
    def __init__(self, model_path: str = "backend/nobla/voice/models/ggml-levantine-large-v3.bin"):
        self.model = WhisperModel(model_path, device="auto", compute_type="auto")
```

**Model loading:** Models are loaded lazily on first use and cached in memory. On CPU-only machines, `compute_type="int8"` is used automatically for acceptable performance.

---

## 5. TTS Engine Design

### 5.1 Abstract Base

```python
class TTSEngine(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice_config: VoiceConfig) -> AsyncIterator[bytes]:
        """Synthesize text to audio stream (Opus frames)."""

    @abstractmethod
    async def get_voices(self) -> list[VoiceInfo]:
        """List available voices for this engine."""
```

### 5.2 Fish Speech V1.5

- **License:** MIT
- **Voice cloning:** Zero-shot from ~10s reference audio
- **Streaming:** Supports streaming output
- **Model size:** ~1.5GB
- **Strengths:** Fast inference, good English/Chinese/Japanese
- **Setup:** Local model download, runs on CPU or GPU

### 5.3 CosyVoice2

- **License:** Apache 2.0
- **Voice cloning:** Zero-shot with reference audio
- **Streaming:** Supports streaming output
- **Model size:** ~2GB
- **Strengths:** Better multilingual support including Arabic, newer architecture
- **Setup:** Local model download, runs on CPU or GPU

### 5.4 PersonaPlex Cloud Client

- **Deployment:** Cloud-only (RunPod/Vast.ai)
- **Access:** User provides endpoint URL + API auth token in settings
- **Features:** Voice prompt conditioning (custom voice character), text prompt conditioning (persona attributes)
- **Fallback:** If endpoint unreachable, auto-fallback to user's configured default engine (Fish Speech or CosyVoice2)

```python
class PersonaPlexTTS(TTSEngine):
    def __init__(self, endpoint_url: str, auth_token: str):
        self.client = httpx.AsyncClient(base_url=endpoint_url, headers={"Authorization": f"Bearer {auth_token}"})

    async def synthesize(self, text: str, voice_config: VoiceConfig) -> AsyncIterator[bytes]:
        # Stream audio from cloud endpoint
        # Auto-fallback on connection error
```

### 5.5 Engine Selection

The active persona's `tts_engine` field determines which engine handles synthesis. Users can also override via `voice.config` RPC at runtime.

Fallback chain: PersonaPlex → user's default engine → CosyVoice2 → Fish Speech

---

## 6. Emotion Detection

### 6.1 Abstract Base

```python
class EmotionDetector(ABC):
    @abstractmethod
    async def detect(self, audio: bytes) -> EmotionResult:
        """Detect emotions from audio. Returns probability distribution."""

# EmotionResult
class EmotionResult(BaseModel):
    joy: float          # 0.0 - 1.0
    sadness: float
    anger: float
    fear: float
    surprise: float
    disgust: float
    neutral: float
    dominant: str       # Highest-scoring emotion label
    confidence: float   # Confidence of dominant emotion
```

### 6.2 Hume AI Integration

Primary engine. Uses Hume's Prosody API to analyze vocal tone, pitch, tempo.

```python
class HumeEmotionDetector(EmotionDetector):
    def __init__(self, api_key: str):
        self.client = HumeClient(api_key=api_key)
```

### 6.3 Open-Source Fallback

Uses wav2vec2-based emotion classification (e.g., `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition` from HuggingFace). Runs locally, no API key needed.

### 6.4 Emotion → LLM Integration

When emotion is detected, the persona manager injects context into the LLM system prompt:

```
Current user emotion: {dominant} (confidence: {confidence:.0%})
Guidance: {persona.emotion_mappings[dominant]}
```

Example for "Friendly" persona with sadness detected:
```
Current user emotion: sadness (confidence: 72%)
Guidance: Respond with warmth and empathy. Acknowledge the feeling before addressing the question.
```

---

## 7. VAD (Voice Activity Detection)

Single module using Silero VAD (MIT license, lightweight, runs on CPU).

### 7.1 Three Modes

```python
class VADMode(str, Enum):
    PUSH_TO_TALK = "push_to_talk"    # Client controls start/stop
    AUTO_DETECT = "auto_detect"       # Silero detects speech boundaries
    WALKIE_TALKIE = "walkie_talkie"   # Tap-to-start, tap-to-stop

class VADConfig(BaseModel):
    mode: VADMode = VADMode.PUSH_TO_TALK
    silence_threshold_ms: int = 800   # Auto-detect: silence before segment end
    min_speech_ms: int = 250          # Ignore segments shorter than this
```

### 7.2 Behavior by Mode

- **Push-to-talk:** VAD is passive. Gateway buffers all audio between `voice.start` and `voice.stop` from client, then sends the complete segment to STT.
- **Auto-detect:** VAD processes every incoming audio frame. On speech-start event, begin buffering. On silence exceeding `silence_threshold_ms`, send buffered segment to STT. `min_speech_ms` filters out coughs, clicks, and other transient sounds.
- **Walkie-talkie:** Like push-to-talk but toggled (first tap starts, second stops). Client manages toggle state; VAD behavior is identical to push-to-talk.

---

## 8. Persona System

### 8.1 Database Schema

New SQLAlchemy model in `backend/nobla/db/models/personas.py`:

```python
class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID]                    # PK, server-generated
    user_id: Mapped[uuid.UUID | None]        # FK to users; null = built-in preset
    name: Mapped[str]                        # Display name
    personality: Mapped[str]                 # Free-text personality description
    language_style: Mapped[str]              # "formal", "casual", "military-precise"
    background: Mapped[str]                  # Backstory for LLM context window
    rules: Mapped[list[str]]                 # PostgreSQL ARRAY of behavioral rules

    # Voice config
    tts_engine: Mapped[str]                  # "fish_speech" | "cosyvoice" | "personaplex"
    voice_id: Mapped[str]                    # Engine-specific voice identifier
    voice_prompt_path: Mapped[str | None]    # Path to voice cloning reference audio

    # Avatar config
    avatar_asset: Mapped[str]                # Rive asset filename

    # Emotion response mappings
    emotion_mappings: Mapped[dict]           # JSONB: {"sadness": "respond with warmth", ...}

    # Metadata
    is_default: Mapped[bool]                 # One default per user
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### 8.2 Built-in Presets

Shipped in `persona/presets.py`, seeded into database on first run:

| Preset | Language Style | Personality | Emotion Response Style |
|---|---|---|---|
| **Professional** | Formal, concise, structured | Helpful, thorough, security-aware | Measured, composed — acknowledges without over-reacting |
| **Friendly** | Casual, warm, conversational | Enthusiastic, supportive, encouraging | Empathetic — mirrors emotion, offers comfort |
| **Military** | Direct, structured, no filler | Disciplined, action-oriented, efficient | Stoic — acknowledges briefly, refocuses on task |

### 8.3 Persona → LLM Integration

`persona/manager.py` generates a system prompt block prepended to every LLM call:

```
You are {name}. {background}
Communication style: {language_style}
Personality: {personality}
Rules:
- {rule_1}
- {rule_2}
Current user emotion: {emotion_result.dominant} (confidence: {confidence:.0%})
Guidance: {emotion_mappings[detected_emotion]}
```

This integrates with `brain/router.py`'s existing system prompt mechanism — the persona prompt is prepended before the user's conversation history.

### 8.4 Persona Switching

Mid-conversation switching is supported:
1. Client sends `voice.config` with new `persona_id`
2. `persona/manager.py` loads the new persona, updates system prompt
3. TTS engine swaps if the new persona uses a different engine
4. Server sends `voice.persona` event with new `avatar_asset` to Flutter
5. Flutter transitions the Rive avatar

---

## 9. WebSocket Protocol Extensions

New JSON-RPC methods added to `gateway/protocol.py`:

### 9.1 Client → Server

| Method | Params | Description |
|---|---|---|
| `voice.start` | `{persona_id, vad_mode, tts_engine}` | Begin voice session |
| `voice.stop` | `{}` | End voice session |
| `voice.audio` | `{data: "<base64 opus>"}` | Audio chunk from mic |
| `voice.config` | `{persona_id?, vad_mode?, tts_engine?}` | Update session config |

### 9.2 Server → Client

| Method | Params | Description |
|---|---|---|
| `voice.transcript` | `{text, language, is_final}` | STT result (partial or final) |
| `voice.audio` | `{data: "<base64 opus>"}` | TTS audio chunk |
| `voice.emotion` | `{joy, sadness, anger, ..., dominant}` | Emotion detection result |
| `voice.state` | `{state: "listening"\|"processing"\|"speaking"}` | Pipeline state change |
| `voice.persona` | `{persona_id, avatar_asset}` | Persona changed notification |
| `voice.error` | `{code, message}` | Pipeline error |

### 9.3 Design Notes

- Reuses existing JSON-RPC transport from Phase 1 — no new WebSocket connections needed
- `voice.transcript` sends partial results (`is_final=false`) for real-time transcription display, then a final result
- `voice.audio` is bidirectional — direction determined by sender (matches `chat.message` pattern)
- Emotion results stream independently so avatar can update expressions without waiting for full LLM response
- Voice session is scoped to a conversation — starting a voice session on a conversation that already has one replaces it

---

## 10. Flutter UI Design

### 10.1 New Feature Modules

```
app/lib/features/
├── voice/
│   ├── providers/
│   │   └── voice_provider.dart     # Riverpod — recording state, WebSocket audio, VAD mode
│   ├── screens/
│   │   └── voice_chat_screen.dart  # Full-screen voice interaction overlay
│   ├── widgets/
│   │   ├── voice_button.dart       # Push-to-talk / walkie-talkie button
│   │   ├── waveform_display.dart   # Real-time audio waveform visualization
│   │   └── vad_mode_selector.dart  # Toggle between 3 VAD modes
│   └── services/
│       ├── audio_recorder.dart     # Mic → Opus encode → WebSocket frames
│       └── audio_player.dart       # WebSocket frames → Opus decode → speaker
│
├── persona/
│   ├── providers/
│   │   └── persona_provider.dart   # Riverpod — CRUD, active persona, switching
│   ├── screens/
│   │   ├── persona_list_screen.dart    # Browse presets + custom personas
│   │   └── persona_editor_screen.dart  # Create/edit persona form
│   └── widgets/
│       ├── persona_card.dart       # Preview card with avatar + name + style
│       └── persona_switcher.dart   # Quick-switch dropdown in chat app bar
│
└── avatar/
    ├── providers/
    │   └── avatar_provider.dart    # Riverpod — avatar state, animation params
    └── widgets/
        └── avatar_display.dart     # Rive animation with lip-sync + emotions
```

### 10.2 Integration with Existing Chat

- `chat_screen.dart` gains a mic button in the message input bar
- Tapping the mic opens `voice_chat_screen.dart` as a full-screen overlay
- `persona_switcher.dart` is added to the chat app bar for quick persona switching
- `avatar_display.dart` renders above the message list during active voice sessions
- Voice transcriptions appear as regular chat messages in the conversation

### 10.3 Audio Flow in Flutter

```
Recording:  Mic → record package (PCM) → opus_dart encode → WebSocket send
Playback:   WebSocket receive → opus_dart decode → just_audio playback
Avatar:     Playback audio → amplitude extraction → Rive state machine inputs
```

### 10.4 Voice State Machine

```
Idle → [user initiates] → Recording → [VAD/button end] → Processing → [response] → Playing → Idle
                                                                                ↑
                                                    [interrupt: user speaks] ───┘
```

- In auto-detect mode, speaking during playback triggers interrupt: cancels TTS, starts new recording
- In push-to-talk/walkie-talkie, pressing the button during playback triggers interrupt
- `voice.state` events from server drive UI transitions (waveform, avatar animation, status text)

### 10.5 Rive Avatar

- Avatar state machine has inputs for: `mouthOpen` (float, lip-sync), `emotion` (enum), `isSpeaking` (bool), `isListening` (bool)
- Audio amplitude is extracted from the playback stream and mapped to `mouthOpen` at ~30fps
- Emotion input is set when `voice.emotion` arrives from server — triggers expression transition
- Ship with 1 default avatar asset. Custom assets can be added to persona config later.

---

## 11. Configuration & Settings

New settings in `backend/nobla/config/settings.py`:

```python
class VoiceSettings(BaseModel):
    stt_model: str = "large-v3"
    levantine_model_path: str = "backend/nobla/voice/models/ggml-levantine-large-v3.bin"
    default_tts_engine: str = "cosyvoice"  # "fish_speech" | "cosyvoice" | "personaplex"
    default_vad_mode: str = "push_to_talk"
    opus_bitrate: int = 32000
    vad_silence_threshold_ms: int = 800
    vad_min_speech_ms: int = 250

class PersonaPlexSettings(BaseModel):
    enabled: bool = False
    endpoint_url: str = ""
    auth_token: str = ""  # Encrypted at rest via existing security module

class EmotionSettings(BaseModel):
    enabled: bool = True
    provider: str = "hume"  # "hume" | "open_source"
    hume_api_key: str = ""  # Encrypted at rest
    inject_into_llm: bool = True  # Feed emotion into system prompt
```

---

## 12. Graceful Degradation

| Scenario | Behavior |
|---|---|
| GPU unavailable | STT/TTS run on CPU with int8 quantization (slower but functional) |
| Levantine model missing | Fall back to standard Whisper large-v3 for Arabic |
| PersonaPlex endpoint down | Auto-fallback to default TTS engine (Fish Speech or CosyVoice2) |
| Hume API unavailable | Fall back to open-source wav2vec2 emotion model |
| Emotion detection disabled | Pipeline skips emotion stage, no mood in LLM prompt |
| Both TTS engines fail | Return text-only response via existing chat, log error |

---

## 13. Dependencies

### Backend (Python)

| Package | Purpose | License |
|---|---|---|
| `faster-whisper` | STT inference | MIT |
| `fish-speech` | TTS engine option 1 | MIT |
| `cosyvoice2` | TTS engine option 2 | Apache 2.0 |
| `silero-vad` | Voice activity detection | MIT |
| `opuslib` | Opus encode/decode | BSD |
| `hume` | Emotion detection API client | Proprietary API |
| `transformers` | Open-source emotion model (wav2vec2) | Apache 2.0 |
| `httpx` | PersonaPlex cloud client | BSD |
| `pydub` | Audio format conversion utilities | MIT |
| `soundfile` | Audio I/O | BSD |

### Flutter (Dart)

| Package | Purpose |
|---|---|
| `record` | Microphone capture (already in pubspec) |
| `just_audio` | Audio playback (already in pubspec) |
| `rive` | Avatar animation with state machines |
| `opus_dart` | Opus codec for Flutter |
| `audio_waveforms` | Waveform visualization widget |

---

## 14. Implementation Sub-phases

| Sub-phase | Scope | Depends on |
|---|---|---|
| **3A** | Backend voice pipeline: STT (Whisper + Levantine), TTS (Fish Speech + CosyVoice2), VAD, pipeline orchestrator, WebSocket protocol extensions | Nothing — starts immediately |
| **3B** | Persona system (DB model, CRUD, presets, LLM integration), emotion detection (Hume + open-source), PersonaPlex cloud client | 3A |
| **3C** | Flutter voice UI, persona UI, Rive avatar with lip-sync, full end-to-end integration | 3A + 3B |

### Phase 3 Verification Checklist
1. Speak English → STT transcribes → LLM responds → TTS plays audio response
2. Speak Lebanese Arabic → verify Levantine model activates, correct transcription
3. Switch TTS engine mid-session → audio response uses new engine
4. Switch persona → voice, personality, and avatar all change
5. Express sadness in voice → emotion detected → LLM response adapts tone
6. PersonaPlex configured → audio response comes from cloud endpoint
7. PersonaPlex endpoint down → auto-fallback to local TTS engine
8. All three VAD modes function correctly
9. Interrupt during playback → TTS cancelled, new recording starts

---

## 15. Security Considerations

- **Voice data privacy:** Audio is processed in-memory and never persisted to disk unless user explicitly enables recording storage
- **PersonaPlex auth:** API tokens encrypted at rest using existing AES-256 encryption from security module
- **Hume API key:** Encrypted at rest, same mechanism
- **Voice cloning reference audio:** Stored locally in user's data directory, never uploaded without consent
- **Emotion data:** Emotion results are ephemeral (used for current response only), not stored in conversation history unless user enables it
