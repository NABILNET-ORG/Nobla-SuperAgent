import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.tools.search.engine import SearchEngine
from nobla.tools.search.models import SearchMode, SearchResult

@pytest.fixture
def engine():
    return SearchEngine(searxng=MagicMock(), brave=MagicMock(), academic=MagicMock(), synthesizer=MagicMock(), memory=None)

@pytest.mark.asyncio
async def test_quick_search(engine):
    engine._searxng.search = AsyncMock(return_value=[SearchResult(title="R1", url="https://r1.com", snippet="Result one", source="searxng")])
    engine._synthesizer.synthesize = AsyncMock(return_value=("Answer [1].", []))
    response = await engine.search("test query", mode=SearchMode.QUICK)
    assert response.answer == "Answer [1]."

@pytest.mark.asyncio
async def test_wide_search(engine):
    engine._searxng.search = AsyncMock(return_value=[SearchResult(title="R", url="https://r.com", snippet="Result", source="searxng")])
    engine._synthesizer.synthesize = AsyncMock(return_value=("Wide.", []))
    await engine.search("compare X vs Y", mode=SearchMode.WIDE)
    assert engine._searxng.search.call_count >= 2

@pytest.mark.asyncio
async def test_brave_premium(engine):
    engine._brave.search = AsyncMock(return_value=[SearchResult(title="B", url="https://b.com", snippet="Brave", source="brave")])
    engine._searxng.search = AsyncMock(return_value=[])
    engine._synthesizer.synthesize = AsyncMock(return_value=("Brave.", []))
    await engine.search("test", mode=SearchMode.QUICK, use_brave=True)
    engine._brave.search.assert_called_once()

@pytest.mark.asyncio
async def test_academic_trigger(engine):
    engine._academic.arxiv_search = AsyncMock(return_value=[SearchResult(title="Paper", url="https://arxiv.org/1", snippet="Abstract", source="arxiv")])
    engine._searxng.search = AsyncMock(return_value=[])
    engine._synthesizer.synthesize = AsyncMock(return_value=("Paper.", []))
    await engine.search("find papers on transformers", mode=SearchMode.DEEP)
    engine._academic.arxiv_search.assert_called_once()
