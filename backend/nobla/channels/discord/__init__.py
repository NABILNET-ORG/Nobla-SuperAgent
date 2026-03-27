"""Discord channel adapter (Phase 5A)."""

__all__ = ["DiscordAdapter"]


def __getattr__(name: str):
    if name == "DiscordAdapter":
        from nobla.channels.discord.adapter import DiscordAdapter
        return DiscordAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
