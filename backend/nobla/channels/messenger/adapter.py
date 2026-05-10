"""Facebook Messenger Platform channel adapter (Phase 5-Channels).

Implements ``BaseChannelAdapter`` to connect Messenger via Meta's Graph API
Send API. Inbound: webhook POST with X-Hub-Signature-256 (HMAC-SHA256)
verification. Outbound: REST calls to /me/messages on the Graph API.

The adapter intentionally does not own the FastAPI route — the gateway
exposes /webhook/messenger and forwards verified payloads here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.messenger.formatter import format_response
from nobla.channels.messenger.handlers import MessengerHandlers
from nobla.channels.messenger.media import send_attachment
from nobla.channels.messenger.models import (
    DEFAULT_API_VERSION,
    GRAPH_API_BASE,
)

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from nobla.config.settings import MessengerSettings

logger = logging.getLogger(__name__)


class MessengerAdapter(BaseChannelAdapter):
    """Facebook Messenger Platform adapter (webhook-only).

    Args:
        settings: Messenger configuration (page access token, app secret,
            verify token, page id, api version, download timeout).
        handlers: Pre-built ``MessengerHandlers`` with linking + event bus.
    """

    def __init__(
        self,
        settings: "MessengerSettings",
        handlers: MessengerHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: httpx.AsyncClient | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "messenger"

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Initialize the HTTP client and wire the handler send function."""
        if self._running:
            logger.warning("Messenger adapter already running")
            return

        page_access_token = getattr(self._settings, "page_access_token", "") or ""
        page_id = getattr(self._settings, "page_id", "") or ""

        if not page_access_token:
            raise ValueError("Messenger page_access_token is required")
        if not page_id:
            raise ValueError("Messenger page_id is required")

        timeout = float(getattr(self._settings, "download_timeout", 30) or 30)

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {page_access_token}",
                "Content-Type": "application/json",
            },
        )

        # Wire handler's outbound send function so handler-side replies
        # (pairing prompts, command responses) flow through the Send API.
        self._handlers.set_send_fn(self._send_raw_text)

        self._running = True
        logger.info("Messenger adapter started (page_id=%s)", page_id)

    async def stop(self) -> None:
        """Gracefully shut down the HTTP client."""
        if not self._running:
            return

        if self._client is not None:
            await self._client.aclose()
            self._client = None

        self._running = False
        logger.info("Messenger adapter stopped")

    # ── Webhook verification ──────────────────────────────

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify the X-Hub-Signature-256 header from a Messenger webhook.

        Args:
            body: Raw request body bytes.
            signature: Value of the X-Hub-Signature-256 header (sha256=...).

        Returns:
            True if the signature is valid (or no app_secret is configured —
            in which case we log and accept, matching WhatsApp behavior).
        """
        app_secret = getattr(self._settings, "app_secret", "") or ""
        if not app_secret:
            logger.warning(
                "Messenger app_secret not configured — skipping signature check"
            )
            return True

        if not signature:
            logger.warning("Messenger webhook missing X-Hub-Signature-256")
            return False

        expected = hmac.new(
            app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        provided = signature.removeprefix("sha256=").strip()
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
        verify_token = getattr(self._settings, "verify_token", "") or ""
        if mode == "subscribe" and token == verify_token:
            logger.info("Messenger webhook verification succeeded")
            return challenge
        logger.warning("Messenger webhook verification failed (mode=%s)", mode)
        return None

    async def handle_webhook_payload(
        self, body: bytes, signature: str
    ) -> bool:
        """Verify signature and dispatch a webhook payload to handlers.

        Returns True if processed successfully.
        """
        if not self.verify_webhook_signature(body, signature):
            logger.warning("Messenger invalid webhook signature")
            return False

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.exception("Messenger invalid JSON in webhook body")
            return False

        try:
            await self._handlers.handle_webhook(payload)
        except Exception:
            logger.exception("Messenger webhook dispatch failed")
            return False
        return True

    # ── Outbound messaging ────────────────────────────────

    async def send(
        self, channel_user_id: str, response: ChannelResponse
    ) -> None:
        """Send a formatted response to a Messenger user.

        The base contract requires this method not to raise — we log and
        absorb all exceptions on the outbound path.
        """
        if self._client is None:
            logger.error("Messenger cannot send — client not initialized")
            return

        try:
            page_access_token = getattr(self._settings, "page_access_token", "") or ""
            page_id = getattr(self._settings, "page_id", "") or ""
            api_version = (
                getattr(self._settings, "api_version", "") or DEFAULT_API_VERSION
            )

            # Send attachments first.
            for attachment in response.attachments or []:
                await send_attachment(
                    recipient_id=channel_user_id,
                    attachment=attachment,
                    page_access_token=page_access_token,
                    page_id=page_id,
                    api_version=api_version,
                    client=self._client,
                )

            # Format and send text + interactive chunks.
            formatted = format_response(response)
            for msg in formatted:
                interactive = msg.interactive
                if interactive is None:
                    if msg.text:
                        await self._send_raw_text(channel_user_id, msg.text)
                    continue

                itype = interactive.get("type")
                if itype == "quick_replies":
                    await self._send_with_quick_replies(
                        channel_user_id,
                        interactive.get("text", "") or msg.text,
                        interactive.get("quick_replies", []),
                    )
                elif itype == "button_template":
                    await self._send_button_template(
                        channel_user_id,
                        interactive.get("text", "") or msg.text,
                        interactive.get("buttons", {}),
                    )
                elif msg.text:
                    # Unknown interactive shape — fall back to plain text.
                    await self._send_raw_text(channel_user_id, msg.text)
        except Exception:
            logger.exception(
                "Messenger send failed for %s", channel_user_id
            )

    async def send_notification(
        self, channel_user_id: str, text: str
    ) -> None:
        """Send a plain-text notification with messaging_type=UPDATE."""
        await self._send_raw_text(
            channel_user_id, text, messaging_type="UPDATE"
        )

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict[str, Any]]:
        """Parse a Messenger callback into (action_id, metadata).

        Accepts:
          * a full webhook payload (extracts mid from entry[0].messaging[0]),
          * a single messaging event dict,
          * a raw string (treated as the action_id).
        """
        if isinstance(raw_callback, str):
            return raw_callback, {}

        if isinstance(raw_callback, dict):
            # Full webhook payload?
            if "entry" in raw_callback:
                entries = raw_callback.get("entry") or []
                if entries:
                    messaging = entries[0].get("messaging") or []
                    if messaging:
                        return self.parse_callback(messaging[0])
                return "", raw_callback

            # Postback event?
            postback = raw_callback.get("postback") or {}
            if postback:
                return (
                    postback.get("payload", "") or postback.get("mid", ""),
                    raw_callback,
                )

            # Message event with quick_reply?
            message = raw_callback.get("message") or {}
            qr = message.get("quick_reply") or {}
            if qr.get("payload"):
                return qr.get("payload", ""), raw_callback

            mid = message.get("mid") or raw_callback.get("mid", "")
            return mid, raw_callback

        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check connectivity by calling the Graph API /me endpoint.

        Uses the bearer-token-bearing client to fetch /{api_version}/me — a
        200 indicates the page access token is valid and reachable.
        """
        if self._client is None:
            return False
        try:
            api_version = (
                getattr(self._settings, "api_version", "") or DEFAULT_API_VERSION
            )
            url = f"{GRAPH_API_BASE}/{api_version}/me"
            resp = await self._client.get(url)
            ok = resp.status_code == 200
            if not ok:
                logger.warning(
                    "Messenger health check returned HTTP %s", resp.status_code
                )
            return ok
        except httpx.RequestError:
            logger.exception("Messenger health check network error")
            return False
        except Exception:
            logger.exception("Messenger health check failed")
            return False

    # ── Private helpers ───────────────────────────────────

    def _messages_url(self) -> str:
        api_version = (
            getattr(self._settings, "api_version", "") or DEFAULT_API_VERSION
        )
        return f"{GRAPH_API_BASE}/{api_version}/me/messages"

    async def _post_send(self, payload: dict[str, Any], recipient: str) -> None:
        """POST a Send API payload, logging and absorbing all errors."""
        if self._client is None:
            logger.error("Messenger cannot POST — client not initialized")
            return
        try:
            resp = await self._client.post(self._messages_url(), json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text[:512]
            except Exception:
                body = ""
            logger.error(
                "Messenger Send API HTTP %s for %s: %s",
                exc.response.status_code,
                recipient,
                body,
            )
        except httpx.RequestError:
            logger.exception("Messenger Send API network error for %s", recipient)
        except Exception:
            logger.exception("Messenger Send API unexpected error for %s", recipient)

    async def _send_raw_text(
        self,
        recipient: str,
        text: str,
        messaging_type: str = "RESPONSE",
    ) -> None:
        """Send a plain text message via the Graph API."""
        if not text:
            return
        payload = {
            "recipient": {"id": recipient},
            "messaging_type": messaging_type,
            "message": {"text": text},
        }
        await self._post_send(payload, recipient)

    async def _send_with_quick_replies(
        self,
        recipient: str,
        text: str,
        quick_replies: list[dict[str, Any]],
        messaging_type: str = "RESPONSE",
    ) -> None:
        """Send a text message with attached quick_replies."""
        body: dict[str, Any] = {"text": text}
        if quick_replies:
            body["quick_replies"] = quick_replies
        payload = {
            "recipient": {"id": recipient},
            "messaging_type": messaging_type,
            "message": body,
        }
        await self._post_send(payload, recipient)

    async def _send_button_template(
        self,
        recipient: str,
        text: str,
        button_template: dict[str, Any],
        messaging_type: str = "RESPONSE",
    ) -> None:
        """Send a button-template attachment to the recipient.

        ``button_template`` is the full template attachment object built by
        ``formatter.build_button_template`` — i.e. {"type": "template",
        "payload": {"template_type": "button", "text": ..., "buttons": [...]}}.
        """
        if not button_template:
            # Fall back to plain text if the template was omitted.
            await self._send_raw_text(recipient, text, messaging_type)
            return

        payload = {
            "recipient": {"id": recipient},
            "messaging_type": messaging_type,
            "message": {"attachment": button_template},
        }
        await self._post_send(payload, recipient)
