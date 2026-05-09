"""Facebook Messenger media operations via the Graph API (Phase 5-Channels).

Messenger media flow (Send API):

  * Inbound: webhook events carry ``attachment.payload.url`` (CDN URL) and an
    optional ``attachment_id``. We download bytes from the CDN URL.
  * Outbound: send a remote URL directly OR upload via
    POST /{page_id}/message_attachments to obtain a reusable attachment_id,
    then reference that id in subsequent /me/messages calls.
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

import httpx

from nobla.channels.base import Attachment, AttachmentType
from nobla.channels.messenger.models import (
    DEFAULT_API_VERSION,
    GRAPH_API_BASE,
)

logger = logging.getLogger(__name__)


# ── Type detection ────────────────────────────────────────


# Messenger Send API attachment.type values.
_VALID_ATTACHMENT_TYPES = frozenset({"image", "audio", "video", "file"})


def detect_attachment_type(filename: str) -> AttachmentType:
    """Map a filename (or MIME-bearing identifier) to the unified AttachmentType.

    The base ``AttachmentType`` enum has IMAGE, AUDIO, VIDEO, DOCUMENT — we
    map Messenger's "file" category to DOCUMENT.
    """
    mime = guess_mime_type(filename)
    if mime.startswith("image/"):
        return AttachmentType.IMAGE
    if mime.startswith("audio/"):
        return AttachmentType.AUDIO
    if mime.startswith("video/"):
        return AttachmentType.VIDEO
    return AttachmentType.DOCUMENT


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from a filename, defaulting to application/octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _attachment_type_to_messenger(att_type: AttachmentType) -> str:
    """Convert our AttachmentType to the Messenger Send API string."""
    if att_type == AttachmentType.IMAGE:
        return "image"
    if att_type == AttachmentType.AUDIO:
        return "audio"
    if att_type == AttachmentType.VIDEO:
        return "video"
    return "file"


# ── Download ──────────────────────────────────────────────


async def get_attachment_url(
    attachment_id: str,
    page_access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Resolve the CDN download URL for a Messenger ``attachment_id``."""
    url = f"{GRAPH_API_BASE}/{api_version}/{attachment_id}"
    headers = {"Authorization": f"Bearer {page_access_token}"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        cdn_url = data.get("url")
        if not cdn_url:
            logger.warning(
                "Messenger attachment %s has no url in response", attachment_id
            )
        return cdn_url
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Messenger get_attachment_url HTTP %s for %s",
            exc.response.status_code,
            attachment_id,
        )
        return None
    except httpx.RequestError:
        logger.exception(
            "Messenger get_attachment_url network error for %s", attachment_id
        )
        return None
    except ValueError:
        logger.exception(
            "Messenger get_attachment_url malformed JSON for %s", attachment_id
        )
        return None
    finally:
        if own_client and client is not None:
            await client.aclose()


async def _download_bytes(
    cdn_url: str,
    page_access_token: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> bytes | None:
    """Download raw bytes from a Messenger CDN URL."""
    headers = {"Authorization": f"Bearer {page_access_token}"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout)

    try:
        resp = await client.get(cdn_url, headers=headers)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Messenger media download HTTP %s for %s",
            exc.response.status_code,
            cdn_url,
        )
        return None
    except httpx.RequestError:
        logger.exception("Messenger media download network error for %s", cdn_url)
        return None
    finally:
        if own_client and client is not None:
            await client.aclose()


async def download_attachment(
    attachment_id: str,
    page_access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
    max_size_bytes: int = 100 * 1024 * 1024,
    filename_hint: str | None = None,
    mime_type_hint: str | None = None,
) -> Attachment | None:
    """Download a Messenger attachment and return a unified ``Attachment``.

    Chains ``get_attachment_url`` + a CDN GET. Honors ``max_size_bytes`` —
    payloads exceeding the cap are dropped with a warning rather than
    truncated.
    """
    cdn_url = await get_attachment_url(
        attachment_id, page_access_token, api_version, client
    )
    if not cdn_url:
        return None

    data = await _download_bytes(cdn_url, page_access_token, client, timeout)
    if data is None:
        return None

    if len(data) > max_size_bytes:
        logger.warning(
            "Messenger attachment %s exceeds size limit (%d > %d)",
            attachment_id,
            len(data),
            max_size_bytes,
        )
        return None

    mime = mime_type_hint or guess_mime_type(filename_hint or attachment_id)
    if filename_hint:
        filename = filename_hint
    else:
        ext = mimetypes.guess_extension(mime) or ""
        filename = f"{attachment_id}{ext}"

    logger.info(
        "Messenger downloaded attachment %s (%d bytes, %s)",
        attachment_id,
        len(data),
        mime,
    )

    return Attachment(
        type=detect_attachment_type(filename),
        filename=filename,
        mime_type=mime,
        size_bytes=len(data),
        url=cdn_url,
        data=data,
    )


