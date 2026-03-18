import pytest
from nobla.brain.base_provider import BaseLLMProvider, LLMResponse, LLMMessage


def test_llm_response_total_tokens():
    resp = LLMResponse(content="Hi", model="test", tokens_input=5, tokens_output=3, cost_usd=0.0, latency_ms=100)
    assert resp.total_tokens == 8


def test_base_provider_is_abstract():
    with pytest.raises(TypeError):
        BaseLLMProvider(name="test", model="test")


def test_estimate_cost():
    class DummyProvider(BaseLLMProvider):
        async def generate(self, messages, **kwargs): pass
        async def stream(self, messages, **kwargs): yield ""
        async def count_tokens(self, text): return 0
        async def health_check(self): return True

    p = DummyProvider(name="test", model="test", cost_per_input_token=0.001, cost_per_output_token=0.002)
    assert p.estimate_cost(100, 50) == pytest.approx(0.2)


def test_llm_message_creation():
    msg = LLMMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
