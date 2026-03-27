"""Discord media handling — upload, download, MIME detection (Phase 5A).

Bridges between Nobla's ``Attachment`` model and Discord's file API.
Inbound: downloads files from Discord message attachments.
Outbound: wraps data as ``discord.File`` objects for sending.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.discord.models import MIME_TO_EMBED_TYPE

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# MIME prefix → AttachmentType mapping
_MIME_PREFIX_MAP: dict[str, AttachmentType] = {
    "image/": AttachmentType.IMAGE,
    "audio/": AttachmentType.AUDIO,
    "video/": AttachmentType.VIDEO,
}


def detect_attachment_type(mime_type: str) -> AttachmentType:
    """Map a MIME type to an AttachmentType enum value."""
    for prefix, atype in _MIME_PREFIX_MAP.items():
        if mime_type.startswith(prefix):
            return atype
    return AttachmentType.DOCUMENT


async def download_attachment(
    discord_attachment: discord.Attachment,
    max_size_mb: int = 25,
) -> Attachment | None:
    """Download a file from Discord and wrap it as a Nobla Attachment.

    Returns None if the file exceeds ``max_size_mb``.
    """
    max_bytes = max_size_mb * 1024 * 1024
    if discord_attachment.size > max_bytes:
        logger.warning(
            "File %s exceeds size limit (%d > %d bytes)",
            discord_attachment.filename, discord_attachment.size, max_bytes,
        )
        return None

    try:
        data = await discord_attachment.read()
    except Exception:
        logger.exception(
            "Failed to download Discord attachment %s",
            discord_attachment.filename,
        )
        return None

    mime = discord_attachment.content_type or "application/octet-stream"

    return Attachment(
        type=detect_attachment_type(mime),
        filename=discord_attachment.filename,
        mime_type=mime,
        size_bytes=len(data),
        data=data,
    )


def extract_attachments_info(
    message: discord.Message,
) -> list[discord.Attachment]:
    """Extract downloadable attachments from a Discord message."""
    return list(message.attachments)


def attachment_to_file(attachment: Attachment) -> dict[str, Any]:
    """Convert a Nobla Attachment to kwargs for discord.File constructor.

    Returns a dict with 'fp' and 'filename' keys that can be unpacked
    into ``discord.File(fp=..., filename=...)``.
    """
    if not attachment.data:
        return {}

    return {
        "fp": BytesIO(attachment.data),
        "filename": attachment.filename,
    }


def is_embeddable(mime_type: str) -> bool:
    """Check if a MIME type can be embedded inline in Discord."""
    return mime_type in MIME_TO_EMBED_TYPE
