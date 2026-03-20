import pytest
from nobla.brain.token_counter import TokenCounter

def test_count_openai_tokens():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="openai", model="gpt-4o")
    assert isinstance(count, int)
    assert count > 0

def test_count_anthropic_tokens():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="anthropic", model="claude-sonnet-4-20250514")
    assert isinstance(count, int)
    assert count > 0

def test_count_fallback_estimation():
    counter = TokenCounter()
    count = counter.count("Hello, world!", provider="unknown", model="some-model")
    assert isinstance(count, int)
    assert count > 0

def test_empty_string_returns_zero():
    counter = TokenCounter()
    assert counter.count("", provider="openai", model="gpt-4o") == 0

def test_cost_estimate():
    counter = TokenCounter()
    cost = counter.estimate_cost(input_tokens=1000, output_tokens=500, provider="openai", model="gpt-4o")
    assert isinstance(cost, float)
    assert cost > 0

def test_cost_estimate_free_provider():
    counter = TokenCounter()
    cost = counter.estimate_cost(input_tokens=1000, output_tokens=500, provider="ollama", model="llama3.1")
    assert cost == 0.0
