from __future__ import annotations

import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse


# Claude Sonnet pricing per token
# $3.00 / 1M input tokens, $15.00 / 1M output tokens
_COST_INPUT = 3.00 / 1_000_000
_COST_OUTPUT = 15.00 / 1_000_000


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        super().__init__(
            name="anthropic",
            model=model,
            is_local=False,
            cost_per_input_token=_COST_INPUT,
            cost_per_output_token=_COST_OUTPUT,
        )
        self._client = AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_anthropic_messages(
        messages: list[LLMMessage],
    ) -> tuple[str, list[dict]]:
        """Separate system prompt from conversation messages.

        Anthropic requires ``system`` as a top-level parameter, not as a
        message in the list.
        """
        system = ""
        msgs: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                msgs.append({"role": msg.role, "content": msg.content})
        return system, msgs

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        system, msgs = self._to_anthropic_messages(messages)
        start = time.monotonic()
        response = await self._client.messages.create(
            model=self.model,
            messages=msgs,
            system=system or "You are a helpful assistant.",
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        content = response.content[0].text if response.content else ""
        tokens_input = response.usage.input_tokens
        tokens_output = response.usage.output_tokens
        cost = self.estimate_cost(tokens_input, tokens_output)

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        system, msgs = self._to_anthropic_messages(messages)
        async with self._client.messages.stream(
            model=self.model,
            messages=msgs,
            system=system or "You are a helpful assistant.",
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def count_tokens(self, text: str) -> int:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))

    async def health_check(self) -> bool:
        try:
            await self._client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                system="Reply pong.",
                max_tokens=5,
            )
            return True
        except Exception:
            return False
