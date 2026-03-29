"""Slack media upload/download via the Web API v2 pipeline (Phase 5-Channels).

Slack's v2 file upload flow:
  1. POST files.getUploadURLExternal -> get upload_url + file_id
  2. POST upload_url with file content
  3. POST files.completeUploadExternal -> finalize + share to channel

Download:
  GET file.url_private with Bearer token
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

import httpx

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.slack.models import MIME_TO_MEDIA_TYPE, SLACK_API_BASE

logger = logging.getLogger(__name__)


# -- Type detection --------------------------------------------------


def detect_attachment_type(mime_type: str) -> AttachmentType:
    """Map a MIME type to the unified AttachmentType enum."""
    media_type = MIME_TO_MEDIA_TYPE.get(mime_type, "document")
    mapping = {
        "image": AttachmentType.IMAGE,
        "audio": AttachmentType.AUDIO,
        "video": AttachmentType.VIDEO,
        "document": AttachmentType.DOCUMENT,
        "snippet": AttachmentType.DOCUMENT,
    }
    return mapping.get(media_type, AttachmentType.DOCUMENT)


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to application/octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


# -- Upload (v2 pipeline) -------------------------------------------


async def upload_file_v2(
    bot_token: str,
    data: bytes,
    filename: str,
    channel_id: str,
    title: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Upload a file using Slack's v2 upload pipeline.

    Returns the file_id on success, None on failure.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=60.0)

    headers = {"Authorization": f"Bearer {bot_token}"}

    try:
        # Step 1: Get upload URL
        resp1 = await client.post(
            f"{SLACK_API_BASE}/files.getUploadURLExternal",
            headers=headers,
            data={"filename": filename, "length": len(data)},
        )
        resp1.raise_for_status()
        result1 = resp1.json()

        if not result1.get("ok"):
            logger.error(
                "files.getUploadURLExternal failed: %s",
                result1.get("error", "unknown"),
            )
            return None

        upload_url = result1["upload_url"]
        file_id = result1["file_id"]

        # Step 2: Upload file content to the URL (Slack requires PUT)
        resp2 = await client.put(
            upload_url,
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp2.raise_for_status()

        # Step 3: Complete the upload (share to channel)
        import json

        files_payload = [{"id": file_id, "title": title or filename}]
        resp3 = await client.post(
            f"{SLACK_API_BASE}/files.completeUploadExternal",
            headers={
                **headers,
                "Content-Type": "application/json",
            },
            json={
                "files": files_payload,
                "channel_id": channel_id,
            },
        )
        resp3.raise_for_status()

        return file_id

    except Exception:
        logger.exception("Failed to upload file %s via v2 pipeline", filename)
        return None
    finally:
        if own_client:
            await client.aclose()


# -- Download --------------------------------------------------------


async def download_file(
    url: str,
    bot_token: str,
    client: httpx.AsyncClient | None = None,
    max_size_bytes: int = 100 * 1024 * 1024,
) -> bytes | None:
    """Download a file from Slack's CDN using the bot token for auth."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {bot_token}"}
        )
        resp.raise_for_status()

        if len(resp.content) > max_size_bytes:
            logger.warning(
                "File at %s exceeds size limit (%d > %d)",
                url, len(resp.content), max_size_bytes,
            )
            return None

        return resp.content

    except Exception:
        logger.exception("Failed to download file from %s", url)
        return None
    finally:
        if own_client:
            await client.aclose()


# -- Send helper -----------------------------------------------------


async def send_attachment(
    bot_token: str,
    channel_id: str,
    attachment: Attachment,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Upload an Attachment and share it in a Slack channel. Returns success."""
    if not attachment.data:
        logger.warning("Attachment %s has no data to upload", attachment.filename)
        return False

    file_id = await upload_file_v2(
        bot_token=bot_token,
        data=attachment.data,
        filename=attachment.filename,
        channel_id=channel_id,
        client=client,
    )
    return file_id is not None
