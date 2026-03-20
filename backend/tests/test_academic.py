import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nobla.tools.search.academic import AcademicSearchClient


@pytest.fixture
def client():
    return AcademicSearchClient(searxng_url="http://localhost:8888")


@pytest.mark.asyncio
async def test_arxiv_search(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '''<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Neural Networks</title>
        <link href="http://arxiv.org/abs/2301.00001"/>
        <summary>A paper about neural nets.</summary>
        <author><name>John Doe</name></author>
        <published>2023-01-01T00:00:00Z</published>
      </entry>
    </feed>'''
    with patch("nobla.tools.search.academic.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        results = await client.arxiv_search("neural networks")
    assert len(results) == 1
    assert results[0].source == "arxiv"
    assert "Neural Networks" in results[0].title


@pytest.mark.asyncio
async def test_arxiv_handles_error(client):
    with patch("nobla.tools.search.academic.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        results = await client.arxiv_search("test")
    assert results == []
