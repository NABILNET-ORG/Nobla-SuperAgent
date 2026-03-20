import pytest
from nobla.brain.compression import compress_context, naive_truncate

def test_naive_truncate_short():
    assert naive_truncate("Short text.", target_ratio=0.5) == "Short text."

def test_naive_truncate_long():
    text = " ".join([f"word{i}" for i in range(100)])
    result = naive_truncate(text, target_ratio=0.5)
    assert len(result.split()) < len(text.split())

def test_naive_truncate_preserves_start_end():
    words = [f"w{i}" for i in range(100)]
    text = " ".join(words)
    result = naive_truncate(text, target_ratio=0.5)
    assert result.startswith("w0")
    assert "w99" in result

@pytest.mark.asyncio
async def test_compress_short_unchanged():
    assert await compress_context("Hello world.") == "Hello world."

@pytest.mark.asyncio
async def test_compress_long():
    text = " ".join([f"word{i}" for i in range(200)])
    result = await compress_context(text, target_ratio=0.5)
    assert len(result.split()) < len(text.split())

@pytest.mark.asyncio
async def test_compress_disabled():
    text = " ".join([f"word{i}" for i in range(200)])
    assert await compress_context(text, enabled=False) == text
