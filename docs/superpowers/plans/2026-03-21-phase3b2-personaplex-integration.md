# Phase 3B-2: PersonaPlex TTS Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PersonaPlex premium TTS engine as an HTTP client, with Docker Compose sample and settings integration.

**Architecture:** New `PersonaPlexTTS` subclass of `TTSEngine` communicating via HTTP to an external PersonaPlex server. Registered in the pipeline's TTS engine dict alongside Fish Speech and CosyVoice. Fallback handled by existing `_resolve_tts()`.

**Tech Stack:** Python 3.12, httpx (async HTTP), FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-03-21-phase3b2-personaplex-integration-design.md`

---

## Task 1: PersonaPlexSettings Configuration

**Files:**
- Modify: `backend/nobla/config/settings.py`
- Test: `backend/tests/test_personaplex.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_personaplex.py
"""Tests for PersonaPlex TTS integration."""
import pytest
from nobla.config.settings import PersonaPlexSettings, Settings


class TestPersonaPlexSettings:
    def test_defaults(self):
        s = PersonaPlexSettings()
        assert s.enabled is False
        assert s.server_url == "http://localhost:8880"
        assert s.timeout == 30.0
        assert s.cpu_offload is False

    def test_settings_has_personaplex(self):
        settings = Settings()
        assert hasattr(settings, "personaplex")
        assert isinstance(settings.personaplex, PersonaPlexSettings)
        assert settings.personaplex.enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_personaplex.py::TestPersonaPlexSettings -v`

- [ ] **Step 3: Implement**

Add to `backend/nobla/config/settings.py` after `PersonaSettings`:

```python
class PersonaPlexSettings(BaseModel):
    """PersonaPlex premium TTS server configuration."""

    enabled: bool = False
    server_url: str = "http://localhost:8880"
    timeout: float = 30.0
    voice_prompts_dir: str = "backend/nobla/voice/models/voice_prompts"
    cpu_offload: bool = False
```

Add to `Settings` class:

```python
    personaplex: PersonaPlexSettings = Field(default_factory=PersonaPlexSettings)
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/config/settings.py backend/tests/test_personaplex.py
git commit -m "feat(personaplex): add PersonaPlexSettings configuration"
```

---

## Task 2: PersonaPlexTTS Engine

**Files:**
- Create: `backend/nobla/voice/tts/personaplex.py`
- Test: `backend/tests/test_personaplex.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_personaplex.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


