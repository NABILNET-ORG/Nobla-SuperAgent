"""Tests for retrieval pipeline — hybrid search + re-ranking."""

import pytest
from nobla.memory.retrieval import RetrievalPipeline, RetrievalResult
from nobla.memory.retrieval_sources import RetrievalSource


class FakeSource(RetrievalSource):
    """Fake retrieval source for testing."""

    def __init__(self, results):
        self._results = results

    async def query(self, user_id, query_text, top_k=5):
        return self._results


@pytest.fixture
def pipeline():
    source_a = FakeSource([
        RetrievalResult(id="1", content="Alice likes Python", score=0.9, source="semantic",
                        confidence=0.8, access_count=5, recency=0.7),
        RetrievalResult(id="2", content="Bob uses Java", score=0.6, source="semantic",
                        confidence=0.6, access_count=2, recency=0.3),
    ])
    source_b = FakeSource([
        RetrievalResult(id="1", content="Alice likes Python", score=0.8, source="keyword",
                        confidence=0.8, access_count=5, recency=0.7),
        RetrievalResult(id="3", content="Alice works at Google", score=0.7, source="keyword",
                        confidence=0.9, access_count=3, recency=0.5),
    ])
    return RetrievalPipeline(sources=[source_a, source_b])


@pytest.mark.asyncio
async def test_query_returns_results(pipeline):
    results = await pipeline.query(user_id="test-user", query_text="Alice", top_k=5)
    assert isinstance(results, list)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_dedup_by_id(pipeline):
    results = await pipeline.query(user_id="test-user", query_text="Alice", top_k=5)
    ids = [r.id for r in results]
    assert len(ids) == len(set(ids))  # No duplicates


@pytest.mark.asyncio
async def test_ranking_order(pipeline):
    results = await pipeline.query(user_id="test-user", query_text="Alice", top_k=5)
    scores = [r.final_score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_top_k_limit(pipeline):
    results = await pipeline.query(user_id="test-user", query_text="Alice", top_k=2)
    assert len(results) <= 2


def test_format_context(pipeline):
    results = [
        RetrievalResult(id="1", content="Alice likes Python", score=0.9, source="semantic",
                        confidence=0.8, access_count=5, recency=0.7),
    ]
    context = pipeline.format_context(results)
    assert "Alice likes Python" in context
