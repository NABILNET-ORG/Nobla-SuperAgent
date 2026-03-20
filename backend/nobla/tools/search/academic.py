"""Academic search: ArXiv + Google Scholar via SearxNG."""

from __future__ import annotations
import xml.etree.ElementTree as ET
import httpx
import structlog
from nobla.tools.search.models import SearchResult

logger = structlog.get_logger(__name__)

_ARXIV_API = "http://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


class AcademicSearchClient:
    def __init__(self, searxng_url: str = "http://localhost:8888") -> None:
        self._searxng_url = searxng_url

    async def arxiv_search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    _ARXIV_API,
                    params={"search_query": f"all:{query}", "max_results": max_results},
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("arxiv.search_failed", error=str(exc))
            return []

        results = []
        try:
            root = ET.fromstring(resp.text)
            for entry in root.findall(f"{_ATOM_NS}entry"):
                title = entry.findtext(f"{_ATOM_NS}title", "").strip()
                link_el = entry.find(f"{_ATOM_NS}link")
                url = link_el.get("href", "") if link_el is not None else ""
                summary = entry.findtext(f"{_ATOM_NS}summary", "").strip()
                authors = [a.findtext(f"{_ATOM_NS}name", "") for a in entry.findall(f"{_ATOM_NS}author")]
                published = entry.findtext(f"{_ATOM_NS}published", "")
                snippet = f"{', '.join(authors)} ({published[:4]}): {summary[:300]}"
                results.append(SearchResult(title=title, url=url, snippet=snippet, source="arxiv"))
        except ET.ParseError:
            logger.warning("arxiv.parse_failed")
        return results

    async def scholar_search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search Google Scholar via SearxNG's scholar engine."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._searxng_url}/search",
                    params={"q": query, "format": "json", "engines": "google_scholar"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("scholar.search_failed", error=str(exc))
            return []

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("title", ""), url=item.get("url", ""),
                snippet=item.get("content", ""), source="scholar",
            ))
        return results
