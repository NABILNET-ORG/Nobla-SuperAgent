from __future__ import annotations
import re
from enum import Enum
from typing import AsyncIterator

import structlog

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse
from nobla.brain.circuit_breaker import CircuitBreaker

logger = structlog.get_logger(__name__)


class TaskComplexity(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


_EASY_PATTERNS = re.compile(
    r"\b("
    r"hi|hello|hey|thanks|thank you|bye|goodbye|"
    r"translate|summarize|summary|define|definition|what is|what are|"
    r"who is|who are|when is|when was|where is|where was|how do you say"
    r")\b",
    re.IGNORECASE,
)

_HARD_PATTERNS = re.compile(
    r"\b("
    r"write code|write a|implement|function|class|algorithm|"
    r"debug|fix the bug|refactor|optimize|regex|regular expression|"
    r"math|equation|proof|derive|integral|derivative|"
    r"create a program|build a|design a system|architect"
    r")\b",
    re.IGNORECASE,
)

_TECHNICAL_KEYWORDS = re.compile(
    r"\b("
    r"api|database|sql|docker|kubernetes|deploy|server|"
    r"authentication|encryption|pipeline|microservice|"
    r"neural network|machine learning|training"
    r")\b",
    re.IGNORECASE,
)

_PREFERENCE: dict[TaskComplexity, list[str]] = {
    TaskComplexity.EASY: ["groq", "gemini", "ollama"],
    TaskComplexity.MEDIUM: ["gemini", "deepseek", "groq", "ollama"],
    TaskComplexity.HARD: ["anthropic", "openai", "gemini", "ollama"],
}


class LLMRouter:
    """Routes LLM requests based on complexity, health, and circuit breakers."""

    def __init__(
        self,
        providers: dict[str, BaseLLMProvider],
        fallback_chain: list[str],
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self.providers = providers
        self.fallback_chain = fallback_chain
        self.circuit_breakers = circuit_breakers or {}

    def classify_complexity(self, message: str) -> TaskComplexity:
        if _HARD_PATTERNS.search(message):
            return TaskComplexity.HARD
        if _EASY_PATTERNS.search(message):
            return TaskComplexity.EASY
        if len(message.split()) <= 6:
            return TaskComplexity.EASY

        score = 0.0
        word_count = len(message.split())
        if word_count > 30:
            score += 0.3
        if _TECHNICAL_KEYWORDS.search(message):
            score += 0.3
        if "?" in message and word_count > 15:
            score += 0.1

        if score >= 0.6:
            return TaskComplexity.HARD
        return TaskComplexity.MEDIUM

    def _select_provider_name(self, complexity: TaskComplexity) -> list[str]:
        return _PREFERENCE.get(complexity, self.fallback_chain)

    def _build_candidates(self, preferred: list[str]) -> list[str]:
        candidates = list(preferred)
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)
        return candidates

    async def route(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        # --- Persona integration: extract persona kwargs before forwarding ---
        system_prompt_extra: str | None = kwargs.pop("system_prompt_extra", None)
        temperature_bias: float | None = kwargs.pop("temperature_bias", None)

        if system_prompt_extra:
            messages = [
                LLMMessage(role="system", content=system_prompt_extra),
                *messages,
            ]

        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)
        candidates = self._build_candidates(preferred)

        logger.info("router.routing", complexity=complexity.value, preferred=preferred, message_preview=last_user[:80])

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue

            cb = self.circuit_breakers.get(name)
            if cb and not cb.is_available():
                logger.info("router.circuit_open", provider=name)
                continue

            try:
                healthy = await provider.health_check()
                if not healthy:
                    continue

                # Apply temperature bias relative to provider default
                call_kwargs = dict(kwargs)
                if temperature_bias is not None:
                    base_temp = getattr(provider, "default_temperature", 1.0)
                    call_kwargs["temperature"] = max(
                        0.0, min(2.0, base_temp + temperature_bias)
                    )

                result = await provider.generate(messages, **call_kwargs)
                if cb:
                    cb.record_success()
                return result
            except Exception as exc:
                logger.warning("router.provider_failed", provider=name, error=str(exc))
                if cb:
                    cb.record_failure()
                continue

        raise RuntimeError("All LLM providers failed health checks")

    async def stream_route(
        self, messages: list[LLMMessage], **kwargs
    ) -> tuple[str, AsyncIterator[str]]:
        # --- Persona integration: extract persona kwargs before forwarding ---
        system_prompt_extra: str | None = kwargs.pop("system_prompt_extra", None)
        temperature_bias: float | None = kwargs.pop("temperature_bias", None)

        if system_prompt_extra:
            messages = [
                LLMMessage(role="system", content=system_prompt_extra),
                *messages,
            ]

        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)
        candidates = self._build_candidates(preferred)

        logger.info("router.stream_routing", complexity=complexity.value, preferred=preferred)

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue

            cb = self.circuit_breakers.get(name)
            if cb and not cb.is_available():
                continue

            try:
                healthy = await provider.health_check()
                if not healthy:
                    continue

                # Apply temperature bias relative to provider default
                call_kwargs = dict(kwargs)
                if temperature_bias is not None:
                    base_temp = getattr(provider, "default_temperature", 1.0)
                    call_kwargs["temperature"] = max(
                        0.0, min(2.0, base_temp + temperature_bias)
                    )

                return provider.name, provider.stream(messages, **call_kwargs)
            except Exception as exc:
                logger.warning("router.stream_provider_failed", provider=name, error=str(exc))
                if cb:
                    cb.record_failure()
                continue

        raise RuntimeError("All LLM providers failed health checks")
