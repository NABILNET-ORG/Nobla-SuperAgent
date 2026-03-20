from __future__ import annotations
import time
from typing import AsyncIterator

import google.generativeai as genai

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


# Gemini 2.0 Flash pricing per token (as of 2026)
# $0.075 / 1M input tokens, $0.30 / 1M output tokens
_COST_INPUT = 0.075 / 1_000_000
_COST_OUTPUT = 0.30 / 1_000_000


class GeminiProvider(BaseLLMProvider):
    """LLM provider backed by Google Gemini via google-generativeai."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        super().__init__(
            name="gemini",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_gemini_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """Convert LLMMessage list to the format expected by Gemini."""
        result = []
        for msg in messages:
            # Gemini uses "model" for assistant, "user" for everything else
            role = "model" if msg.role == "assistant" else "user"
            result.append({"role": role, "parts": [msg.content]})
        return result

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        gemini_messages = self._to_gemini_messages(messages)
        start = time.monotonic()
        response = await self._client.generate_content_async(gemini_messages, **kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = getattr(response, "usage_metadata", None)
        tokens_input = getattr(usage, "prompt_token_count", 0) or 0
        tokens_output = getattr(usage, "candidates_token_count", 0) or 0

        cost = self.estimate_cost(tokens_input, tokens_output)
        return LLMResponse(
            content=response.text,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        gemini_messages = self._to_gemini_messages(messages)
        response = await self._client.generate_content_async(
            gemini_messages, stream=True, **kwargs
        )
        async for chunk in response:
            text = getattr(chunk, "text", None)
            if text:
                yield text

    async def count_tokens(self, text: str) -> int:
        result = await self._client.count_tokens_async(text)
        return result.total_tokens

    async def health_check(self) -> bool:
        try:
            await self._client.count_tokens_async("ping")
            return True
        except Exception:
            return False
