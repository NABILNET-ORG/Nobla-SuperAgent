"""Signal channel adapter (Phase 5-Channels)."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "SignalAdapter":
        from nobla.channels.signal.adapter import SignalAdapter
        return SignalAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
