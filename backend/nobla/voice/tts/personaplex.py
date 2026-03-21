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
        self._voice_prompts_dir = (
            Path(voice_prompts_dir) if voice_prompts_dir else None
        )
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
            logger.debug(
                "personaplex_health_check_failed url=%s", self._server_url
            )
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
            logger.warning(
                "personaplex_voice_prompt_not_found path=%s", path
            )
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
