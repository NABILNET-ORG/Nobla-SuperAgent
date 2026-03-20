import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nobla.tools.search.searxng import SearxNGClient
from nobla.tools.search.models import SearchResult


@pytest.fixture
def client():
    return SearxNGClient(base_url="http://localhost:8888")


@pytest.mark.asyncio
async def test_search_returns_results(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"title": "Python", "url": "https://python.org", "content": "Python language"},
            {"title": "Rust", "url": "https://rust-lang.org", "content": "Rust language"},
        ]
    }
    with patch("nobla.tools.search.searxng.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        results = await client.search("python programming")
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].source == "searxng"


@pytest.mark.asyncio
async def test_search_handles_error(client):
    with patch("nobla.tools.search.searxng.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        results = await client.search("test")
    assert results == []


@pytest.mark.asyncio
async def test_search_with_engines(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    with patch("nobla.tools.search.searxng.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        await client.search("test", engines=["google", "bing"])
    call_kwargs = mock_client.get.call_args
    assert "google,bing" in str(call_kwargs)
