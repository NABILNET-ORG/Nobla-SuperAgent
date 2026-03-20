"""Prompt compression with LLMLingua-2 fallback to naive truncation."""
from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)
_llmlingua = None
_llmlingua_failed = False

def _get_llmlingua():
    global _llmlingua, _llmlingua_failed
    if _llmlingua_failed:
        return None
    if _llmlingua is not None:
        return _llmlingua
    try:
        from llmlingua import PromptCompressor
        _llmlingua = PromptCompressor()
        logger.info("compression.llmlingua_loaded")
        return _llmlingua
    except Exception as exc:
        _llmlingua_failed = True
        logger.info("compression.llmlingua_unavailable", reason=str(exc))
        return None

def naive_truncate(text: str, target_ratio: float = 0.5) -> str:
    words = text.split()
    if len(words) <= 50:
        return text
    target_len = max(int(len(words) * target_ratio), 10)
    head = int(target_len * 0.67)
    tail = target_len - head
    return " ".join(words[:head]) + " ... " + " ".join(words[-tail:])

async def compress_context(text: str, target_ratio: float = 0.5, enabled: bool = True) -> str:
    if not enabled or len(text) < 200:
        return text
    compressor = _get_llmlingua()
    if compressor:
        try:
            result = compressor.compress_prompt([text], rate=target_ratio, force_tokens=["\n", ".", "?", "!"])
            return result.get("compressed_prompt", text)
        except Exception as exc:
            logger.warning("compression.llmlingua_error", error=str(exc))
    return naive_truncate(text, target_ratio)
