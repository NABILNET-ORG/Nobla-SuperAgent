"""WhatsApp Business Cloud API channel adapter (Phase 5-Channels).

Implements ``BaseChannelAdapter`` to connect WhatsApp via Meta's Cloud API.
Inbound: webhook POST with HMAC-SHA256 signature verification.
Outbound: REST calls to the Graph API (text, media, interactive messages).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.whatsapp.formatter import format_response
from nobla.channels.whatsapp.handlers import WhatsAppHandlers
from nobla.channels.whatsapp.media import send_attachment
from nobla.channels.whatsapp.models import GRAPH_API_BASE
from nobla.config.settings import WhatsAppSettings

logger = logging.getLogger(__name__)


class WhatsAppAdapter(BaseChannelAdapter):
    """WhatsApp Business Cloud API adapter (webhook-only).

    Args:
        settings: WhatsApp configuration (tokens, phone_number_id, etc.).
        handlers: Pre-built ``WhatsAppHandlers`` with linking + event bus.
    """

    def __init__(
        self,
        settings: WhatsAppSettings,
        handlers: WhatsAppHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: httpx.AsyncClient | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "whatsapp"

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Initialize the HTTP client and wire handler send function."""
        if self._running:
            logger.warning("WhatsApp adapter already running")
            return

        if not self._settings.access_token:
            raise ValueError("WhatsApp access_token is required")
        if not self._settings.phone_number_id:
            raise ValueError("WhatsApp phone_number_id is required")

        self._client = httpx.AsyncClient(
            timeout=float(self._settings.download_timeout),
            headers={
                "Authorization": f"Bearer {self._settings.access_token}",
                "Content-Type": "application/json",
            },
        )

        # Wire handler's outbound send function
        self._handlers.set_send_fn(self._send_raw_text)
        self._handlers.set_bot_phone(self._settings.phone_number_id)

        self._running = True
        logger.info("WhatsApp adapter started (phone_number_id=%s)", self._settings.phone_number_id)

    async def stop(self) -> None:
        """Gracefully shut down the HTTP client."""
        if not self._running:
            return

        if self._client:
            await self._client.aclose()
            self._client = None

        self._running = False
        logger.info("WhatsApp adapter stopped")

    # ── Webhook verification ──────────────────────────────

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify the X-Hub-Signature-256 header from Meta's webhook.

        Args:
            body: Raw request body bytes.
            signature: Value of X-Hub-Signature-256 header (sha256=...).

        Returns:
            True if the signature is valid.
        """
        if not self._settings.app_secret:
            logger.warning("No app_secret configured — skipping signature check")
            return True

        expected = hmac.new(
            self._settings.app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        provided = signature.removeprefix("sha256=")
        return hmac.compare_digest(expected, provided)

    def verify_webhook_challenge(
        self, mode: str, token: str, challenge: str
    ) -> str | None:
        """Handle Meta's webhook verification GET request.

        Args:
            mode: hub.mode query parameter (should be "subscribe").
            token: hub.verify_token query parameter.
            challenge: hub.challenge query parameter.

        Returns:
            The challenge string if valid, None otherwise.
        """
        if mode == "subscribe" and token == self._settings.verify_token:
            logger.info("Webhook verification succeeded")
            return challenge
        logger.warning("Webhook verification failed (mode=%s)", mode)
        return None

    async def handle_webhook_payload(
        self, body: bytes, signature: str
    ) -> bool:
        """Verify signature and dispatch webhook payload to handlers.

        Returns True if processed successfully.
        """
        if not self.verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            return False

        import json

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.exception("Invalid JSON in webhook body")
            return False

        await self._handlers.handle_webhook(payload)
        return True

    # ── Outbound messaging ────────────────────────────────

    async def send(
        self, channel_user_id: str, response: ChannelResponse
    ) -> None:
        """Send a formatted response to a WhatsApp user."""
        if not self._client:
            logger.error("Cannot send — client not initialized")
            return

        # Send attachments first
        for attachment in response.attachments:
            await send_attachment(
                self._settings.phone_number_id,
                self._settings.access_token,
                channel_user_id,
                attachment,
                self._settings.api_version,
                self._client,
            )

        # Format and send text messages
        if response.content:
            formatted = format_response(response)
            for msg in formatted:
                if msg.interactive:
                    await self._send_interactive(channel_user_id, msg.interactive)
                else:
                    await self._send_raw_text(channel_user_id, msg.text)

    async def send_notification(
        self, channel_user_id: str, text: str
    ) -> None:
        """Send a plain-text notification."""
        await self._send_raw_text(channel_user_id, text)

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a WhatsApp interactive reply into (action_id, metadata).

        Interactive replies arrive as webhook messages (type=interactive),
        already handled in handlers.py. This method handles any raw
        callback data passed directly.
        """
        if isinstance(raw_callback, dict):
            action_id = raw_callback.get("id", "")
            return action_id, raw_callback
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check connectivity by calling the Graph API /me endpoint."""
        if not self._client:
            return False
        try:
            url = (
                f"{GRAPH_API_BASE}/{self._settings.api_version}"
                f"/{self._settings.phone_number_id}"
            )
            resp = await self._client.get(url)
            return resp.status_code == 200
        except Exception:
            logger.exception("WhatsApp health check failed")
            return False

    # ── Private helpers ───────────────────────────────────

    async def _send_raw_text(self, recipient: str, text: str) -> None:
        """Send a plain text message via the Graph API."""
        if not self._client:
            logger.error("Cannot send — client not initialized")
            return

        url = (
            f"{GRAPH_API_BASE}/{self._settings.api_version}"
            f"/{self._settings.phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to send text to %s", recipient)

    async def _send_interactive(
        self, recipient: str, interactive: dict[str, Any]
    ) -> None:
        """Send an interactive message (buttons or list) via the Graph API."""
        if not self._client:
            logger.error("Cannot send — client not initialized")
            return

        url = (
            f"{GRAPH_API_BASE}/{self._settings.api_version}"
            f"/{self._settings.phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "interactive",
            "interactive": interactive,
        }

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to send interactive message to %s", recipient)
