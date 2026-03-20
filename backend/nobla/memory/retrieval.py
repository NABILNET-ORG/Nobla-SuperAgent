"""Retrieval pipeline — merge + re-rank orchestration.

Queries multiple retrieval sources in parallel, merges results,
deduplicates by ID, and re-ranks using a weighted formula:
  0.4*similarity + 0.3*recency + 0.2*frequency + 0.1*confidence
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Re-ranking weights
W_SIMILARITY = 0.4
W_RECENCY = 0.3
W_FREQUENCY = 0.2
W_CONFIDENCE = 0.1

# Normalize frequency: cap at this value
MAX_ACCESS_COUNT = 50


@dataclass
class RetrievalResult:
    """A single retrieval result from any source."""

    id: str
    content: str
    score: float  # Raw similarity/relevance score (0-1)
    source: str  # Which source produced this result
    confidence: float = 0.5
    access_count: int = 0
    recency: float = 0.5  # 0=old, 1=recent
    final_score: float = 0.0  # Computed after re-ranking


class RetrievalPipeline:
    """Orchestrates parallel retrieval, merge, dedup, and re-ranking."""

    def __init__(self, sources: list = None):
        self._sources = sources or []

    async def query(
        self,
        user_id: str,
        query_text: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Query all sources in parallel, merge, dedup, re-rank, return top-K."""
        if not self._sources:
            return []

        # 1. Parallel query all sources
        tasks = [
            source.query(user_id, query_text, top_k)
            for source in self._sources
        ]
        source_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2. Collect all results
        all_results: list[RetrievalResult] = []
        for result in source_results:
            if isinstance(result, Exception):
                logger.warning("Retrieval source failed: %s", result)
                continue
            all_results.extend(result)

        # 3. Dedup by ID (keep highest raw score)
        seen: dict[str, RetrievalResult] = {}
        for r in all_results:
            if r.id not in seen or r.score > seen[r.id].score:
                seen[r.id] = r
        deduped = list(seen.values())

        # 4. Re-rank
        for r in deduped:
            freq_normalized = min(r.access_count / MAX_ACCESS_COUNT, 1.0)
            r.final_score = (
                W_SIMILARITY * r.score
                + W_RECENCY * r.recency
                + W_FREQUENCY * freq_normalized
                + W_CONFIDENCE * r.confidence
            )

        # 5. Sort by final score descending
        deduped.sort(key=lambda r: r.final_score, reverse=True)

        return deduped[:top_k]

    def format_context(self, results: list[RetrievalResult]) -> str:
        """Format retrieval results into a context block for the LLM."""
        if not results:
            return ""

        lines = []
        for r in results:
            lines.append(f"- {r.content}")
        return "\n".join(lines)
