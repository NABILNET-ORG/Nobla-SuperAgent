"""Signal media handling -- file-path based (Phase 5-Channels).

signal-cli stores attachments as local files. This module provides
helpers to save outbound attachments to disk (for signal-cli to send)
and load inbound attachments from disk paths reported by signal-cli.

Security: all filenames are sanitized with os.path.basename to prevent
path traversal attacks.
"""

from __future__ import annotations

import logging
import mimetypes
import os

from nobla.channels.base import Attachment, AttachmentType

logger = logging.getLogger(__name__)


# ── Type detection ────────────────────────────────────────


def detect_attachment_type(mime_type: str) -> AttachmentType:
    """Map a MIME type to the unified AttachmentType enum."""
    if mime_type.startswith("image/"):
        return AttachmentType.IMAGE
    if mime_type.startswith("audio/"):
        return AttachmentType.AUDIO
    if mime_type.startswith("video/"):
        return AttachmentType.VIDEO
    return AttachmentType.DOCUMENT


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to application/octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


# ── Validation ────────────────────────────────────────────


def validate_file_size(size_bytes: int, max_mb: int = 100) -> bool:
    """Check whether a file is within the allowed size limit."""
    return size_bytes <= max_mb * 1024 * 1024


# ── Disk I/O ──────────────────────────────────────────────


def save_attachment_to_disk(attachment: Attachment, data_dir: str) -> str:
    """Save an attachment to disk for signal-cli to send.

    Args:
        attachment: The attachment with data bytes.
        data_dir: Base directory for signal data.

    Returns:
        Full path to the saved file.

    Raises:
        ValueError: If the attachment has no data.
    """
    if not attachment.data:
        raise ValueError("Attachment has no data to save")

    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(attachment.filename) or "attachment"

    # Create attachments subdirectory
    attach_dir = os.path.join(data_dir, "attachments")
    os.makedirs(attach_dir, exist_ok=True)

    full_path = os.path.join(attach_dir, safe_name)

    with open(full_path, "wb") as f:
        f.write(attachment.data)

    logger.debug("Saved attachment to %s (%d bytes)", full_path, len(attachment.data))
    return full_path


def load_attachment_from_path(path: str, mime_type: str) -> Attachment:
    """Load an attachment from a local file path (reported by signal-cli).

    Args:
        path: Absolute path to the attachment file.
        mime_type: MIME type reported by signal-cli.

    Returns:
        Attachment with data bytes loaded.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Attachment file not found: {path}")

    with open(path, "rb") as f:
        data = f.read()

    filename = os.path.basename(path)
    att_type = detect_attachment_type(mime_type)

    return Attachment(
        type=att_type,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        data=data,
    )
