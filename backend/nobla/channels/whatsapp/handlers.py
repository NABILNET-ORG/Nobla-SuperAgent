"""WhatsApp webhook payload handlers (Phase 5-Channels).

Parses inbound Cloud API webhook notifications, extracts user context,
routes messages through the linking + executor pipeline, and emits
events on the bus.

Keyword commands (since WhatsApp has no slash-command system):
  "!start"  — welcome + pairing prompt
  "!link"   — start/complete linking
  "!unlink" — remove linked account
  "!status" — show link + health status
"""

from __future__ import annotations

import logging
from typing import Any

from nobla.channels.base import (
    Attachment,
    ChannelMessage,
    ChannelResponse,
)
from nobla.channels.whatsapp.formatter import format_response
from nobla.channels.whatsapp.media import (
    detect_attachment_type,
    download_attachment,
)
from nobla.channels.whatsapp.models import (
    CHANNEL_NAME,
    MESSAGE_STATUSES,
    SUPPORTED_MESSAGE_TYPES,
    WhatsAppUserContext,
)

logger = logging.getLogger(__name__)

# Type aliases for the services we depend on (avoid hard import cycles).
# At runtime these are UserLinkingService and NoblaEventBus instances.
LinkingService = Any
EventBus = Any


class WhatsAppHandlers:
    """Inbound message + status handlers for the WhatsApp Cloud API webhook.

    Args:
        linking: UserLinkingService for resolving/creating links.
        event_bus: NoblaEventBus for emitting channel events.
        access_token: Graph API access token (for media downloads).
        phone_number_id: The bot's phone number ID.
        api_version: Graph API version string.
        max_file_size_mb: Max attachment size to download.
    """

    def __init__(
        self,
        linking: LinkingService,
        event_bus: EventBus,
        access_token: str = "",
        phone_number_id: str = "",
        api_version: str = "v21.0",
        max_file_size_mb: int = 100,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._bot_phone: str | None = None  # Set from adapter after start

    def set_bot_phone(self, phone: str) -> None:
        """Set the bot's phone number for mention detection."""
        self._bot_phone = phone

    # ── Webhook entry point ───────────────────────────────

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process a full Cloud API webhook notification payload.

        A single webhook POST can contain multiple entries and changes.
        """
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                value = change.get("value", {})
                await self._process_value(value)

    async def _process_value(self, value: dict[str, Any]) -> None:
        """Route a single webhook value block to message or status handlers."""
        # Handle message status updates
        for status in value.get("statuses", []):
            await self._handle_status(status)

        # Handle inbound messages
        contacts = {c["wa_id"]: c for c in value.get("contacts", [])}
        metadata = value.get("metadata", {})

        for message in value.get("messages", []):
            msg_type = message.get("type", "")
            if msg_type not in SUPPORTED_MESSAGE_TYPES:
                logger.debug("Ignoring unsupported message type: %s", msg_type)
                continue

            wa_id = message.get("from", "")
            contact = contacts.get(wa_id, {})
            profile_name = contact.get("profile", {}).get("name", "")

            ctx = WhatsAppUserContext(
                wa_id=wa_id,
                display_name=profile_name,
                message_id=message.get("id", ""),
                chat_id=wa_id,  # 1-on-1; group support adds group JID later
                timestamp=message.get("timestamp", ""),
                raw_extras={"metadata": metadata},
            )

            await self._handle_message(ctx, message)

    # ── Message handling ──────────────────────────────────

    async def _handle_message(
        self, ctx: WhatsAppUserContext, raw_message: dict[str, Any]
    ) -> None:
        """Process a single inbound message."""
        msg_type = raw_message.get("type", "")

        # Extract text content
        text = ""
        if msg_type == "text":
            text = raw_message.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = raw_message.get("interactive", {})
            itype = interactive.get("type", "")
            if itype == "button_reply":
                text = interactive.get("button_reply", {}).get("title", "")
                # Also handle as callback
                action_id = interactive.get("button_reply", {}).get("id", "")
                await self._handle_interactive_reply(ctx, action_id, text)
                return
            elif itype == "list_reply":
                text = interactive.get("list_reply", {}).get("title", "")
                action_id = interactive.get("list_reply", {}).get("id", "")
                await self._handle_interactive_reply(ctx, action_id, text)
                return
        elif msg_type == "button":
            text = raw_message.get("button", {}).get("text", "")
            payload_val = raw_message.get("button", {}).get("payload", "")
            if payload_val:
                await self._handle_interactive_reply(ctx, payload_val, text)
                return
        elif msg_type == "reaction":
            await self._handle_reaction(ctx, raw_message)
            return

        # Check for keyword commands
        stripped = text.strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_command(ctx, stripped, text)
            return

        # Download attachments if present
        attachments = await self._extract_attachments(raw_message, msg_type)

        # Resolve linked user
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_pairing_prompt(ctx, code)
            return

        # Build ChannelMessage
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=linked.nobla_user_id,
            conversation_id=getattr(linked, "conversation_id", None),
            attachments=attachments,
            reply_to=raw_message.get("context", {}).get("id"),
            metadata={
                "wa_message_id": ctx.message_id,
                "display_name": ctx.display_name,
                "timestamp": ctx.timestamp,
            },
        )

        # Emit inbound event
        await self._emit_event(
            "channel.message.in",
            {
                "channel": CHANNEL_NAME,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
                "content": text,
                "has_attachments": len(attachments) > 0,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Keyword commands ──────────────────────────────────

    async def _dispatch_command(
        self, ctx: WhatsAppUserContext, stripped: str, raw_text: str
    ) -> None:
        """Route keyword commands."""
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
        if handler:
            await handler(ctx, args)

    async def _cmd_start(self, ctx: WhatsAppUserContext, args: str) -> None:
        """Welcome message + pairing code."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.chat_id_str,
                f"Welcome back, {ctx.display_name}! You're linked to Nobla. Send any message to chat.",
            )
            return

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        await self._send_text(
            ctx.chat_id_str,
            f"Welcome to *Nobla Agent*, {ctx.display_name}!\n\n"
            f"To link your account, use code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n\n"
            f"Code expires in 5 minutes.",
        )

    async def _cmd_link(self, ctx: WhatsAppUserContext, args: str) -> None:
        """Link WhatsApp to Nobla account."""
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_text(
                ctx.chat_id_str,
                f"Your pairing code: `{code}`\n"
                f"Enter this in the Nobla app, or type: `!link <user_id>`",
            )
            return

        nobla_user_id = args.strip()
        try:
            await self._linking.link(CHANNEL_NAME, ctx.user_id_str, nobla_user_id)
            await self._send_text(
                ctx.chat_id_str,
                f"Linked to Nobla account `{nobla_user_id}`.",
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
        except Exception:
            logger.exception("Link failed for %s", ctx.user_id_str)
            await self._send_text(ctx.chat_id_str, "Link failed. Check your user ID.")

    async def _cmd_unlink(self, ctx: WhatsAppUserContext, args: str) -> None:
        """Unlink WhatsApp from Nobla account."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await self._send_text(ctx.chat_id_str, "Not currently linked.")
            return

        nobla_user_id = linked.nobla_user_id
        await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
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

    async def _cmd_status(self, ctx: WhatsAppUserContext, args: str) -> None:
        """Show linking status."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.chat_id_str,
                f"*Status:* Linked\n"
                f"*Nobla ID:* `{linked.nobla_user_id}`\n"
                f"*Channel:* WhatsApp ({ctx.user_id_str})",
            )
        else:
            await self._send_text(
                ctx.chat_id_str,
                "*Status:* Not linked\nUse `!link` to connect your account.",
            )

    # ── Interactive replies (button/list callbacks) ───────

    async def _handle_interactive_reply(
        self, ctx: WhatsAppUserContext, action_id: str, title: str
    ) -> None:
        """Handle a button or list reply as a callback action."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            return

        await self._emit_event(
            "channel.callback",
            {
                "channel": CHANNEL_NAME,
                "action_id": action_id,
                "title": title,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
            },
            user_id=linked.nobla_user_id,
        )

    async def _handle_reaction(
        self, ctx: WhatsAppUserContext, raw_message: dict[str, Any]
    ) -> None:
        """Handle a reaction emoji on a message."""
        reaction = raw_message.get("reaction", {})
        emoji = reaction.get("emoji", "")
        reacted_msg_id = reaction.get("message_id", "")

        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            return

        await self._emit_event(
            "channel.reaction",
            {
                "channel": CHANNEL_NAME,
                "emoji": emoji,
                "message_id": reacted_msg_id,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Status updates ────────────────────────────────────

    async def _handle_status(self, status: dict[str, Any]) -> None:
        """Handle a message status update (sent/delivered/read/failed)."""
        status_value = status.get("status", "")
        if status_value not in MESSAGE_STATUSES:
            return

        await self._emit_event(
            "channel.message.status",
            {
                "channel": CHANNEL_NAME,
                "status": status_value,
                "message_id": status.get("id", ""),
                "recipient": status.get("recipient_id", ""),
                "timestamp": status.get("timestamp", ""),
            },
        )

    # ── Attachment extraction ─────────────────────────────

    async def _extract_attachments(
        self, raw_message: dict[str, Any], msg_type: str
    ) -> list[Attachment]:
        """Download and convert media attachments from the raw message."""
        media_types = {"image", "audio", "video", "document", "sticker"}
        if msg_type not in media_types:
            return []

        media_obj = raw_message.get(msg_type, {})
        media_id = media_obj.get("id")
        mime_type = media_obj.get("mime_type", "application/octet-stream")

        if not media_id:
            return []

        attachment = await download_attachment(
            media_id=media_id,
            mime_type=mime_type,
            access_token=self._access_token,
            api_version=self._api_version,
            max_size_bytes=self._max_file_size_bytes,
        )

        return [attachment] if attachment else []

    # ── Helpers ───────────────────────────────────────────

    # Outbound text helper — the adapter's send() is used for full
    # ChannelResponse messages; this is for simple handler replies.
    _send_text_fn: Any = None  # Set by adapter after construction

    def set_send_fn(self, fn: Any) -> None:
        """Register the adapter's raw send function for handler replies."""
        self._send_text_fn = fn

    async def _send_text(self, recipient: str, text: str) -> None:
        """Send a plain text message via the registered send function."""
        if self._send_text_fn:
            await self._send_text_fn(recipient, text)
        else:
            logger.warning("No send function registered — cannot reply to %s", recipient)

    async def _send_pairing_prompt(
        self, ctx: WhatsAppUserContext, code: str
    ) -> None:
        """Send the standard pairing prompt to an unlinked user."""
        await self._send_text(
            ctx.chat_id_str,
            f"Hi {ctx.display_name}! To use Nobla, link your account.\n\n"
            f"Pairing code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n"
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
            logger.exception("Failed to emit %s event", event_type)