class TestPersonaPlexTTS:
    @pytest.fixture
    def engine(self, tmp_path):
        from nobla.voice.tts.personaplex import PersonaPlexTTS
        return PersonaPlexTTS(
            server_url="http://localhost:8880",
            timeout=5.0,
            voice_prompts_dir=str(tmp_path),
        )

    def test_name(self, engine):
        assert engine.name == "personaplex"

    @pytest.mark.asyncio
    async def test_is_available_when_server_up(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            assert await engine.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_when_server_down(self, engine):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
            assert await engine.is_available() is False

    @pytest.mark.asyncio
    async def test_get_voices(self, engine):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "default", "name": "Default", "language": "en"}
        ]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            voices = await engine.get_voices()
            assert len(voices) == 1
            assert voices[0].id == "default"

    @pytest.mark.asyncio
    async def test_synthesize_streams_audio(self, engine):
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter():
            for c in chunks:
                yield c
        mock_response.aiter_bytes = mock_aiter

        with patch("httpx.AsyncClient.stream", return_value=mock_response):
            result = []
            async for chunk in engine.synthesize("Hello world"):
                result.append(chunk)
            assert result == chunks

    @pytest.mark.asyncio
    async def test_synthesize_with_voice_prompt(self, engine, tmp_path):
        # Create a fake voice prompt file
        prompt_file = tmp_path / "custom.wav"
        prompt_file.write_bytes(b"fake_audio")

        chunks = [b"audio_data"]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter():
            for c in chunks:
                yield c
        mock_response.aiter_bytes = mock_aiter

        with patch("httpx.AsyncClient.stream", return_value=mock_response) as mock_stream:
            result = []
            async for chunk in engine.synthesize("Hello", voice_id="custom.wav"):
                result.append(chunk)
            assert result == chunks

    @pytest.mark.asyncio
    async def test_synthesize_missing_voice_prompt_uses_default(self, engine):
        chunks = [b"audio"]
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter():
            for c in chunks:
                yield c
        mock_response.aiter_bytes = mock_aiter

        with patch("httpx.AsyncClient.stream", return_value=mock_response):
            result = []
            async for chunk in engine.synthesize("Hello", voice_id="nonexistent.wav"):
                result.append(chunk)
            assert result == chunks  # still works, just no voice prompt

    @pytest.mark.asyncio
    async def test_is_available_caches_briefly(self, engine):
        """Health check should not hit server on every call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
            assert await engine.is_available() is True
            assert await engine.is_available() is True
            # Only one actual HTTP call due to brief caching
            assert mock_get.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement PersonaPlexTTS**

```python
# backend/nobla/voice/tts/personaplex.py
"""PersonaPlex 7B TTS engine — HTTP client for external server."""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from nobla.voice.tts.base import TTSEngine, VoiceInfo

logger = logging.getLogger(__name__)

# Cache health check for 10 seconds to avoid hammering the server.
_HEALTH_CACHE_TTL = 10.0


class PersonaPlexTTS(TTSEngine):
    """HTTP client for an external PersonaPlex TTS server."""

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        voice_prompts_dir: str | None = None,
        cpu_offload: bool = False,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._timeout = timeout
        self._voice_prompts_dir = Path(voice_prompts_dir) if voice_prompts_dir else None
        self._cpu_offload = cpu_offload
        self._health_cache: tuple[float, bool] | None = None

    @property
    def name(self) -> str:
        return "personaplex"

    async def is_available(self) -> bool:
        """Health check with brief caching."""
        if self._health_cache is not None:
            cached_time, cached_result = self._health_cache
            if time.time() - cached_time < _HEALTH_CACHE_TTL:
                return cached_result

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._server_url}/health")
                available = resp.status_code == 200
        except Exception:
            logger.debug("personaplex_health_check_failed url=%s", self._server_url)
            available = False

        self._health_cache = (time.time(), available)
        return available

    def _resolve_voice_prompt(self, voice_id: str) -> str | None:
        """Resolve voice_id to an absolute file path, or None."""
        if voice_id == "default":
            return None

        if voice_id.startswith("path:"):
            path = Path(voice_id[5:])
            if path.is_file():
                return str(path)
            logger.warning("personaplex_voice_prompt_not_found path=%s", path)
            return None

        if self._voice_prompts_dir:
            path = self._voice_prompts_dir / voice_id
            if path.is_file():
                return str(path)
            logger.warning(
                "personaplex_voice_prompt_not_found file=%s dir=%s",
                voice_id,
                self._voice_prompts_dir,
            )

        return None

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        voice_config: dict | None = None,
    ) -> AsyncIterator[bytes]:
        """Synthesize text via PersonaPlex server, streaming audio back."""
        voice_prompt_path = self._resolve_voice_prompt(voice_id)

        body: dict = {"text": text, "cpu_offload": self._cpu_offload}
        if voice_prompt_path:
            body["voice_prompt_path"] = voice_prompt_path
        if voice_config and "text_prompt" in voice_config:
            body["text_prompt"] = voice_config["text_prompt"]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._server_url}/synthesize",
                json=body,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk

    async def get_voices(self) -> list[VoiceInfo]:
        """Query PersonaPlex server for available voices."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._server_url}/voices")
                resp.raise_for_status()
                data = resp.json()
                return [
                    VoiceInfo(
                        id=v.get("id", "unknown"),
                        name=v.get("name", "Unknown"),
                        language=v.get("language", "en"),
                        gender=v.get("gender"),
                    )
                    for v in data
                ]
        except Exception:
            logger.warning("personaplex_get_voices_failed", exc_info=True)
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/tts/personaplex.py backend/tests/test_personaplex.py
git commit -m "feat(personaplex): add PersonaPlex TTS engine HTTP client"
```

---

## Task 3: App Lifespan Registration + Docker Compose

**Files:**
- Modify: `backend/nobla/gateway/app.py`
- Create: `docker/personaplex/docker-compose.yml`

- [ ] **Step 1: Add PersonaPlex registration in app.py lifespan**

In `backend/nobla/gateway/app.py`, after existing TTS engine initialization and after the Phase 3B persona block, add:

```python
    # --- Phase 3B-2: PersonaPlex premium TTS ---
    if settings.personaplex.enabled:
        from nobla.voice.tts.personaplex import PersonaPlexTTS

        personaplex_engine = PersonaPlexTTS(
            server_url=settings.personaplex.server_url,
            timeout=settings.personaplex.timeout,
            voice_prompts_dir=settings.personaplex.voice_prompts_dir,
            cpu_offload=settings.personaplex.cpu_offload,
        )
        tts_engines["personaplex"] = personaplex_engine
        logger.info("personaplex_registered url=%s", settings.personaplex.server_url)
```

- [ ] **Step 2: Create Docker Compose sample**

```yaml
# docker/personaplex/docker-compose.yml
# Sample Docker Compose for PersonaPlex 7B deployment.
# Requires NVIDIA GPU with Docker GPU support enabled.
#
# Usage:
#   docker compose up -d
#
# Then configure Nobla:
#   NOBLA_PERSONAPLEX_ENABLED=true
#   NOBLA_PERSONAPLEX_SERVER_URL=http://localhost:8880

services:
  personaplex:
    image: personaplex/personaplex-7b:latest
    ports:
      - "8880:8880"
    volumes:
      - ./voice_prompts:/data/voice_prompts
      - personaplex-models:/models
    environment:
      MODEL_PATH: /models/personaplex-7b-v1
      CPU_OFFLOAD: "false"
      HOST: "0.0.0.0"
      PORT: "8880"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8880/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  personaplex-models:
```

- [ ] **Step 3: Verify app starts without PersonaPlex (disabled by default)**

Run: `cd backend && python -c "from nobla.config.settings import Settings; s = Settings(); print(f'personaplex.enabled={s.personaplex.enabled}')"`
Expected: `personaplex.enabled=False`

- [ ] **Step 4: Run full persona+personaplex test suite**

Run: `cd backend && python -m pytest tests/test_personaplex.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/app.py docker/personaplex/docker-compose.yml
git commit -m "feat(personaplex): register engine in lifespan + Docker Compose sample"
```

---

## Summary

| Task | Component | New Lines | Test Lines |
|------|-----------|-----------|------------|
| 1 | PersonaPlexSettings | ~15 | ~15 |
| 2 | PersonaPlexTTS engine | ~120 | ~80 |
| 3 | App registration + Docker Compose | ~15 + ~30 | — |
| **Total** | | **~180** | **~95** |

3 tasks, ~15 steps, estimated ~180 new lines + ~95 test lines.
