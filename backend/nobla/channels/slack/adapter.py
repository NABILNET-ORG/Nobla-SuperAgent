"""Slack channel adapter with dual Socket Mode + Events API (Phase 5-Channels).

Implements ``BaseChannelAdapter`` for Slack.
  - Socket Mode (default): WebSocket connection via app-level token (xapp-...)
  - Events API: HTTP webhook with request signature verification

Outbound: REST calls to chat.postMessage with Block Kit formatting.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.slack.formatter import format_response
from nobla.channels.slack.handlers import SlackHandlers
from nobla.channels.slack.media import send_attachment
from nobla.channels.slack.models import SLACK_API_BASE

logger = logging.getLogger(__name__)


class SlackAdapter(BaseChannelAdapter):
    """Slack adapter supporting both Socket Mode and Events API.

    Args:
        settings: Slack configuration (tokens, bot_user_id, etc.).
        handlers: Pre-built ``SlackHandlers`` with linking + event bus.
    """

    def __init__(
        self,
        settings: Any,
        handlers: SlackHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: httpx.AsyncClient | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "slack"

    # -- Lifecycle ---------------------------------------------------

    async def start(self) -> None:
        """Initialize the HTTP client and wire handler send function."""
        if self._running:
            logger.warning("Slack adapter already running")
            return

        if not self._settings.bot_token:
            raise ValueError("Slack bot_token is required")

        self._client = httpx.AsyncClient(
            timeout=float(self._settings.download_timeout),
            headers={
                "Authorization": f"Bearer {self._settings.bot_token}",
                "Content-Type": "application/json",
            },
        )

        # Wire handler's outbound send function
        self._handlers.set_send_fn(self._send_raw_text)

        self._running = True
        mode = "Socket Mode" if self._settings.socket_mode else "Events API"
        logger.info(
            "Slack adapter started (bot_user_id=%s, mode=%s)",
            self._settings.bot_user_id, mode,
        )

    async def stop(self) -> None:
        """Gracefully shut down the HTTP client."""
        if not self._running:
            return

        if self._client:
            await self._client.aclose()
            self._client = None

        self._running = False
        logger.info("Slack adapter stopped")

    # -- Request signature verification ------------------------------

    def verify_request_signature(
        self, body: bytes, timestamp: str, signature: str,
    ) -> bool:
        """Verify a Slack request signature (Events API / slash commands).

        Args:
            body: Raw request body bytes.
            timestamp: X-Slack-Request-Timestamp header value.
            signature: X-Slack-Signature header value (v0=...).

        Returns:
            True if the signature is valid.
        """
        if not self._settings.signing_secret:
            logger.warning("No signing_secret configured - skipping check")
            return True

        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            self._settings.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    # -- Events API entry points -------------------------------------

    def handle_url_verification(
        self, payload: dict[str, Any],
    ) -> str:
        """Handle Slack's URL verification challenge.

        Returns the challenge string to echo back.
        """
        return payload.get("challenge", "")

    async def handle_events_api(
        self, payload: dict[str, Any],
    ) -> None:
        """Process an Events API callback payload."""
        event_type = payload.get("type", "")
        if event_type == "url_verification":
            return  # Handled by handle_url_verification
        if event_type == "event_callback":
            await self._handlers.handle_event(payload)

    # -- Socket Mode support -----------------------------------------

    def build_socket_ack(
        self, envelope: dict[str, Any],
    ) -> dict[str, str]:
        """Build a Socket Mode acknowledgement response.

        Must be sent within 3 seconds of receiving the envelope.
        """
        return {"envelope_id": envelope.get("envelope_id", "")}

    async def handle_socket_event(
        self, envelope: dict[str, Any],
    ) -> None:
        """Process a Socket Mode envelope after ack is sent."""
        envelope_type = envelope.get("type", "")
        payload = envelope.get("payload", {})

        if envelope_type == "events_api":
            await self._handlers.handle_event(payload)
        elif envelope_type == "interactive":
            await self._handlers.handle_interaction(payload)
        elif envelope_type == "slash_commands":
            # Slash commands in Socket Mode arrive as payload
            pass  # Handled via HTTP response in gateway

    # -- Outbound messaging ------------------------------------------

    async def send(
        self,
        channel_user_id: str,
        response: ChannelResponse,
        thread_ts: str | None = None,
    ) -> None:
        """Send a formatted response to a Slack channel or DM."""
        if not self._client:
            logger.error("Cannot send - client not initialized")
            return

        # Send attachments first
        for attachment in response.attachments:
            await send_attachment(
                bot_token=self._settings.bot_token,
                channel_id=channel_user_id,
                attachment=attachment,
                client=self._client,
            )

        # Format and send text + blocks
        if response.content:
            formatted = format_response(response)
            payload: dict[str, Any] = {
                "channel": channel_user_id,
                "text": formatted["text"],
                "blocks": formatted["blocks"],
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts

            await self._post_message(payload)

    async def send_notification(
        self, channel_user_id: str, text: str,
    ) -> None:
        """Send a plain-text notification."""
        await self._send_raw_text(channel_user_id, text)

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a Slack interaction into (action_id, metadata)."""
        if isinstance(raw_callback, dict):
            action_id = raw_callback.get("action_id", "")
            return action_id, raw_callback
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check connectivity by calling auth.test."""
        if not self._client:
            return False
        try:
            resp = await self._client.post(
                f"{SLACK_API_BASE}/auth.test"
            )
            data = resp.json()
            return data.get("ok", False) is True
        except Exception:
            logger.exception("Slack health check failed")
            return False

    # -- Private helpers ---------------------------------------------

    async def _send_raw_text(
        self, channel: str, text: str, thread_ts: str | None = None,
    ) -> None:
        """Send a plain text message via chat.postMessage."""
        if not self._client:
            logger.error("Cannot send - client not initialized")
            return

        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        await self._post_message(payload)

    async def _post_message(self, payload: dict[str, Any]) -> None:
        """Post a message to the Slack Web API."""
        if not self._client:
            return

        try:
            resp = await self._client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "chat.postMessage failed: %s", data.get("error", "unknown")
                )
        except Exception:
            logger.exception(
                "Failed to post message to %s", payload.get("channel")
            )
