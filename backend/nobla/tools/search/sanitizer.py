"""Search result sanitization -- HTML stripping, size capping, injection detection."""

from __future__ import annotations
import re
from nobla.tools.search.models import SearchResult

_HTML_TAG = re.compile(r"<[^>]+>")
_SCRIPT_TAG = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)

_INJECTION_PATTERNS = re.compile(
    r"(?i)("
    r"ignore\s+(all\s+)?previous\s+instructions|"
    r"output\s+your\s+system\s+prompt|"
    r"you\s+are\s+now\s+DAN|"
    r"disregard\s+(all\s+)?prior|"
    r"forget\s+everything|"
    r"new\s+instructions\s*:|"
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions"
    r")"
)


def sanitize_snippet(text: str, max_tokens: int = 500) -> str:
    text = _SCRIPT_TAG.sub("", text)
    text = _HTML_TAG.sub("", text)
    words = text.split()
    if len(words) > max_tokens:
        words = words[:max_tokens]
    return " ".join(words)


def _is_injection(text: str) -> bool:
    return bool(_INJECTION_PATTERNS.search(text))


def sanitize_results(
    results: list[SearchResult],
    max_snippet_tokens: int = 500,
    max_total_tokens: int = 3000,
) -> list[SearchResult]:
    cleaned = []
    total_tokens = 0

    for r in results:
        if _is_injection(r.snippet) or _is_injection(r.title):
            continue
        snippet = sanitize_snippet(r.snippet, max_snippet_tokens)
        snippet_tokens = len(snippet.split())
        if total_tokens + snippet_tokens > max_total_tokens:
            break
        total_tokens += snippet_tokens
        cleaned.append(SearchResult(
            title=sanitize_snippet(r.title, 50),
            url=r.url,
            snippet=snippet,
            score=r.score,
            source=r.source,
        ))

    return cleaned
