"""Telegram channel adapter (Phase 5A)."""

__all__ = ["TelegramAdapter"]


def __getattr__(name: str):
    if name == "TelegramAdapter":
        from nobla.channels.telegram.adapter import TelegramAdapter
        return TelegramAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
