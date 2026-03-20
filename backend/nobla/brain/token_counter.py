from __future__ import annotations
import tiktoken

_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {"gpt-4o": (2.50/1_000_000, 10.00/1_000_000), "gpt-4o-mini": (0.15/1_000_000, 0.60/1_000_000)},
    "anthropic": {"claude-sonnet-4-20250514": (3.00/1_000_000, 15.00/1_000_000), "claude-haiku-4-5-20251001": (0.80/1_000_000, 4.00/1_000_000)},
    "gemini": {"gemini-2.0-flash": (0.075/1_000_000, 0.30/1_000_000)},
    "groq": {"llama-3.1-70b-versatile": (0.59/1_000_000, 0.79/1_000_000)},
    "deepseek": {"deepseek-chat": (0.14/1_000_000, 0.28/1_000_000)},
    "ollama": {},
}
_DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "openai": (2.50/1_000_000, 10.00/1_000_000),
    "anthropic": (3.00/1_000_000, 15.00/1_000_000),
    "deepseek": (0.14/1_000_000, 0.28/1_000_000),
}

class TokenCounter:
    def __init__(self) -> None:
        self._fallback_enc = tiktoken.get_encoding("cl100k_base")
        self._enc_cache: dict[str, tiktoken.Encoding] = {}

    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        if model not in self._enc_cache:
            try:
                self._enc_cache[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                self._enc_cache[model] = self._fallback_enc
        return self._enc_cache[model]

    def count(self, text: str, provider: str, model: str) -> int:
        if not text:
            return 0
        if provider in ("openai", "anthropic", "deepseek", "groq"):
            return len(self._get_encoding(model).encode(text))
        return len(self._fallback_enc.encode(text))

    def estimate_cost(self, input_tokens: int, output_tokens: int, provider: str, model: str) -> float:
        provider_pricing = _PRICING.get(provider, {})
        if not provider_pricing:
            input_cost, output_cost = _DEFAULT_PRICING.get(provider, (0.0, 0.0))
        else:
            input_cost, output_cost = provider_pricing.get(model, _DEFAULT_PRICING.get(provider, (0.0, 0.0)))
        return (input_tokens * input_cost) + (output_tokens * output_cost)
