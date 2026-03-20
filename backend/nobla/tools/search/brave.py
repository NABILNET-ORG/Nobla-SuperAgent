"""Brave Search LLM Context API client."""

from __future__ import annotations
import httpx
import structlog
from nobla.tools.search.models import SearchResult

logger = structlog.get_logger(__name__)

_BRAVE_API = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchClient:
    """Client for Brave Search API with LLM context support."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("brave.no_api_key")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    _BRAVE_API,
                    headers={"X-Subscription-Token": self._api_key},
                    params={"q": query, "count": count, "extra_snippets": True},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("brave.search_failed", error=str(exc))
            return []

        results = []
        for item in data.get("web", {}).get("results", []):
            snippet = item.get("description", "")
            extras = item.get("extra_snippets", [])
            if extras:
                snippet += " " + " ".join(extras)
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=snippet,
                source="brave",
            ))
        return results
