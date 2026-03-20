"""SearxNG meta-search engine client."""

from __future__ import annotations
import httpx
import structlog
from nobla.tools.search.models import SearchResult

logger = structlog.get_logger(__name__)


class SearxNGClient:
    """Client for self-hosted SearxNG instance."""

    def __init__(self, base_url: str = "http://localhost:8888") -> None:
        self.base_url = base_url.rstrip("/")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        engines: list[str] | None = None,
    ) -> list[SearchResult]:
        params: dict = {"q": query, "format": "json"}
        if engines:
            params["engines"] = ",".join(engines)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/search", params=params,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("searxng.search_failed", error=str(exc))
            return []

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                score=float(item.get("score", 0.0)),
                source="searxng",
            ))
        return results

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/healthz")
                return resp.status_code == 200
        except Exception:
            return False
