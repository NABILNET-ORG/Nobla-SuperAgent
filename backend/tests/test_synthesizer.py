import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.tools.search.synthesizer import SearchSynthesizer
from nobla.tools.search.models import SearchResult
from nobla.brain.base_provider import LLMResponse

@pytest.fixture
def synthesizer():
    return SearchSynthesizer(router=MagicMock())

def test_build_prompt(synthesizer):
    results = [SearchResult(title="Python", url="https://python.org", snippet="Python is a language")]
    prompt = synthesizer._build_prompt("What is Python?", results)
    assert "[1]" in prompt
    assert "Python is a language" in prompt

def test_extract_citations(synthesizer):
    results = [SearchResult(title="A", url="https://a.com", snippet="A"), SearchResult(title="B", url="https://b.com", snippet="B")]
    citations = synthesizer._extract_citations("Text [1] and [2].", results)
    assert len(citations) == 2
    assert citations[0].index == 1

def test_extract_citations_handles_missing(synthesizer):
    results = [SearchResult(title="A", url="https://a.com", snippet="A")]
    citations = synthesizer._extract_citations("Text [1] and [5].", results)
    assert len(citations) == 1

@pytest.mark.asyncio
async def test_synthesize(synthesizer):
    mock_resp = LLMResponse(content="Python is popular [1].", model="g", tokens_input=10, tokens_output=5, cost_usd=0, latency_ms=100)
    synthesizer._router.route = AsyncMock(return_value=mock_resp)
    results = [SearchResult(title="Python", url="https://python.org", snippet="Python language")]
    answer, citations = await synthesizer.synthesize("What is Python?", results)
    assert "Python" in answer
    assert len(citations) == 1

@pytest.mark.asyncio
async def test_synthesize_empty(synthesizer):
    answer, citations = await synthesizer.synthesize("test", [])
    assert "No search results" in answer
