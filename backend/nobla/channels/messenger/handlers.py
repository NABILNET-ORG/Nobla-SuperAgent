"""Facebook Messenger webhook payload handlers (Phase 5-Channels).

Parses inbound Messenger Platform webhook notifications, extracts user
context, routes messages through the linking pipeline, and emits events on
the bus.

Keyword commands (Messenger has no slash-command system):
  "!start"  — welcome + pairing prompt
  "!link"   — start/complete linking
  "!unlink" — remove linked account
  "!status" — show link + health status

Messenger webhook shape (object="page"):
    {"object": "page",
     "entry": [{"id": <page_id>, "time": <ms>,
                "messaging": [<event>, ...]}]}

Each event is one of: message, postback, delivery, read, optin, referral,
account_linking. We currently process message, postback, delivery, read.
"""

from __future__ import annotations

import logging
from typing import Any

from nobla.channels.base import (
    Attachment,
    AttachmentType,
    ChannelMessage,
)
from nobla.channels.messenger.media import (
    download_attachment,
    download_attachment_from_url,
)
from nobla.channels.messenger.models import (
    CHANNEL_NAME,
    DEFAULT_API_VERSION,
    MessengerUserContext,
)

logger = logging.getLogger(__name__)

# Type aliases for the services we depend on (avoid hard import cycles).
# At runtime these are UserLinkingService and NoblaEventBus instances.
LinkingService = Any
EventBus = Any


