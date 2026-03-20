import pytest
from unittest.mock import AsyncMock
from nobla.brain.router import LLMRouter, TaskComplexity
from nobla.brain.base_provider import BaseLLMProvider, LLMResponse, LLMMessage
from nobla.brain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


def make_mock_provider(name: str, healthy: bool = True) -> BaseLLMProvider:
    provider = AsyncMock(spec=BaseLLMProvider)
    provider.name = name
    provider.model = f"{name}-model"
    provider.is_local = (name == "ollama")
    provider.health_check = AsyncMock(return_value=healthy)
    provider.generate = AsyncMock(return_value=LLMResponse(
        content=f"Response from {name}", model=f"{name}-model",
        tokens_input=10, tokens_output=20, cost_usd=0.0, latency_ms=100,
    ))
    return provider


def test_classify_easy_task():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("hi") == TaskComplexity.EASY
    assert router.classify_complexity("translate this") == TaskComplexity.EASY


def test_classify_hard_task():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("write a python function that sorts") == TaskComplexity.HARD


def test_classify_medium_task():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("analyze the quarterly revenue data for trends") == TaskComplexity.MEDIUM


@pytest.mark.asyncio
async def test_router_uses_fallback_on_failure():
    gemini = make_mock_provider("gemini", healthy=False)
    groq = make_mock_provider("groq", healthy=True)
    router = LLMRouter(
        providers={"gemini": gemini, "groq": groq},
        fallback_chain=["gemini", "groq"],
    )
    result = await router.route([LLMMessage(role="user", content="hello")])
    assert result.content == "Response from groq"


@pytest.mark.asyncio
async def test_router_all_providers_fail():
    gemini = make_mock_provider("gemini", healthy=False)
    router = LLMRouter(providers={"gemini": gemini}, fallback_chain=["gemini"])
    with pytest.raises(RuntimeError, match="All LLM providers failed"):
        await router.route([LLMMessage(role="user", content="hello")])


def test_classify_with_technical_keywords():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("explain how neural network architectures handle training data in production") == TaskComplexity.MEDIUM
    assert router.classify_complexity("write a recursive fibonacci function") == TaskComplexity.HARD

def test_classify_length_signal():
    router = LLMRouter(providers={}, fallback_chain=[])
    assert router.classify_complexity("ok") == TaskComplexity.EASY
    long_msg = "Can you analyze the trade-offs between microservices and monolithic architectures for our use case"
    assert router.classify_complexity(long_msg) == TaskComplexity.MEDIUM

@pytest.mark.asyncio
async def test_router_skips_circuit_broken_provider():
    gemini = make_mock_provider("gemini", healthy=True)
    groq = make_mock_provider("groq", healthy=True)
    cb_gemini = CircuitBreaker("gemini", CircuitBreakerConfig(failure_threshold=1))
    cb_gemini.record_failure()
    router = LLMRouter(
        providers={"gemini": gemini, "groq": groq},
        fallback_chain=["gemini", "groq"],
        circuit_breakers={"gemini": cb_gemini},
    )
    result = await router.route([LLMMessage(role="user", content="hello")])
    assert result.content == "Response from groq"
    gemini.generate.assert_not_called()

@pytest.mark.asyncio
async def test_router_records_circuit_breaker_failure():
    gemini = make_mock_provider("gemini", healthy=True)
    gemini.generate = AsyncMock(side_effect=Exception("API error"))
    groq = make_mock_provider("groq", healthy=True)
    cb_gemini = CircuitBreaker("gemini", CircuitBreakerConfig(failure_threshold=3))
    router = LLMRouter(
        providers={"gemini": gemini, "groq": groq},
        fallback_chain=["gemini", "groq"],
        circuit_breakers={"gemini": cb_gemini},
    )
    result = await router.route([LLMMessage(role="user", content="analyze the quarterly revenue data for trends")])
    assert result.content == "Response from groq"
    assert cb_gemini.failure_count == 1

def test_preference_includes_new_providers():
    router = LLMRouter(providers={}, fallback_chain=[])
    hard_prefs = router._select_provider_name(TaskComplexity.HARD)
    assert "anthropic" in hard_prefs
    assert "openai" in hard_prefs
