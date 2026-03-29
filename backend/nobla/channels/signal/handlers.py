"""Signal envelope handlers (Phase 5-Channels).

Parses inbound signal-cli JSON-RPC envelopes, extracts user context,
routes messages through the linking + executor pipeline, and emits
events on the bus.

Text commands (since Signal has no slash-command or bot API):
  /start  -- welcome + pairing prompt
  /link   -- start/complete linking
  /unlink -- remove linked account
  /status -- show link + health status
"""

from __future__ import annotations

import logging
from typing import Any

from nobla.channels.base import (
    Attachment,
    ChannelMessage,
)
from nobla.channels.signal.media import load_attachment_from_path
from nobla.channels.signal.models import CHANNEL_NAME, SignalUserContext

logger = logging.getLogger(__name__)

# Type aliases to avoid hard import cycles.
LinkingService = Any
EventBus = Any


class SignalHandlers:
    """Inbound message + receipt handlers for the signal-cli JSON-RPC daemon.

    Args:
        linking_service: UserLinkingService for resolving/creating links.
        event_bus: NoblaEventBus for emitting channel events.
        bot_phone_number: The bot's own phone number (E.164 format).
    """

    def __init__(
        self,
        linking_service: LinkingService,
        event_bus: EventBus,
        bot_phone_number: str = "",
    ) -> None:
        self._linking = linking_service
        self._event_bus = event_bus
        self._bot_phone = bot_phone_number
        self._bot_uuid: str = ""
        self._data_dir: str = ""
        self._send_fn: Any = None
        self._send_receipt_fn: Any = None

    def set_send_fn(self, fn: Any) -> None:
        """Register the adapter's raw send function for handler replies."""
        self._send_fn = fn

    def set_send_receipt_fn(self, fn: Any) -> None:
        """Register the adapter's read receipt function."""
        self._send_receipt_fn = fn

    def set_bot_uuid(self, uuid: str) -> None:
        """Set the bot's UUID for group mention detection."""
        self._bot_uuid = uuid

    def set_data_dir(self, data_dir: str) -> None:
        """Set the data directory for attachment file paths."""
        self._data_dir = data_dir

    # ── Main dispatcher ───────────────────────────────────

    async def handle_message(self, envelope: dict[str, Any]) -> None:
        """Process a single signal-cli envelope.

        Routes to data message, receipt, or ignores unsupported types
        (e.g. typingMessage, syncMessage).
        """
        source = envelope.get("source", "")
        source_uuid = envelope.get("sourceUuid", "")

        # Ignore own messages
        if source == self._bot_phone:
            return

        # Route by envelope content
        if "dataMessage" in envelope:
            await self._handle_data_message(envelope, source, source_uuid)
        elif "receiptMessage" in envelope:
            await self._handle_receipt(envelope, source, source_uuid)
        # typingMessage, syncMessage, etc. are silently ignored

    # ── Data message handling ─────────────────────────────

    async def _handle_data_message(
        self,
        envelope: dict[str, Any],
        source: str,
        source_uuid: str,
    ) -> None:
        """Process a data message (text, attachments, group info)."""
        data = envelope.get("dataMessage", {})
        timestamp = envelope.get("timestamp", 0)
        text = data.get("message", "") or ""
        expires_in = data.get("expiresInSeconds", 0)

        # Group detection
        group_info = data.get("groupInfo")
        is_group = group_info is not None
        group_id = group_info.get("groupId") if group_info else None

        # Mention detection for group activation
        is_bot_mentioned = False
        if is_group:
            mentions = data.get("mentions", [])
            is_bot_mentioned = self._check_bot_mentioned(mentions)
            if not is_bot_mentioned:
                # In groups, only respond when mentioned
                return

        ctx = SignalUserContext(
            source_number=source,
            source_uuid=source_uuid,
            is_group=is_group,
            is_bot_mentioned=is_bot_mentioned,
            timestamp=timestamp,
            group_id=group_id,
            expires_in_seconds=expires_in,
        )

        # Check for text commands (case-insensitive)
        stripped = text.strip().lower()
        if stripped.startswith("/"):
            handled = await self._dispatch_command(ctx, stripped, text)
            if handled:
                return

        # Extract attachments
        attachments = self._extract_attachments(data)

        # Resolve linked user
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_pairing_prompt(ctx, code)
            return

        # Build metadata
        metadata: dict[str, Any] = {
            "source_uuid": source_uuid,
            "timestamp": timestamp,
        }
        if expires_in > 0:
            metadata["disappearing"] = True
            metadata["expires_in_seconds"] = expires_in

        nobla_user_id = (
            linked.nobla_user_id
            if hasattr(linked, "nobla_user_id")
            else str(linked)
        )

        # Build ChannelMessage
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=nobla_user_id,
            conversation_id=getattr(linked, "conversation_id", None),
            attachments=attachments,
            metadata=metadata,
        )

        # Emit inbound event
        await self._emit_event(
            "channel.message.in",
            {
                "channel": CHANNEL_NAME,
                "user_id": nobla_user_id,
                "channel_user_id": ctx.user_id_str,
                "content": text,
                "has_attachments": len(attachments) > 0,
                "metadata": metadata,
            },
            user_id=nobla_user_id,
        )

        # Send read receipt
        if self._send_receipt_fn:
            await self._send_receipt_fn(source, timestamp)

    def _check_bot_mentioned(self, mentions: list[dict[str, Any]]) -> bool:
        """Check if the bot is mentioned in the mentions array."""
        for mention in mentions:
            mention_uuid = mention.get("uuid", "")
            if mention_uuid == self._bot_uuid:
                return True
            # Also check by phone number pattern
            mention_number = mention.get("number", "")
            if mention_number and mention_number == self._bot_phone:
                return True
        return False

    # ── Commands ──────────────────────────────────────────

    async def _dispatch_command(
        self, ctx: SignalUserContext, stripped: str, raw_text: str
    ) -> bool:
        """Route text commands. Returns True if a command was handled."""
        parts = stripped.split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/start": self._cmd_start,
            "/link": self._cmd_link,
            "/unlink": self._cmd_unlink,
            "/status": self._cmd_status,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(ctx, args)
            return True
        return False

    async def _cmd_start(self, ctx: SignalUserContext, args: str) -> None:
        """Welcome message + pairing code."""
        linked = await self._linking.resolve(
            CHANNEL_NAME, ctx.user_id_str
        )
        if linked:
            await self._send_text(
                ctx.chat_id_str,
                "Welcome back! You're linked to Nobla. Send any message to chat.",
            )
            return

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        await self._send_text(
            ctx.chat_id_str,
            f"Welcome to Nobla Agent!\n\n"
            f"To link your account, use code: {code}\n"
            f"Or type: /link <your_nobla_user_id>\n\n"
            f"Code expires in 5 minutes.",
        )

    async def _cmd_link(self, ctx: SignalUserContext, args: str) -> None:
        """Link Signal to Nobla account."""
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_text(
                ctx.chat_id_str,
                f"Your pairing code: {code}\n"
                f"Enter this in the Nobla app, or type: /link <user_id>",
            )
            return

        nobla_user_id = args.strip()
        try:
            await self._linking.link(
                CHANNEL_NAME, ctx.user_id_str, nobla_user_id
            )
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
        except Exception:
            logger.exception("Link failed for %s", ctx.user_id_str)
            await self._send_text(
                ctx.chat_id_str, "Link failed. Check your user ID."
            )

    async def _cmd_unlink(self, ctx: SignalUserContext, args: str) -> None:
        """Unlink Signal from Nobla account."""
        linked = await self._linking.resolve(
            CHANNEL_NAME, ctx.user_id_str
        )
        if not linked:
            await self._send_text(ctx.chat_id_str, "Not currently linked.")
            return

        nobla_user_id = (
            linked.nobla_user_id
            if hasattr(linked, "nobla_user_id")
            else str(linked)
        )
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

    async def _cmd_status(self, ctx: SignalUserContext, args: str) -> None:
        """Show linking status."""
        linked = await self._linking.resolve(
            CHANNEL_NAME, ctx.user_id_str
        )
        if linked:
            nobla_id = (
                linked.nobla_user_id
                if hasattr(linked, "nobla_user_id")
                else str(linked)
            )
            await self._send_text(
                ctx.chat_id_str,
                f"Status: Linked\n"
                f"Nobla ID: {nobla_id}\n"
                f"Channel: Signal ({ctx.user_id_str})",
            )
        else:
            await self._send_text(
                ctx.chat_id_str,
                "Status: Not linked\nUse /link to connect your account.",
            )

    # ── Receipts ──────────────────────────────────────────

    async def _handle_receipt(
        self,
        envelope: dict[str, Any],
        source: str,
        source_uuid: str,
    ) -> None:
        """Handle a receipt message (delivery, read, viewed)."""
        receipt = envelope.get("receiptMessage", {})
        receipt_type = receipt.get("type", "").lower()
        timestamps = receipt.get("timestamps", [])

        # Map Signal receipt types to status values
        status_map = {
            "delivery": "delivered",
            "read": "read",
            "viewed": "viewed",
        }
        status = status_map.get(receipt_type, receipt_type)

        for ts in timestamps:
            await self._emit_event(
                "channel.message.status",
                {
                    "channel": CHANNEL_NAME,
                    "status": status,
                    "source": source,
                    "timestamp": ts,
                },
            )

    # ── Attachment extraction ─────────────────────────────

    def _extract_attachments(
        self, data: dict[str, Any]
    ) -> list[Attachment]:
        """Load attachments from signal-cli file paths."""
        raw_attachments = data.get("attachments", [])
        attachments: list[Attachment] = []

        for raw in raw_attachments:
            content_type = raw.get("contentType", "application/octet-stream")
            filename = raw.get("filename", "")
            att_id = raw.get("id", "")

            # signal-cli stores attachments at a known path
            if self._data_dir and att_id:
                path = f"{self._data_dir}/attachments/{att_id}"
                try:
                    att = load_attachment_from_path(path, content_type)
                    attachments.append(att)
                except FileNotFoundError:
                    logger.warning(
                        "Attachment file not found: %s", path
                    )
            elif filename:
                try:
                    att = load_attachment_from_path(filename, content_type)
                    attachments.append(att)
                except FileNotFoundError:
                    logger.warning(
                        "Attachment file not found: %s", filename
                    )

        return attachments

    # ── Helpers ───────────────────────────────────────────

    async def _send_text(self, recipient: str, text: str) -> None:
        """Send a plain text message via the registered send function."""
        if self._send_fn:
            await self._send_fn(recipient, text)
        else:
            logger.warning(
                "No send function registered -- cannot reply to %s",
                recipient,
            )

    async def _send_pairing_prompt(
        self, ctx: SignalUserContext, code: str
    ) -> None:
        """Send the standard pairing prompt to an unlinked user."""
        await self._send_text(
            ctx.chat_id_str,
            f"Hi! To use Nobla, link your account.\n\n"
            f"Pairing code: {code}\n"
            f"Or type: /link <your_nobla_user_id>\n"
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
