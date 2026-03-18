import pytest
from unittest.mock import AsyncMock
from nobla.brain.router import LLMRouter, TaskComplexity
from nobla.brain.base_provider import BaseLLMProvider, LLMResponse, LLMMessage


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
