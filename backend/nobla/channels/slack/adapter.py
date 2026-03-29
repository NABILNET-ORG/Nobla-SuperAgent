"""Slack channel adapter with dual Socket Mode + Events API (Phase 5-Channels).

Implements ``BaseChannelAdapter`` for Slack.
  - Socket Mode (default): WebSocket connection via app-level token (xapp-...)
  - Events API: HTTP webhook with request signature verification

Outbound: REST calls to chat.postMessage with Block Kit formatting.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

try:
    import websockets  # Only required for Socket Mode
except ImportError:
    websockets = None  # type: ignore[assignment]

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.slack.formatter import format_response
from nobla.channels.slack.handlers import RateLimitQueue, SlackHandlers
from nobla.channels.slack.media import send_attachment
from nobla.channels.slack.models import SLACK_API_BASE

logger = logging.getLogger(__name__)


class SlackRateLimitError(Exception):
    """Raised when Slack returns HTTP 429 (rate limited)."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


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
        self._rate_queue: RateLimitQueue | None = None
        self._queue_task: asyncio.Task | None = None
        self._socket_task: asyncio.Task | None = None
        self._socket_ws: Any = None
        self._socket_url: str | None = None

    @property
    def name(self) -> str:
        return "slack"

    # -- Lifecycle ---------------------------------------------------

    async def start(self) -> None:
        """Initialize the HTTP client, rate queue, and Socket Mode if configured."""
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

        # Initialize rate-limit queue with _post_message as sender
        self._rate_queue = RateLimitQueue(sender=self._post_message)
        self._queue_task = asyncio.create_task(self._queue_worker())

        self._running = True

        # Socket Mode: open WebSocket via app-level token
        if self._settings.socket_mode and getattr(self._settings, "app_token", ""):
            await self._open_socket_mode()

        mode = "Socket Mode" if self._settings.socket_mode else "Events API"
        logger.info(
            "Slack adapter started (bot_user_id=%s, mode=%s)",
            self._settings.bot_user_id, mode,
        )

    async def stop(self) -> None:
        """Gracefully shut down WebSocket, queue worker, and HTTP client."""
        if not self._running:
            return

        # Cancel Socket Mode receive loop
        if self._socket_task and not self._socket_task.done():
            self._socket_task.cancel()
            try:
                await self._socket_task
            except asyncio.CancelledError:
                pass
            self._socket_task = None

        # Close WebSocket connection
        if self._socket_ws:
            try:
                await self._socket_ws.close()
            except Exception:
                pass
            self._socket_ws = None

        # Cancel queue worker
        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self._queue_task = None

        self._rate_queue = None

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

        # Reject requests older than 5 minutes to prevent replay attacks
        try:
            if abs(time.time() - float(timestamp)) > 300:
                logger.warning("Request timestamp too old: %s", timestamp)
                return False
        except (ValueError, TypeError):
            logger.warning("Invalid timestamp value: %s", timestamp)
            return False

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

        # Format and send text + blocks via rate-limit queue
        if response.content:
            formatted = format_response(response)
            payload: dict[str, Any] = {
                "channel": channel_user_id,
                "text": formatted["text"],
                "blocks": formatted["blocks"],
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            if self._rate_queue:
                await self._rate_queue.enqueue(payload)
            else:
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
        """Post a message to the Slack Web API with rate-limit handling."""
        if not self._client:
            return

        try:
            resp = await self._client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                json=payload,
            )

            # Handle rate limiting (HTTP 429)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                if self._rate_queue:
                    self._rate_queue.set_retry_after(retry_after)
                    await self._rate_queue.enqueue(payload)
                raise SlackRateLimitError(retry_after)

            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "chat.postMessage failed: %s", data.get("error", "unknown")
                )
        except SlackRateLimitError:
            logger.warning(
                "Rate limited posting to %s, re-queued",
                payload.get("channel"),
            )
        except Exception:
            logger.exception(
                "Failed to post message to %s", payload.get("channel")
            )

    async def _post_message_raw(self, payload: dict[str, Any]) -> None:
        """Send a message payload -- used as RateLimitQueue sender."""
        await self._post_message(payload)

    async def _queue_worker(self) -> None:
        """Background loop that drains the rate-limit queue."""
        try:
            while True:
                if self._rate_queue:
                    await self._rate_queue.process()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    # -- Socket Mode helpers -----------------------------------------

    async def _open_socket_mode(self) -> None:
        """Request a WebSocket URL and launch the receive loop."""
        if websockets is None:
            logger.warning(
                "websockets package not installed -- "
                "Socket Mode unavailable, falling back to Events API"
            )
            return

        app_token = self._settings.app_token
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(
                    "https://slack.com/api/apps.connections.open",
                    headers={"Authorization": f"Bearer {app_token}"},
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error(
                        "apps.connections.open failed: %s",
                        data.get("error", "unknown"),
                    )
                    return
                self._socket_url = data.get("url")
        except Exception:
            logger.exception("Failed to obtain Socket Mode URL")
            return

        if self._socket_url:
            self._socket_task = asyncio.create_task(
                self._socket_receive_loop()
            )

    async def _socket_receive_loop(self) -> None:
        """Read Socket Mode envelopes, ack, and dispatch."""
        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            try:
                async with websockets.connect(self._socket_url) as ws:
                    self._socket_ws = ws
                    backoff = 1.0  # reset on successful connect
                    logger.info("Socket Mode WebSocket connected")

                    async for raw in ws:
                        try:
                            envelope = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue

                        envelope_id = envelope.get("envelope_id")
                        etype = envelope.get("type", "")

                        # Ack within 3 seconds
                        if envelope_id:
                            await ws.send(
                                json.dumps({"envelope_id": envelope_id})
                            )

                        # Dispatch
                        if etype == "events_api":
                            await self.handle_socket_event(envelope)
                        elif etype == "slash_commands":
                            payload = envelope.get("payload", {})
                            await self._handlers.handle_slash_command(
                                command=payload.get("command", ""),
                                text=payload.get("text", ""),
                                user_id=payload.get("user_id", ""),
                                channel_id=payload.get("channel_id", ""),
                            )
                        elif etype == "interactive":
                            await self.handle_socket_event(envelope)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Socket Mode disconnected, reconnecting in %.1fs",
                    backoff,
                )
                self._socket_ws = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
