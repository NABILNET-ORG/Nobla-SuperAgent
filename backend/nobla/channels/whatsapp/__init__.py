"""WhatsApp channel adapter (Phase 5-Channels)."""

__all__ = ["WhatsAppAdapter"]


def __getattr__(name: str):
    if name == "WhatsAppAdapter":
        from nobla.channels.whatsapp.adapter import WhatsAppAdapter

        return WhatsAppAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
