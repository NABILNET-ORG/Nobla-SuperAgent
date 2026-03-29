"""Microsoft Teams channel adapter (Phase 5-Channels)."""

__all__ = ["TeamsAdapter"]


def __getattr__(name: str):
    if name == "TeamsAdapter":
        from nobla.channels.teams.adapter import TeamsAdapter
        return TeamsAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
