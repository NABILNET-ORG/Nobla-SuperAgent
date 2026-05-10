"""Facebook Messenger channel adapter (Phase 5-Channels)."""

__all__ = ["MessengerAdapter"]


def __getattr__(name: str):
    if name == "MessengerAdapter":
        from nobla.channels.messenger.adapter import MessengerAdapter

        return MessengerAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
