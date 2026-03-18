from __future__ import annotations
import re
from enum import Enum
from typing import AsyncIterator

import structlog

from nobla.brain.base_provider import BaseLLMProvider, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


class TaskComplexity(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Patterns that indicate a simple / trivial query
_EASY_PATTERNS = re.compile(
    r"\b("
    r"hi|hello|hey|thanks|thank you|bye|goodbye|"
    r"translate|summarize|summary|define|definition|what is|what are|"
    r"who is|who are|when is|when was|where is|where was|how do you say"
    r")\b",
    re.IGNORECASE,
)

# Patterns that indicate a complex / engineering task
_HARD_PATTERNS = re.compile(
    r"\b("
    r"write code|write a|implement|function|class|algorithm|"
    r"debug|fix the bug|refactor|optimize|regex|regular expression|"
    r"math|equation|proof|derive|integral|derivative|"
    r"create a program|build a|design a system|architect"
    r")\b",
    re.IGNORECASE,
)

# Provider preference lists per complexity tier
_PREFERENCE: dict[TaskComplexity, list[str]] = {
    TaskComplexity.EASY: ["groq", "gemini", "ollama"],
    TaskComplexity.MEDIUM: ["gemini", "groq", "ollama"],
    TaskComplexity.HARD: ["gemini", "ollama", "groq"],
}


class LLMRouter:
    """
    Routes LLM requests to the most appropriate provider based on task
    complexity, provider health, and a configurable fallback chain.
    """

    def __init__(
        self,
        providers: dict[str, BaseLLMProvider],
        fallback_chain: list[str],
    ) -> None:
        self.providers = providers
        self.fallback_chain = fallback_chain

    # ------------------------------------------------------------------
    # Complexity classification
    # ------------------------------------------------------------------

    def classify_complexity(self, message: str) -> TaskComplexity:
        """
        Classify a user message into EASY / MEDIUM / HARD.

        Decision order:
        1. HARD patterns take priority (code, algorithms, math).
        2. EASY patterns detected next (greetings, definitions, simple ops).
        3. Short messages (<=6 words) default to EASY.
        4. Everything else is MEDIUM.
        """
        if _HARD_PATTERNS.search(message):
            return TaskComplexity.HARD
        if _EASY_PATTERNS.search(message):
            return TaskComplexity.EASY
        if len(message.split()) <= 6:
            return TaskComplexity.EASY
        return TaskComplexity.MEDIUM

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def _select_provider_name(self, complexity: TaskComplexity) -> list[str]:
        """Return the ordered preference list for a given complexity tier."""
        return _PREFERENCE.get(complexity, self.fallback_chain)

    async def _get_healthy_provider(
        self, preferred: list[str]
    ) -> BaseLLMProvider | None:
        """
        Walk the preferred list (then the global fallback chain) and return
        the first provider that passes a health check.
        """
        # Combine preferred order with any remaining providers from fallback_chain
        candidates = list(preferred)
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)

        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                continue
            try:
                healthy = await provider.health_check()
                if healthy:
                    logger.info("router.provider_selected", provider=name)
                    return provider
                logger.warning("router.provider_unhealthy", provider=name)
            except Exception as exc:
                logger.warning("router.provider_health_check_error", provider=name, error=str(exc))

        return None

    # ------------------------------------------------------------------
    # Public routing API
    # ------------------------------------------------------------------

    async def route(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """
        Classify the last user message, pick the best healthy provider,
        and return a complete LLMResponse.

        Raises RuntimeError if every provider in the chain is unavailable.
        """
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)

        logger.info(
            "router.routing",
            complexity=complexity.value,
            preferred=preferred,
            message_preview=last_user[:80],
        )

        provider = await self._get_healthy_provider(preferred)
        if provider is None:
            raise RuntimeError("All LLM providers failed health checks")

        return await provider.generate(messages, **kwargs)

    async def stream_route(
        self, messages: list[LLMMessage], **kwargs
    ) -> tuple[str, AsyncIterator[str]]:
        """
        Like route() but returns a (provider_name, async_iterator) tuple
        so the caller can stream tokens as they arrive.

        Raises RuntimeError if every provider in the chain is unavailable.
        """
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        complexity = self.classify_complexity(last_user)
        preferred = self._select_provider_name(complexity)

        logger.info(
            "router.stream_routing",
            complexity=complexity.value,
            preferred=preferred,
        )

        provider = await self._get_healthy_provider(preferred)
        if provider is None:
            raise RuntimeError("All LLM providers failed health checks")

        return provider.name, provider.stream(messages, **kwargs)
