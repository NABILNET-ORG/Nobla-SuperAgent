from __future__ import annotations
import time
from typing import AsyncIterator

from groq import AsyncGroq

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


# Groq llama-3.1-70b-versatile pricing per token
# $0.59 / 1M input tokens, $0.79 / 1M output tokens
_COST_INPUT = 0.59 / 1_000_000
_COST_OUTPUT = 0.79 / 1_000_000


class GroqProvider(BaseLLMProvider):
    """LLM provider backed by Groq's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile") -> None:
        super().__init__(
            name="groq",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        self._client = AsyncGroq(api_key=api_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openai_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages)
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0
        cost = self.estimate_cost(tokens_input, tokens_output)

        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        openai_messages = self._to_openai_messages(messages)
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        # Groq does not expose a standalone token-count endpoint; estimate.
        return len(text.split()) * 4 // 3

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
