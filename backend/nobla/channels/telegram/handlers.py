"""Telegram update handlers — commands, messages, callbacks (Phase 5A).

Each handler extracts a ``TelegramUserContext``, resolves the user via
``UserLinkingService``, and routes through the channel bridge to the
executor pipeline.  Unlinked users receive a pairing prompt.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from nobla.channels.base import Attachment, ChannelMessage, ChannelResponse
from nobla.channels.bridge import ChannelConnectionState, create_channel_connection
from nobla.channels.linking import UserLinkingService
from nobla.channels.telegram.media import download_attachment, extract_file_info
from nobla.channels.telegram.models import TelegramUserContext
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    from telegram import Bot, CallbackQuery, Message, Update
    from telegram.ext import ContextTypes

    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

CHANNEL_NAME = "telegram"


# ── Context extraction ────────────────────────────────────


def extract_user_context(
    update: Update,
    bot_username: str | None = None,
) -> TelegramUserContext | None:
    """Build a TelegramUserContext from an incoming Update.

    Returns None if the update has no usable message or callback.
    """
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return None

    is_group = chat.type in ("group", "supergroup")

    # Mention detection
    is_mentioned = False
    is_reply = False

    if is_group and bot_username:
        text = message.text or message.caption or ""
        is_mentioned = f"@{bot_username}" in text

        if message.reply_to_message and message.reply_to_message.from_user:
            is_reply = message.reply_to_message.from_user.username == bot_username

    return TelegramUserContext(
        chat_id=chat.id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        is_group=is_group,
        is_bot_mentioned=is_mentioned,
        is_reply_to_bot=is_reply,
        message_id=message.message_id,
    )


def should_process_group_message(ctx: TelegramUserContext) -> bool:
    """Check if a group message should be processed (mention-only mode)."""
    if not ctx.is_group:
        return True  # DMs always processed
    return ctx.is_bot_mentioned or ctx.is_reply_to_bot


def strip_bot_mention(text: str, bot_username: str | None) -> str:
    """Remove the @bot mention from message text."""
    if bot_username and f"@{bot_username}" in text:
        return text.replace(f"@{bot_username}", "").strip()
    return text


# ── Command handlers ──────────────────────────────────────


class TelegramHandlers:
    """Stateful handler collection wired to linking service and event bus."""

    def __init__(
        self,
        linking: UserLinkingService,
        event_bus: NoblaEventBus,
        bot_username: str | None = None,
        max_file_size_mb: int = 50,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._bot_username = bot_username
        self._max_file_size_mb = max_file_size_mb

    def set_bot_username(self, username: str) -> None:
        self._bot_username = username

    # ── /start ────────────────────────────────────────────

    async def cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start — send welcome and pairing instructions."""
        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        user_id_str = ctx.user_id_str
        linked = await self._linking.resolve(CHANNEL_NAME, user_id_str)

        if linked:
            await update.effective_message.reply_text(
                f"Welcome back! You're linked as {linked.nobla_user_id}."
            )
            return

        code = await self._linking.create_pairing_code(CHANNEL_NAME, user_id_str)
        await update.effective_message.reply_text(
            f"Welcome to Nobla Agent!\n\n"
            f"To link your account, enter this code in the Nobla app "
            f"or use /link <your_nobla_id>:\n\n"
            f"Pairing code: {code}\n\n"
            f"This code expires in 5 minutes."
        )

    # ── /link ─────────────────────────────────────────────

    async def cmd_link(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /link <nobla_user_id> — complete account pairing."""
        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        args = context.args or []
        if not args:
            await update.effective_message.reply_text(
                "Usage: /link <your_nobla_user_id>"
            )
            return

        nobla_user_id = args[0]
        user_id_str = ctx.user_id_str

        # Check if already linked
        existing = await self._linking.resolve(CHANNEL_NAME, user_id_str)
        if existing:
            await update.effective_message.reply_text(
                f"Already linked to {existing.nobla_user_id}. "
                f"Use /unlink first to change."
            )
            return

        # Create pairing code and immediately complete it
        code = await self._linking.create_pairing_code(CHANNEL_NAME, user_id_str)
        success = await self._linking.complete_pairing(code, nobla_user_id)

        if success:
            await update.effective_message.reply_text(
                f"Account linked to {nobla_user_id}. You can now send messages!"
            )
            await self._emit_event(
                "channel.user.linked",
                {"channel": CHANNEL_NAME, "channel_user_id": user_id_str,
                 "nobla_user_id": nobla_user_id},
                user_id=nobla_user_id,
            )
        else:
            await update.effective_message.reply_text(
                "Linking failed. Please try again."
            )

    # ── /unlink ───────────────────────────────────────────

    async def cmd_unlink(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /unlink — remove account link."""
        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        user_id_str = ctx.user_id_str
        linked = await self._linking.resolve(CHANNEL_NAME, user_id_str)

        if not linked:
            await update.effective_message.reply_text("No account linked.")
            return

        await self._linking.unlink(CHANNEL_NAME, user_id_str)
        await update.effective_message.reply_text(
            "Account unlinked. Use /start to link again."
        )
        await self._emit_event(
            "channel.user.unlinked",
            {"channel": CHANNEL_NAME, "channel_user_id": user_id_str,
             "nobla_user_id": linked.nobla_user_id},
            user_id=linked.nobla_user_id,
        )

    # ── /status ───────────────────────────────────────────

    async def cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status — show link status."""
        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await update.effective_message.reply_text(
                f"Linked to: {linked.nobla_user_id}\n"
                f"Tier: {linked.tier.name}\n"
                f"Telegram user: {ctx.username or ctx.user_id_str}"
            )
        else:
            await update.effective_message.reply_text(
                "Not linked. Use /start to begin pairing."
            )

    # ── Text messages ─────────────────────────────────────

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming text (and media) messages."""
        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        if not should_process_group_message(ctx):
            return

        # Resolve user
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await update.effective_message.reply_text(
                f"Please link your account first.\n"
                f"Pairing code: {code}\n"
                f"Enter this in the Nobla app, or use /link <your_nobla_id>"
            )
            return

        message = update.effective_message
        text = message.text or message.caption or ""
        text = strip_bot_mention(text, self._bot_username)

        # Download attachments
        attachments = await self._download_attachments(
            context.bot, message
        )

        # Build ChannelMessage
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=linked.nobla_user_id,
            attachments=attachments,
            reply_to=str(message.reply_to_message.message_id)
            if message.reply_to_message else None,
            metadata={
                "chat_id": ctx.chat_id,
                "message_id": ctx.message_id,
                "username": ctx.username,
                "is_group": ctx.is_group,
            },
        )

        # Build bridge connection
        conn = create_channel_connection(
            linked_user=linked,
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
        )

        # Emit inbound event
        await self._emit_event(
            "channel.message.in",
            {
                "message": {
                    "channel": channel_msg.channel,
                    "channel_user_id": channel_msg.channel_user_id,
                    "content": channel_msg.content,
                    "nobla_user_id": channel_msg.nobla_user_id,
                    "attachment_count": len(channel_msg.attachments),
                    "metadata": channel_msg.metadata,
                },
                "connection_id": conn.connection_id,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Callback queries (inline button presses) ──────────

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses."""
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()  # Acknowledge to Telegram

        ctx = extract_user_context(update, self._bot_username)
        if not ctx:
            return

        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await query.edit_message_text("Session expired. Use /start to re-link.")
            return

        action_id, metadata = self._parse_callback_data(query)

        await self._emit_event(
            "channel.callback",
            {
                "action_id": action_id,
                "metadata": metadata,
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Helpers ───────────────────────────────────────────

    def _parse_callback_data(
        self, query: CallbackQuery
    ) -> tuple[str, dict[str, Any]]:
        """Parse callback_data into (action_id, metadata).

        Expected format: "{domain}:{resource_id}:{verb}"
        e.g. "approval:req-123:approve"
        """
        data = query.data or ""
        parts = data.split(":")
        metadata: dict[str, Any] = {
            "raw_data": data,
            "message_id": query.message.message_id if query.message else None,
        }
        return data, metadata

    async def _download_attachments(
        self, bot: Bot, message: Message
    ) -> list[Attachment]:
        """Download all media from a Telegram message."""
        file_infos = extract_file_info(message)
        attachments: list[Attachment] = []

        for info in file_infos:
            attachment = await download_attachment(
                bot=bot,
                file_id=info["file_id"],
                filename=info["filename"],
                mime_type=info["mime_type"],
                file_size=info.get("file_size"),
                max_size_mb=self._max_file_size_mb,
            )
            if attachment:
                attachments.append(attachment)

        return attachments

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit a NoblaEvent on the event bus."""
        event = NoblaEvent(
            event_type=event_type,
            source=CHANNEL_NAME,
            payload=payload,
            user_id=user_id,
        )
        await self._event_bus.emit(event)
