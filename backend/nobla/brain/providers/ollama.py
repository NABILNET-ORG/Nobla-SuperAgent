from __future__ import annotations
import time
from typing import AsyncIterator

from ollama import AsyncClient

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


class OllamaProvider(BaseLLMProvider):
    """LLM provider backed by a local Ollama instance."""

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
    ) -> None:
        super().__init__(
            name="ollama",
            model=model,
            is_local=True,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )
        self._client = AsyncClient(host=base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_ollama_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        ollama_messages = self._to_ollama_messages(messages)
        start = time.monotonic()
        response = await self._client.chat(
            model=self.model,
            messages=ollama_messages,
            **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        tokens_input = getattr(response, "prompt_eval_count", 0) or 0
        tokens_output = getattr(response, "eval_count", 0) or 0

        content = ""
        if hasattr(response, "message") and response.message:
            content = getattr(response.message, "content", "") or ""

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        ollama_messages = self._to_ollama_messages(messages)
        async for chunk in await self._client.chat(
            model=self.model,
            messages=ollama_messages,
            stream=True,
            **kwargs,
        ):
            content = None
            if hasattr(chunk, "message") and chunk.message:
                content = getattr(chunk.message, "content", None)
            if content:
                yield content

    async def count_tokens(self, text: str) -> int:
        # Ollama does not expose a standalone token-count endpoint;
        # estimate using the standard ~0.75 words-per-token heuristic.
        return len(text.split()) * 4 // 3

    async def health_check(self) -> bool:
        try:
            await self._client.list()
            return True
        except Exception:
            return False
