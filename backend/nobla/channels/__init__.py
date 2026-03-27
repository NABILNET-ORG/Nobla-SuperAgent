"""Nobla Channel Abstraction Layer — unified interface for all messaging platforms."""

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    BaseChannelAdapter,
    ChannelMessage,
    ChannelResponse,
    InlineAction,
)

__all__ = [
    "Attachment",
    "AttachmentType",
    "BaseChannelAdapter",
    "ChannelMessage",
    "ChannelResponse",
    "InlineAction",
]
