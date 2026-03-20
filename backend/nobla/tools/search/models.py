"""Data models for the search subsystem."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class SearchMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"
    WIDE = "wide"
    DEEP_WIDE = "deep_wide"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    source: str = ""  # "searxng", "brave", "arxiv", "scholar"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
            "source": self.source,
        }


@dataclass
class Citation:
    index: int
    title: str
    url: str
    snippet: str


@dataclass
class SearchResponse:
    query: str
    mode: SearchMode
    answer: str
    citations: list[Citation] = field(default_factory=list)
    raw_results: list[SearchResult] = field(default_factory=list)
    from_memory: bool = False

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "mode": self.mode.value,
            "answer": self.answer,
            "citations": [
                {"index": c.index, "title": c.title, "url": c.url, "snippet": c.snippet}
                for c in self.citations
            ],
            "from_memory": self.from_memory,
        }
