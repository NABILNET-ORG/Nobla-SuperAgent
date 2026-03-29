"""Microsoft Teams media upload/download (Phase 5-Channels).

Download:
  - contentUrl: GET with Bearer token auth
  - downloadUrl (file download info): direct GET, no auth

Upload:
  - ≤256KB: inline base64 data URI in Activity attachments
  - >256KB with URL: hero card with download link
  - >256KB without URL: unsupported (log warning)
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from typing import Any

import httpx

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.teams.models import (
    MAX_ATTACHMENT_INLINE_BYTES,
    MIME_TO_MEDIA_TYPE,
)

logger = logging.getLogger(__name__)


def detect_attachment_type(mime_type: str) -> AttachmentType:
    media_type = MIME_TO_MEDIA_TYPE.get(mime_type, "document")
    mapping = {
        "image": AttachmentType.IMAGE, "audio": AttachmentType.AUDIO,
        "video": AttachmentType.VIDEO, "document": AttachmentType.DOCUMENT,
    }
    return mapping.get(media_type, AttachmentType.DOCUMENT)


def guess_mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


async def download_attachment(
    attachment_data: dict[str, Any], bot_token: str,
    client: httpx.AsyncClient, max_size_bytes: int = 100 * 1024 * 1024,
) -> Attachment | None:
    content_type = attachment_data.get("contentType", "")
    name = attachment_data.get("name", "attachment")
    url: str | None = None
    needs_auth = True

    if content_type == "application/vnd.microsoft.teams.file.download.info":
        content = attachment_data.get("content", {})
        url = content.get("downloadUrl")
        needs_auth = False
        content_type = guess_mime_type(name)
    else:
        url = attachment_data.get("contentUrl")

    if not url:
        logger.warning("No download URL found in attachment: %s", name)
        return None

    try:
        headers = {}
        if needs_auth:
            headers["Authorization"] = f"Bearer {bot_token}"
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content_length = int(resp.headers.get("Content-Length", len(resp.content)))
        if content_length > max_size_bytes:
            logger.warning(
                "Attachment %s exceeds size limit (%d > %d)", name, content_length, max_size_bytes
            )
            return None
        att_type = detect_attachment_type(content_type)
        return Attachment(
            type=att_type, filename=name, mime_type=content_type,
            size_bytes=len(resp.content), data=resp.content,
        )
    except Exception:
        logger.exception("Failed to download Teams attachment: %s", name)
        return None


async def send_attachment(
    service_url: str, conversation_id: str, attachment: Attachment,
    bot_token: str, client: httpx.AsyncClient,
) -> bool:
    has_data = bool(attachment.data and len(attachment.data) > 0)
    has_url = bool(attachment.url)

    if has_data and len(attachment.data) <= MAX_ATTACHMENT_INLINE_BYTES:
        b64 = base64.b64encode(attachment.data).decode()
        activity = {
            "type": "message",
            "attachments": [{
                "contentType": attachment.mime_type,
                "contentUrl": f"data:{attachment.mime_type};base64,{b64}",
                "name": attachment.filename,
            }],
        }
        return await _post_activity(service_url, conversation_id, activity, bot_token, client)

    if has_url:
        activity = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.hero",
                "content": {
                    "title": attachment.filename,
                    "subtitle": f"{attachment.mime_type} ({attachment.size_bytes} bytes)",
                    "buttons": [{"type": "openUrl", "title": "Download", "value": attachment.url}],
                },
            }],
        }
        return await _post_activity(service_url, conversation_id, activity, bot_token, client)

    logger.warning(
        "Cannot send attachment %s: too large for inline (%d bytes) and no URL",
        attachment.filename, attachment.size_bytes,
    )
    return False


async def _post_activity(
    service_url: str, conversation_id: str, activity: dict[str, Any],
    bot_token: str, client: httpx.AsyncClient,
) -> bool:
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    try:
        resp = await client.post(url, json=activity, headers={
            "Authorization": f"Bearer {bot_token}", "Content-Type": "application/json",
        })
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to post activity to %s", conversation_id)
        return False
