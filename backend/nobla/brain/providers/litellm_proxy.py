from __future__ import annotations

import time
from typing import AsyncIterator

import litellm

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


class LiteLLMProvider(BaseLLMProvider):
    """Universal LLM provider backed by LiteLLM.

    LiteLLM supports 100+ LLM providers through a unified interface.
    Pass the model string in LiteLLM format, e.g.:
      - ``together_ai/meta-llama/Llama-3-70b``
      - ``replicate/llama-2-70b-chat``
      - ``bedrock/anthropic.claude-3-sonnet``
    """

    def __init__(self, model: str, api_key: str | None = None) -> None:
        super().__init__(
            name="litellm",
            model=model,
            is_local=False,
        )
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_messages(messages: list[LLMMessage]) -> list[dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        start = time.monotonic()
        response = await litellm.acompletion(
            model=self.model,
            messages=self._to_messages(messages),
            api_key=self._api_key,
            **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0

        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        response = await litellm.acompletion(
            model=self.model,
            messages=self._to_messages(messages),
            api_key=self._api_key,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            if chunk.choices:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        # Approximate; LiteLLM covers many models with varying tokenizers.
        return len(text.split()) * 4 // 3

    async def health_check(self) -> bool:
        try:
            await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                api_key=self._api_key,
                max_tokens=5,
            )
            return True
        except Exception:
            return False
