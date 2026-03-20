"""Search orchestrator: search -> sanitize -> synthesize."""
from __future__ import annotations
import re
import structlog
from nobla.tools.search.models import SearchMode, SearchResult, SearchResponse
from nobla.tools.search.sanitizer import sanitize_results

logger = structlog.get_logger(__name__)
_ACADEMIC_TRIGGER = re.compile(r"\b(papers?|research|arxiv|scholar|study|studies)\b", re.IGNORECASE)

class SearchEngine:
    def __init__(self, searxng, brave=None, academic=None, synthesizer=None, memory=None) -> None:
        self._searxng = searxng
        self._brave = brave
        self._academic = academic
        self._synthesizer = synthesizer
        self._memory = memory

    async def search(self, query: str, mode: SearchMode = SearchMode.QUICK, use_brave: bool = False) -> SearchResponse:
        logger.info("search.start", query=query[:80], mode=mode.value)
        all_results: list[SearchResult] = []
        if mode == SearchMode.QUICK:
            all_results.extend(await self._quick_search(query, use_brave))
        elif mode == SearchMode.DEEP:
            all_results.extend(await self._deep_search(query, use_brave))
        elif mode == SearchMode.WIDE:
            all_results.extend(await self._wide_search(query, use_brave))
        elif mode == SearchMode.DEEP_WIDE:
            all_results.extend(await self._deep_search(query, use_brave))
            all_results.extend(await self._wide_search(query, use_brave))
        if self._academic and _ACADEMIC_TRIGGER.search(query):
            all_results.extend(await self._academic.arxiv_search(query, max_results=3))
        cleaned = sanitize_results(all_results)
        answer, citations = "", []
        if self._synthesizer and cleaned:
            answer, citations = await self._synthesizer.synthesize(query, cleaned)
        elif cleaned:
            answer = "\n".join(f"[{i+1}] {r.title}: {r.snippet[:100]}" for i, r in enumerate(cleaned))
        return SearchResponse(query=query, mode=mode, answer=answer, citations=citations, raw_results=cleaned)

    async def _quick_search(self, query, use_brave):
        r = await self._searxng.search(query, max_results=5)
        if use_brave and self._brave:
            r.extend(await self._brave.search(query, count=5))
        return r

    async def _deep_search(self, query, use_brave):
        r = await self._searxng.search(query, max_results=10)
        if use_brave and self._brave:
            r.extend(await self._brave.search(query, count=10))
        return r

    async def _wide_search(self, query, use_brave):
        results = []
        for sq in self._generate_sub_queries(query):
            results.extend(await self._searxng.search(sq, max_results=5))
        return results

    @staticmethod
    def _generate_sub_queries(query: str) -> list[str]:
        parts = re.split(r"\bvs\.?\b|\bversus\b|\bcompared?\s+to\b", query, flags=re.IGNORECASE)
        if len(parts) >= 2:
            return [p.strip() for p in parts if p.strip()]
        return [query]

    def available_modes(self) -> list[str]:
        return [m.value for m in SearchMode]
