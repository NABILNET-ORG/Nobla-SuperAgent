import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nobla.tools.search.brave import BraveSearchClient
from nobla.tools.search.models import SearchResult


@pytest.fixture
def client():
    return BraveSearchClient(api_key="test-brave-key")


@pytest.mark.asyncio
async def test_search_returns_results(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "web": {"results": [
            {"title": "Python", "url": "https://python.org",
             "description": "Python language", "extra_snippets": ["More info"]},
        ]}
    }
    with patch("nobla.tools.search.brave.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        results = await client.search("python")
    assert len(results) == 1
    assert results[0].source == "brave"
    assert "More info" in results[0].snippet


@pytest.mark.asyncio
async def test_search_without_api_key():
    client = BraveSearchClient(api_key="")
    results = await client.search("test")
    assert results == []


@pytest.mark.asyncio
async def test_search_sends_auth_header(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"web": {"results": []}}
    with patch("nobla.tools.search.brave.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        await client.search("test")
    call_kwargs = mock_client.get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("X-Subscription-Token") == "test-brave-key"
