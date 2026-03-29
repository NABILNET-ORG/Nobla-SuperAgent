"""Slack channel adapter (Phase 5-Channels)."""

__all__ = ["SlackAdapter"]


def __getattr__(name: str):
    if name == "SlackAdapter":
        from nobla.channels.slack.adapter import SlackAdapter

        return SlackAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
