"""LLM-powered search result synthesis with source citations."""
from __future__ import annotations
import re
from nobla.brain.base_provider import LLMMessage
from nobla.tools.search.models import SearchResult, Citation
import structlog

logger = structlog.get_logger(__name__)
_CITATION_RE = re.compile(r"\[(\d+)]")

class SearchSynthesizer:
    def __init__(self, router) -> None:
        self._router = router

    def _build_prompt(self, query: str, results: list[SearchResult]) -> str:
        sources = []
        for i, r in enumerate(results, 1):
            sources.append(f"[{i}] {r.title}\n    URL: {r.url}\n    {r.snippet}")
        return ("Answer the user's question using ONLY the sources below. "
                "Cite sources using [N] notation. If sources are insufficient, say so.\n\n"
                f"Sources:\n" + "\n\n".join(sources) + f"\n\nQuestion: {query}")

    def _extract_citations(self, text: str, results: list[SearchResult]) -> list[Citation]:
        cited = set(int(m) for m in _CITATION_RE.findall(text))
        return [Citation(index=idx, title=results[idx-1].title, url=results[idx-1].url, snippet=results[idx-1].snippet[:200])
                for idx in sorted(cited) if 1 <= idx <= len(results)]

    async def synthesize(self, query: str, results: list[SearchResult]) -> tuple[str, list[Citation]]:
        if not results:
            return "No search results found.", []
        prompt = self._build_prompt(query, results)
        try:
            response = await self._router.route([LLMMessage(role="user", content=prompt)])
            answer = response.content
        except Exception as exc:
            logger.error("synthesizer.failed", error=str(exc))
            return f"Search found {len(results)} results but synthesis failed.", []
        return answer, self._extract_citations(answer, results)
