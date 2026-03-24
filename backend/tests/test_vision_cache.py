"""Unit tests for ElementCache and hash_thumbnail."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from nobla.tools.vision.cache import ElementCache, hash_thumbnail


class TestElementCache:
    def test_put_and_get(self):
        cache = ElementCache(ttl=5)
        elements = [{"element_type": "button", "label": "OK", "bbox": {}, "confidence": 0.9}]
        cache.put("hash123", elements)
        assert cache.get("hash123") == elements

    def test_miss_on_different_hash(self):
        cache = ElementCache(ttl=5)
        cache.put("hash123", [{"label": "OK"}])
        assert cache.get("hash456") is None

    def test_miss_on_expired_ttl(self):
        cache = ElementCache(ttl=1)
        with patch("nobla.tools.vision.cache.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            cache.put("hash123", [{"label": "OK"}])
            mock_time.monotonic.return_value = 102.0  # 2s later, TTL=1 expired
            assert cache.get("hash123") is None

    def test_miss_on_empty_cache(self):
        cache = ElementCache(ttl=5)
        assert cache.get("hash123") is None

    def test_clear(self):
        cache = ElementCache(ttl=5)
        cache.put("hash123", [{"label": "OK"}])
        cache.clear()
        assert cache.get("hash123") is None

    def test_put_overwrites_previous(self):
        cache = ElementCache(ttl=5)
        cache.put("hash1", [{"label": "A"}])
        cache.put("hash2", [{"label": "B"}])
        assert cache.get("hash1") is None
        assert cache.get("hash2") == [{"label": "B"}]


class TestHashThumbnail:
    def test_same_image_same_hash(self):
        from PIL import Image
        img = Image.new("RGB", (200, 200), color="red")
        assert hash_thumbnail(img) == hash_thumbnail(img)

    def test_different_image_different_hash(self):
        from PIL import Image
        img1 = Image.new("RGB", (200, 200), color="red")
        img2 = Image.new("RGB", (200, 200), color="blue")
        assert hash_thumbnail(img1) != hash_thumbnail(img2)

    def test_returns_string(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        result = hash_thumbnail(img)
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex digest length