class MessengerHandlers:
    """Inbound message + postback + status handlers for the Messenger webhook.

    Args:
        linking: UserLinkingService for resolving/creating links.
        event_bus: NoblaEventBus for emitting channel events.
        page_access_token: Page Access Token (for Send API + media downloads).
        page_id: The bot Page's numeric ID.
        api_version: Graph API version string (e.g. "v21.0").
        max_file_size_mb: Max attachment size to download.
    """

    def __init__(
        self,
        linking: LinkingService,
        event_bus: EventBus,
        page_access_token: str = "",
        page_id: str = "",
        api_version: str = DEFAULT_API_VERSION,
        max_file_size_mb: int = 100,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._page_access_token = page_access_token
        self._page_id = page_id
        self._api_version = api_version
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        # Outbound text helper — set by the adapter after construction.
        self._send_text_fn: Any = None

    def set_send_fn(self, fn: Any) -> None:
        """Register the adapter's raw send function for handler replies."""
        self._send_text_fn = fn

    # ── Webhook entry point ───────────────────────────────

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process a full Messenger webhook notification payload.

        A single webhook POST can carry multiple entries; each entry's
        ``messaging`` list contains one or more events.
        """
        if payload.get("object") != "page":
            logger.debug(
                "Messenger webhook ignored: object=%r", payload.get("object")
            )
            return

        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                await self._dispatch_event(event)

    async def _dispatch_event(self, event: dict[str, Any]) -> None:
        """Route a single messaging event to the correct handler."""
        try:
            if "message" in event:
                await self._handle_message(event)
            elif "postback" in event:
                await self._handle_postback(event)
            elif "delivery" in event:
                await self._handle_delivery(event)
            elif "read" in event:
                await self._handle_read(event)
            else:
                logger.debug(
                    "Messenger event ignored (no recognized field): keys=%s",
                    list(event.keys()),
                )
        except Exception:
            logger.exception("Messenger event dispatch failed")

    # ── Message handling ──────────────────────────────────

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """Process an inbound 'message' event from the messaging array."""
        sender = event.get("sender", {}) or {}
        recipient = event.get("recipient", {}) or {}
        message = event.get("message", {}) or {}

        psid = sender.get("id", "")
        if not psid:
            logger.warning("Messenger message event missing sender.id")
            return

        # Echo events (sent by our page) carry message.is_echo=True; ignore.
        if message.get("is_echo"):
            return

        ctx = MessengerUserContext(
            psid=psid,
            display_name=None,  # Resolved via Graph /{psid} if needed; not done inline.
            message_id=message.get("mid", ""),
            chat_id=psid,
            is_group=False,
            is_bot_mentioned=False,
            is_reply_to_bot=bool(message.get("reply_to")),
            timestamp=int(event.get("timestamp", 0) or 0),
            raw_extras={"recipient": recipient, "thread_type": event.get("thread_type")},
        )

        text = (message.get("text") or "").strip()

        # Quick replies arrive as text messages with a 'quick_reply' object
        # carrying the postback payload.
        quick_reply = message.get("quick_reply") or {}
        qr_payload = quick_reply.get("payload")
        if qr_payload:
            await self._handle_interactive_reply(ctx, qr_payload, text)
            return

        # Keyword commands.
        stripped = text.strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_command(ctx, stripped, text)
            return

        # Extract attachments (images, video, audio, files, location share).
        attachments = await self._extract_attachments(message)

        # Resolve linked user.
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_pairing_prompt(ctx, code)
            return

        # Build ChannelMessage.
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=linked.nobla_user_id,
            conversation_id=getattr(linked, "conversation_id", None),
            attachments=attachments,
            reply_to=(message.get("reply_to") or {}).get("mid"),
            metadata={
                "messenger_message_id": ctx.message_id,
                "display_name": ctx.display_name,
                "timestamp": ctx.timestamp,
                "page_id": recipient.get("id", self._page_id),
            },
        )

        await self._emit_event(
            "channel.message.in",
            {
                "channel": CHANNEL_NAME,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
                "content": text,
                "has_attachments": len(channel_msg.attachments) > 0,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Postback handling ─────────────────────────────────

    async def _handle_postback(self, event: dict[str, Any]) -> None:
        """Handle a postback (button press) event."""
        sender = event.get("sender", {}) or {}
        psid = sender.get("id", "")
        if not psid:
            logger.warning("Messenger postback event missing sender.id")
            return

        postback = event.get("postback", {}) or {}
        payload = postback.get("payload", "")
        title = postback.get("title", "")
        mid = postback.get("mid", "")

        ctx = MessengerUserContext(
            psid=psid,
            display_name=None,
            message_id=mid,
            chat_id=psid,
            timestamp=int(event.get("timestamp", 0) or 0),
            raw_extras={"postback": postback},
        )

        # Treat keyword-style payloads (e.g. "!link", "GET_STARTED") with
        # the same command pipeline as text. Otherwise emit a callback event.
        stripped = (payload or "").strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_command(ctx, stripped, payload)
            return

        if payload == "GET_STARTED":
            # Synthesize a !start command so onboarding flows uniformly.
            await self._dispatch_command(ctx, "!start", "!start")
            return

        await self._handle_interactive_reply(ctx, payload, title)

    # ── Delivery / read receipts ──────────────────────────

    async def _handle_delivery(self, event: dict[str, Any]) -> None:
        """Handle a delivery confirmation event."""
        sender = event.get("sender", {}) or {}
        delivery = event.get("delivery", {}) or {}

        await self._emit_event(
            "channel.message.delivered",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": sender.get("id", ""),
                "watermark": delivery.get("watermark", 0),
                "mids": delivery.get("mids", []),
                "timestamp": int(event.get("timestamp", 0) or 0),
            },
        )

    async def _handle_read(self, event: dict[str, Any]) -> None:
        """Handle a read receipt event."""
        sender = event.get("sender", {}) or {}
        read = event.get("read", {}) or {}

        await self._emit_event(
            "channel.message.read",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": sender.get("id", ""),
                "watermark": read.get("watermark", 0),
                "timestamp": int(event.get("timestamp", 0) or 0),
            },
        )

    # ── Keyword commands ──────────────────────────────────

    async def _dispatch_command(
        self,
        ctx: MessengerUserContext,
        stripped: str,
        raw_text: str,
    ) -> bool:
        """Route keyword commands. Returns True if handled."""
        parts = stripped.split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "!start": self._cmd_start,
            "!link": self._cmd_link,
            "!unlink": self._cmd_unlink,
            "!status": self._cmd_status,
        }

        handler = handlers.get(cmd)
        if not handler:
            return False

        await handler(ctx, args)
        return True

    async def _cmd_start(self, ctx: MessengerUserContext, args: str) -> None:
        """Welcome message + pairing code."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            display = ctx.display_name or "there"
            await self._send_text(
                ctx.chat_id_str,
                f"Welcome back, {display}! You're linked to Nobla. Send any message to chat.",
            )
            return

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        display = ctx.display_name or "there"
        await self._send_text(
            ctx.chat_id_str,
            f"Welcome to Nobla Agent, {display}!\n\n"
            f"To link your account, use code: {code}\n"
            f"Or type: !link <your_nobla_user_id>\n\n"
            f"Code expires in 5 minutes.",
        )

    async def _cmd_link(self, ctx: MessengerUserContext, args: str) -> None:
        """Link Messenger PSID to a Nobla account."""
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_text(
                ctx.chat_id_str,
                f"Your pairing code: {code}\n"
                f"Enter this in the Nobla app, or type: !link <user_id>",
            )
            return

        nobla_user_id = args.strip()
        await self._link_user(ctx, nobla_user_id)

    async def _cmd_unlink(self, ctx: MessengerUserContext, args: str) -> None:
        """Unlink Messenger PSID from any Nobla account."""
        await self._unlink_user(ctx)

    async def _cmd_status(self, ctx: MessengerUserContext, args: str) -> None:
        """Show linking status."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.chat_id_str,
                f"Status: Linked\n"
                f"Nobla ID: {linked.nobla_user_id}\n"
                f"Channel: Messenger ({ctx.user_id_str})",
            )
        else:
            await self._send_text(
                ctx.chat_id_str,
                "Status: Not linked\nUse !link to connect your account.",
            )

    # ── Linking helpers ───────────────────────────────────

    async def _link_user(self, ctx: MessengerUserContext, code: str) -> None:
        """Complete a linking flow and emit channel.user.linked."""
        nobla_user_id = code.strip()
        if not nobla_user_id:
            await self._send_text(ctx.chat_id_str, "Missing code or user id.")
            return

        try:
            await self._linking.link(CHANNEL_NAME, ctx.user_id_str, nobla_user_id)
        except Exception:
            logger.exception("Messenger link failed for %s", ctx.user_id_str)
            await self._send_text(
                ctx.chat_id_str, "Link failed. Check your code or user ID."
            )
            return

        await self._send_text(
            ctx.chat_id_str,
            f"Linked to Nobla account {nobla_user_id}.",
        )
        await self._emit_event(
            "channel.user.linked",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            },
            user_id=nobla_user_id,
        )

    async def _unlink_user(self, ctx: MessengerUserContext) -> None:
        """Tear down a link and emit channel.user.unlinked."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await self._send_text(ctx.chat_id_str, "Not currently linked.")
            return

        nobla_user_id = linked.nobla_user_id
        try:
            await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
        except Exception:
            logger.exception("Messenger unlink failed for %s", ctx.user_id_str)
            await self._send_text(ctx.chat_id_str, "Unlink failed; try again later.")
            return

        await self._send_text(ctx.chat_id_str, "Account unlinked.")
        await self._emit_event(
            "channel.user.unlinked",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            },
            user_id=nobla_user_id,
        )

    # ── Interactive replies (quick_reply / postback callbacks) ─

    async def _handle_interactive_reply(
        self,
        ctx: MessengerUserContext,
        action_id: str,
        title: str,
    ) -> None:
        """Handle a quick reply or postback as a callback action."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        nobla_user_id = linked.nobla_user_id if linked else None

        await self._emit_event(
            "channel.callback",
            {
                "channel": CHANNEL_NAME,
                "action_id": action_id,
                "title": title,
                "user_id": nobla_user_id,
                "channel_user_id": ctx.user_id_str,
            },
            user_id=nobla_user_id,
        )

    # ── Attachment extraction ─────────────────────────────

    async def _extract_attachments(
        self, message: dict[str, Any]
    ) -> list[Attachment]:
        """Download and convert media attachments from a Messenger message."""
        raw_attachments = message.get("attachments") or []
        if not raw_attachments:
            return []

        results: list[Attachment] = []
        for raw in raw_attachments:
            att_type = raw.get("type", "")
            payload = raw.get("payload") or {}

            # Location attachments carry coordinates, no media to download.
            if att_type == "location":
                # Surface as a synthetic Attachment with metadata for the brain.
                coords = payload.get("coordinates") or {}
                lat = coords.get("lat")
                lon = coords.get("long")
                if lat is None or lon is None:
                    continue
                # Encode coordinates in filename so downstream code can recover
                # them without extending the base ``Attachment`` model.
                results.append(
                    Attachment(
                        type=AttachmentType.DOCUMENT,
                        filename=f"location-{lat}-{lon}.txt",
                        mime_type="text/plain",
                        size_bytes=0,
                        url=None,
                        data=None,
                    )
                )
                continue

            cdn_url = payload.get("url")
            attachment_id = payload.get("attachment_id")

            attachment: Attachment | None = None
            if cdn_url:
                attachment = await download_attachment_from_url(
                    cdn_url=cdn_url,
                    page_access_token=self._page_access_token,
                    timeout=30.0,
                    max_size_bytes=self._max_file_size_bytes,
                )
            elif attachment_id:
                attachment = await download_attachment(
                    attachment_id=attachment_id,
                    page_access_token=self._page_access_token,
                    api_version=self._api_version,
                    timeout=30.0,
                    max_size_bytes=self._max_file_size_bytes,
                )
            else:
                logger.warning(
                    "Messenger attachment has neither url nor attachment_id (type=%s)",
                    att_type,
                )
                continue

            if attachment is not None:
                results.append(attachment)

        return results

    # ── Helpers ───────────────────────────────────────────

    async def _send_text(self, recipient: str, text: str) -> None:
        """Send a plain text message via the registered send function."""
        if self._send_text_fn is not None:
            await self._send_text_fn(recipient, text)
        else:
            logger.warning(
                "Messenger handler has no send function — cannot reply to %s",
                recipient,
            )

    async def _send_pairing_prompt(
        self, ctx: MessengerUserContext, code: str
    ) -> None:
        """Send the standard pairing prompt to an unlinked user."""
        display = ctx.display_name or "there"
        await self._send_text(
            ctx.chat_id_str,
            f"Hi {display}! To use Nobla, link your account.\n\n"
            f"Pairing code: {code}\n"
            f"Or type: !link <your_nobla_user_id>\n"
            f"Code expires in 5 minutes.",
        )

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit an event on the bus if available."""
        if not self._event_bus:
            return
        try:
            from nobla.events.models import NoblaEvent

            event = NoblaEvent(
                event_type=event_type,
                source=CHANNEL_NAME,
                payload=payload,
                user_id=user_id,
            )
            await self._event_bus.publish(event)
        except Exception:
            logger.exception("Messenger failed to emit %s event", event_type)
