"""Shared TTL cache for detected UI elements."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from PIL import Image


@dataclass
class CachedElements:
    elements: list[dict]
    screenshot_hash: str
    timestamp: float


class ElementCache:
    """Single-entry TTL cache for detected elements.

    Keyed by screenshot thumbnail hash. The most recent detection
    result is cached; older entries are evicted on put().
    """

    def __init__(self, ttl: int = 5):
        self._ttl = ttl
        self._entry: CachedElements | None = None

    def get(self, screenshot_hash: str) -> list[dict] | None:
        if (
            self._entry
            and self._entry.screenshot_hash == screenshot_hash
            and (time.monotonic() - self._entry.timestamp) < self._ttl
        ):
            return self._entry.elements
        return None

    def put(self, screenshot_hash: str, elements: list[dict]) -> None:
        self._entry = CachedElements(elements, screenshot_hash, time.monotonic())

    def clear(self) -> None:
        self._entry = None


def hash_thumbnail(image: Image.Image) -> str:
    """Fast image hash via 64x64 thumbnail. ~1ms vs ~50ms for full 4K."""
    thumb = image.resize((64, 64)).tobytes()
    return hashlib.md5(thumb).hexdigest()


# Module-level singleton. Imported by detection.py and targeting.py directly.
element_cache = ElementCache()
