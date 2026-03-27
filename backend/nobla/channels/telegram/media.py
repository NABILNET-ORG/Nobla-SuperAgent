"""Telegram media handling — upload, download, MIME detection (Phase 5A).

Bridges between Nobla's ``Attachment`` model and Telegram's file API.
Inbound: downloads files from Telegram into ``Attachment`` objects.
Outbound: selects the correct ``send_*`` method based on attachment type.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.telegram.models import MAX_CAPTION_LENGTH, MIME_TO_SEND_METHOD

if TYPE_CHECKING:
    from telegram import Bot, Message

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
    bot: Bot,
    file_id: str,
    filename: str,
    mime_type: str,
    file_size: int | None = None,
    max_size_mb: int = 50,
) -> Attachment | None:
    """Download a file from Telegram and wrap it as an Attachment.

    Returns None if the file exceeds ``max_size_mb``.
    """
    max_bytes = max_size_mb * 1024 * 1024
    if file_size and file_size > max_bytes:
        logger.warning(
            "File %s exceeds size limit (%d > %d bytes)",
            filename, file_size, max_bytes,
        )
        return None

    try:
        tg_file = await bot.get_file(file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(buf)
        data = buf.getvalue()
    except Exception:
        logger.exception("Failed to download Telegram file %s", file_id)
        return None

    return Attachment(
        type=detect_attachment_type(mime_type),
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        data=data,
    )


def extract_file_info(message: Message) -> list[dict[str, Any]]:
    """Extract downloadable file metadata from a Telegram message.

    Checks photo, audio, video, voice, video_note, document, animation
    in priority order and returns a list of dicts with keys:
    file_id, filename, mime_type, file_size.
    """
    files: list[dict[str, Any]] = []

    if message.photo:
        # Telegram sends multiple sizes — take the largest
        photo = message.photo[-1]
        files.append({
            "file_id": photo.file_id,
            "filename": f"photo_{photo.file_unique_id}.jpg",
            "mime_type": "image/jpeg",
            "file_size": photo.file_size,
        })

    if message.audio:
        files.append({
            "file_id": message.audio.file_id,
            "filename": message.audio.file_name or "audio.mp3",
            "mime_type": message.audio.mime_type or "audio/mpeg",
            "file_size": message.audio.file_size,
        })

    if message.voice:
        files.append({
            "file_id": message.voice.file_id,
            "filename": "voice.ogg",
            "mime_type": message.voice.mime_type or "audio/ogg",
            "file_size": message.voice.file_size,
        })

    if message.video:
        files.append({
            "file_id": message.video.file_id,
            "filename": message.video.file_name or "video.mp4",
            "mime_type": message.video.mime_type or "video/mp4",
            "file_size": message.video.file_size,
        })

    if message.video_note:
        files.append({
            "file_id": message.video_note.file_id,
            "filename": "video_note.mp4",
            "mime_type": "video/mp4",
            "file_size": message.video_note.file_size,
        })

    if message.animation:
        files.append({
            "file_id": message.animation.file_id,
            "filename": message.animation.file_name or "animation.gif",
            "mime_type": message.animation.mime_type or "image/gif",
            "file_size": message.animation.file_size,
        })

    if message.document:
        files.append({
            "file_id": message.document.file_id,
            "filename": message.document.file_name or "document",
            "mime_type": message.document.mime_type or "application/octet-stream",
            "file_size": message.document.file_size,
        })

    return files


def select_send_method(attachment: Attachment) -> str:
    """Choose the correct Telegram Bot ``send_*`` method for an attachment."""
    method = MIME_TO_SEND_METHOD.get(attachment.mime_type)
    if method:
        return method

    # Fall back based on AttachmentType
    return {
        AttachmentType.IMAGE: "send_photo",
        AttachmentType.AUDIO: "send_audio",
        AttachmentType.VIDEO: "send_video",
        AttachmentType.DOCUMENT: "send_document",
    }.get(attachment.type, "send_document")


async def send_attachment(
    bot: Bot,
    chat_id: int | str,
    attachment: Attachment,
    caption: str | None = None,
    reply_markup: Any = None,
) -> Message | None:
    """Send an attachment to a Telegram chat using the appropriate method."""
    method_name = select_send_method(attachment)
    send_fn = getattr(bot, method_name, None)
    if not send_fn:
        logger.error("Bot has no method %s", method_name)
        return None

    # Truncate caption to Telegram's limit
    if caption and len(caption) > MAX_CAPTION_LENGTH:
        caption = caption[: MAX_CAPTION_LENGTH - 3] + "..."

    file_data = BytesIO(attachment.data) if attachment.data else attachment.url
    if not file_data:
        logger.error("Attachment %s has no data or URL", attachment.filename)
        return None

    # Map send method to the kwarg name for the media
    media_kwarg = {
        "send_photo": "photo",
        "send_audio": "audio",
        "send_voice": "voice",
        "send_video": "video",
        "send_video_note": "video_note",
        "send_animation": "animation",
        "send_sticker": "sticker",
        "send_document": "document",
    }.get(method_name, "document")

    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        media_kwarg: file_data,
    }
    if caption:
        kwargs["caption"] = caption
    if reply_markup:
        kwargs["reply_markup"] = reply_markup

    try:
        return await send_fn(**kwargs)
    except Exception:
        logger.exception("Failed to send %s to %s", method_name, chat_id)
        return None