async def download_attachment_from_url(
    cdn_url: str,
    page_access_token: str,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
    max_size_bytes: int = 100 * 1024 * 1024,
    filename_hint: str | None = None,
    mime_type_hint: str | None = None,
) -> Attachment | None:
    """Download a Messenger attachment when only the CDN URL is available.

    Inbound webhook events typically carry ``attachment.payload.url`` directly,
    so we don't always need an attachment_id round-trip.
    """
    data = await _download_bytes(cdn_url, page_access_token, client, timeout)
    if data is None:
        return None

    if len(data) > max_size_bytes:
        logger.warning(
            "Messenger CDN payload exceeds size limit (%d > %d) at %s",
            len(data),
            max_size_bytes,
            cdn_url,
        )
        return None

    mime = mime_type_hint or guess_mime_type(filename_hint or cdn_url)
    if filename_hint:
        filename = filename_hint
    else:
        ext = mimetypes.guess_extension(mime) or ""
        filename = f"messenger-attachment{ext}"

    logger.info(
        "Messenger downloaded CDN attachment (%d bytes, %s)", len(data), mime
    )

    return Attachment(
        type=detect_attachment_type(filename),
        filename=filename,
        mime_type=mime,
        size_bytes=len(data),
        url=cdn_url,
        data=data,
    )


# ── Upload (reusable attachment) ──────────────────────────


