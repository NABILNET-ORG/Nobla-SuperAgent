"""WhatsApp media upload/download via the Graph API (Phase 5-Channels).

All media operations go through Meta's Cloud API:
  Upload:   POST /<phone_number_id>/media  →  returns media_id
  Download: GET /<media_id>  →  returns CDN url  →  GET url → bytes
  Send:     POST /<phone_number_id>/messages with media_id reference
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

import httpx

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.whatsapp.models import (
    GRAPH_API_BASE,
    MIME_TO_MEDIA_TYPE,
)

logger = logging.getLogger(__name__)


# ── Type detection ────────────────────────────────────────


def detect_attachment_type(mime_type: str) -> AttachmentType:
    """Map a MIME type to the unified AttachmentType enum."""
    media_type = MIME_TO_MEDIA_TYPE.get(mime_type, "document")
    mapping = {
        "image": AttachmentType.IMAGE,
        "audio": AttachmentType.AUDIO,
        "video": AttachmentType.VIDEO,
        "document": AttachmentType.DOCUMENT,
    }
    return mapping.get(media_type, AttachmentType.DOCUMENT)


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to application/octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


# ── Download ──────────────────────────────────────────────


async def get_media_url(
    media_id: str,
    access_token: str,
    api_version: str = "v21.0",
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Retrieve the CDN download URL for a media_id from the Graph API."""
    url = f"{GRAPH_API_BASE}/{api_version}/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("url")
    except Exception:
        logger.exception("Failed to get media URL for %s", media_id)
        return None
    finally:
        if own_client:
            await client.aclose()


async def download_media(
    media_url: str,
    access_token: str,
    client: httpx.AsyncClient | None = None,
    timeout: int = 30,
) -> bytes | None:
    """Download media bytes from a WhatsApp CDN URL."""
    headers = {"Authorization": f"Bearer {access_token}"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=float(timeout))

    try:
        resp = await client.get(media_url, headers=headers)
        resp.raise_for_status()
        return resp.content
    except Exception:
        logger.exception("Failed to download media from %s", media_url)
        return None
    finally:
        if own_client:
            await client.aclose()


async def download_attachment(
    media_id: str,
    mime_type: str,
    access_token: str,
    api_version: str = "v21.0",
    client: httpx.AsyncClient | None = None,
    max_size_bytes: int = 100 * 1024 * 1024,
) -> Attachment | None:
    """Download a WhatsApp media attachment and return a unified Attachment."""
    media_url = await get_media_url(media_id, access_token, api_version, client)
    if not media_url:
        return None

    data = await download_media(media_url, access_token, client)
    if not data:
        return None

    if len(data) > max_size_bytes:
        logger.warning(
            "Media %s exceeds size limit (%d > %d)", media_id, len(data), max_size_bytes
        )
        return None

    ext = mimetypes.guess_extension(mime_type) or ""
    filename = f"{media_id}{ext}"

    return Attachment(
        type=detect_attachment_type(mime_type),
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        data=data,
    )


# ── Upload ────────────────────────────────────────────────


async def upload_media(
    phone_number_id: str,
    access_token: str,
    data: bytes,
    mime_type: str,
    filename: str,
    api_version: str = "v21.0",
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Upload media to WhatsApp and return the media_id."""
    url = f"{GRAPH_API_BASE}/{api_version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        files = {"file": (filename, data, mime_type)}
        form_data = {"messaging_product": "whatsapp", "type": mime_type}
        resp = await client.post(url, headers=headers, files=files, data=form_data)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception:
        logger.exception("Failed to upload media %s", filename)
        return None
    finally:
        if own_client:
            await client.aclose()


# ── Send helpers ──────────────────────────────────────────


async def send_media_message(
    phone_number_id: str,
    access_token: str,
    recipient: str,
    media_id: str,
    media_type: str,
    caption: str | None = None,
    api_version: str = "v21.0",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Send a media message to a WhatsApp user by media_id."""
    url = f"{GRAPH_API_BASE}/{api_version}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    media_obj: dict[str, Any] = {"id": media_id}
    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption[:1024]
    if media_type == "document":
        media_obj.setdefault("filename", "attachment")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": media_type,
        media_type: media_obj,
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to send %s to %s", media_type, recipient)
        return None
    finally:
        if own_client:
            await client.aclose()


async def send_attachment(
    phone_number_id: str,
    access_token: str,
    recipient: str,
    attachment: Attachment,
    api_version: str = "v21.0",
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Upload an Attachment and send it to a WhatsApp user. Returns success."""
    if not attachment.data:
        logger.warning("Attachment %s has no data to upload", attachment.filename)
        return False

    media_id = await upload_media(
        phone_number_id, access_token, attachment.data,
        attachment.mime_type, attachment.filename, api_version, client,
    )
    if not media_id:
        return False

    media_type = MIME_TO_MEDIA_TYPE.get(attachment.mime_type, "document")
    result = await send_media_message(
        phone_number_id, access_token, recipient,
        media_id, media_type, api_version=api_version, client=client,
    )
    return result is not None