async def upload_reusable_attachment(
    file_url: str,
    attachment_type: str,
    page_access_token: str,
    page_id: str,
    api_version: str = DEFAULT_API_VERSION,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Upload a remote file to Messenger and return a reusable attachment_id.

    POST /{page_id}/message_attachments with
        {"message": {"attachment": {"type": <type>, "payload":
            {"is_reusable": true, "url": <file_url>}}}}
    """
    if attachment_type not in _VALID_ATTACHMENT_TYPES:
        logger.error(
            "Messenger upload_reusable_attachment: invalid type %r", attachment_type
        )
        return None

    url = f"{GRAPH_API_BASE}/{api_version}/{page_id}/message_attachments"
    headers = {
        "Authorization": f"Bearer {page_access_token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "message": {
            "attachment": {
                "type": attachment_type,
                "payload": {"is_reusable": True, "url": file_url},
            },
        },
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        attachment_id = data.get("attachment_id")
        if not attachment_id:
            logger.warning(
                "Messenger upload returned no attachment_id (response=%s)", data
            )
            return None
        logger.info(
            "Messenger uploaded reusable attachment id=%s type=%s",
            attachment_id,
            attachment_type,
        )
        return attachment_id
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Messenger upload_reusable_attachment HTTP %s for %s",
            exc.response.status_code,
            file_url,
        )
        return None
    except httpx.RequestError:
        logger.exception(
            "Messenger upload_reusable_attachment network error for %s", file_url
        )
        return None
    except ValueError:
        logger.exception(
            "Messenger upload_reusable_attachment malformed JSON for %s", file_url
        )
        return None
    finally:
        if own_client and client is not None:
            await client.aclose()


# ── Send helpers ──────────────────────────────────────────


def _send_url() -> str:
    """Build the Send API URL — always /me/messages on Graph."""
    # The Send API does not require a path-version segment for /me/messages;
    # callers pass api_version explicitly so callers stay version-aware.
    return f"{GRAPH_API_BASE}/{DEFAULT_API_VERSION}/me/messages"


async def send_media_via_url(
    recipient_id: str,
    attachment_type: str,
    url: str,
    page_access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    client: httpx.AsyncClient | None = None,
    is_reusable: bool = False,
    messaging_type: str = "RESPONSE",
) -> dict[str, Any] | None:
    """Send media to a Messenger user by remote URL.

    POST /{api_version}/me/messages with
        {"recipient": {"id": <psid>}, "messaging_type": "RESPONSE",
         "message": {"attachment": {"type": <type>,
            "payload": {"url": <url>, "is_reusable": <bool>}}}}
    """
    if attachment_type not in _VALID_ATTACHMENT_TYPES:
        logger.error("Messenger send_media_via_url: invalid type %r", attachment_type)
        return None

    endpoint = f"{GRAPH_API_BASE}/{api_version}/me/messages"
    headers = {
        "Authorization": f"Bearer {page_access_token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "recipient": {"id": recipient_id},
        "messaging_type": messaging_type,
        "message": {
            "attachment": {
                "type": attachment_type,
                "payload": {"url": url, "is_reusable": is_reusable},
            },
        },
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.post(endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "Messenger sent %s via URL to %s (mid=%s)",
            attachment_type,
            recipient_id,
            result.get("message_id", ""),
        )
        return result
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Messenger send_media_via_url HTTP %s for %s",
            exc.response.status_code,
            recipient_id,
        )
        return None
    except httpx.RequestError:
        logger.exception(
            "Messenger send_media_via_url network error for %s", recipient_id
        )
        return None
    except ValueError:
        logger.exception(
            "Messenger send_media_via_url malformed JSON for %s", recipient_id
        )
        return None
    finally:
        if own_client and client is not None:
            await client.aclose()


async def send_media_via_attachment_id(
    recipient_id: str,
    attachment_type: str,
    attachment_id: str,
    page_access_token: str,
    api_version: str = DEFAULT_API_VERSION,
    client: httpx.AsyncClient | None = None,
    messaging_type: str = "RESPONSE",
) -> dict[str, Any] | None:
    """Send previously-uploaded media to a Messenger user by attachment_id."""
    if attachment_type not in _VALID_ATTACHMENT_TYPES:
        logger.error(
            "Messenger send_media_via_attachment_id: invalid type %r", attachment_type
        )
        return None

    endpoint = f"{GRAPH_API_BASE}/{api_version}/me/messages"
    headers = {
        "Authorization": f"Bearer {page_access_token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "recipient": {"id": recipient_id},
        "messaging_type": messaging_type,
        "message": {
            "attachment": {
                "type": attachment_type,
                "payload": {"attachment_id": attachment_id},
            },
        },
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        resp = await client.post(endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "Messenger sent %s via attachment_id=%s to %s",
            attachment_type,
            attachment_id,
            recipient_id,
        )
        return result
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Messenger send_media_via_attachment_id HTTP %s for %s",
            exc.response.status_code,
            recipient_id,
        )
        return None
    except httpx.RequestError:
        logger.exception(
            "Messenger send_media_via_attachment_id network error for %s",
            recipient_id,
        )
        return None
    except ValueError:
        logger.exception(
            "Messenger send_media_via_attachment_id malformed JSON for %s",
            recipient_id,
        )
        return None
    finally:
        if own_client and client is not None:
            await client.aclose()


async def send_attachment(
    recipient_id: str,
    attachment: Attachment,
    page_access_token: str,
    page_id: str,
    api_version: str = DEFAULT_API_VERSION,
    client: httpx.AsyncClient | None = None,
    messaging_type: str = "RESPONSE",
) -> bool:
    """Deliver a unified ``Attachment`` to Messenger.

    Behavior:
      * If the attachment carries a public ``url``, send via URL directly.
      * Otherwise we cannot upload raw bytes through the Send API alone —
        Messenger requires a publicly-reachable URL or a pre-uploaded
        attachment_id. We log and return False.
    """
    att_type = _attachment_type_to_messenger(attachment.type)

    if attachment.url:
        result = await send_media_via_url(
            recipient_id,
            att_type,
            attachment.url,
            page_access_token,
            api_version,
            client,
            messaging_type=messaging_type,
        )
        return result is not None

    logger.warning(
        "Messenger attachment %s has no URL — cannot deliver via Send API",
        attachment.filename,
    )
    return False
