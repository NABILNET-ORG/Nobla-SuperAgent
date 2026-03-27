"""Discord event handlers — commands, messages, interactions (Phase 5A).

Each handler extracts a ``DiscordUserContext``, resolves the user via
``UserLinkingService``, and routes through the channel bridge to the
executor pipeline.  Unlinked users receive a pairing prompt.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nobla.channels.base import Attachment, ChannelMessage, ChannelResponse
from nobla.channels.bridge import create_channel_connection
from nobla.channels.linking import UserLinkingService
from nobla.channels.discord.media import download_attachment, extract_attachments_info
from nobla.channels.discord.models import DiscordUserContext
from nobla.events.models import NoblaEvent

if TYPE_CHECKING:
    import discord

    from nobla.events.bus import NoblaEventBus

logger = logging.getLogger(__name__)

CHANNEL_NAME = "discord"


# ── Context extraction ────────────────────────────────────


def extract_user_context(
    message: discord.Message,
    bot_user: discord.User | None = None,
) -> DiscordUserContext | None:
    """Build a DiscordUserContext from a Discord message.

    Returns None if the message author is a bot.
    """
    if message.author.bot:
        return None

    is_guild = message.guild is not None

    # Mention detection
    is_mentioned = False
    is_reply = False

    if is_guild and bot_user:
        is_mentioned = bot_user in message.mentions

        if message.reference and message.reference.resolved:
            ref = message.reference.resolved
            if hasattr(ref, "author") and ref.author == bot_user:
                is_reply = True

    return DiscordUserContext(
        channel_id=message.channel.id,
        user_id=message.author.id,
        username=message.author.name,
        display_name=message.author.display_name,
        guild_id=message.guild.id if message.guild else None,
        is_guild=is_guild,
        is_bot_mentioned=is_mentioned,
        is_reply_to_bot=is_reply,
        message_id=message.id,
    )


def should_process_guild_message(ctx: DiscordUserContext) -> bool:
    """Check if a guild message should be processed (mention-only mode)."""
    if not ctx.is_guild:
        return True  # DMs always processed
    return ctx.is_bot_mentioned or ctx.is_reply_to_bot


def strip_bot_mention(content: str, bot_user_id: int | None) -> str:
    """Remove the <@bot_id> mention from message content."""
    if bot_user_id:
        content = content.replace(f"<@{bot_user_id}>", "").strip()
        content = content.replace(f"<@!{bot_user_id}>", "").strip()
    return content


# ── Handler class ─────────────────────────────────────────


class DiscordHandlers:
    """Stateful handler collection wired to linking service and event bus."""

    def __init__(
        self,
        linking: UserLinkingService,
        event_bus: NoblaEventBus,
        command_prefix: str = "!",
        max_file_size_mb: int = 25,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._command_prefix = command_prefix
        self._max_file_size_mb = max_file_size_mb
        self._bot_user: discord.User | None = None

    def set_bot_user(self, user: discord.User) -> None:
        self._bot_user = user

    # ── Command dispatch ──────────────────────────────────

    async def handle_message(self, message: discord.Message) -> None:
        """Route incoming messages to commands or general handler."""
        ctx = extract_user_context(message, self._bot_user)
        if not ctx:
            return

        content = message.content.strip()

        # Check for prefix commands
        if content.startswith(self._command_prefix):
            cmd_body = content[len(self._command_prefix):].strip()
            parts = cmd_body.split(maxsplit=1)
            cmd = parts[0].lower() if parts else ""
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "start":
                await self._cmd_start(message, ctx)
                return
            if cmd == "link":
                await self._cmd_link(message, ctx, args)
                return
            if cmd == "unlink":
                await self._cmd_unlink(message, ctx)
                return
            if cmd == "status":
                await self._cmd_status(message, ctx)
                return

        # Regular message
        await self._handle_regular_message(message, ctx)

    # ── !start ────────────────────────────────────────────

    async def _cmd_start(
        self, message: discord.Message, ctx: DiscordUserContext
    ) -> None:
        """Handle !start — send welcome and pairing instructions."""
        user_id_str = ctx.user_id_str
        linked = await self._linking.resolve(CHANNEL_NAME, user_id_str)

        if linked:
            await message.reply(
                f"Welcome back! You're linked as `{linked.nobla_user_id}`."
            )
            return

        code = await self._linking.create_pairing_code(CHANNEL_NAME, user_id_str)
        await message.reply(
            f"Welcome to Nobla Agent!\n\n"
            f"To link your account, enter this code in the Nobla app "
            f"or use `!link <your_nobla_id>`:\n\n"
            f"**Pairing code: `{code}`**\n\n"
            f"This code expires in 5 minutes."
        )

    # ── !link ─────────────────────────────────────────────

    async def _cmd_link(
        self, message: discord.Message, ctx: DiscordUserContext, args: str
    ) -> None:
        """Handle !link <nobla_user_id> — complete account pairing."""
        nobla_user_id = args.strip()
        if not nobla_user_id:
            await message.reply("Usage: `!link <your_nobla_user_id>`")
            return

        user_id_str = ctx.user_id_str

        existing = await self._linking.resolve(CHANNEL_NAME, user_id_str)
        if existing:
            await message.reply(
                f"Already linked to `{existing.nobla_user_id}`. "
                f"Use `!unlink` first to change."
            )
            return

        code = await self._linking.create_pairing_code(CHANNEL_NAME, user_id_str)
        success = await self._linking.complete_pairing(code, nobla_user_id)

        if success:
            await message.reply(
                f"Account linked to `{nobla_user_id}`. You can now send messages!"
            )
            await self._emit_event(
                "channel.user.linked",
                {"channel": CHANNEL_NAME, "channel_user_id": user_id_str,
                 "nobla_user_id": nobla_user_id},
                user_id=nobla_user_id,
            )
        else:
            await message.reply("Linking failed. Please try again.")

    # ── !unlink ───────────────────────────────────────────

    async def _cmd_unlink(
        self, message: discord.Message, ctx: DiscordUserContext
    ) -> None:
        """Handle !unlink — remove account link."""
        user_id_str = ctx.user_id_str
        linked = await self._linking.resolve(CHANNEL_NAME, user_id_str)

        if not linked:
            await message.reply("No account linked.")
            return

        await self._linking.unlink(CHANNEL_NAME, user_id_str)
        await message.reply("Account unlinked. Use `!start` to link again.")
        await self._emit_event(
            "channel.user.unlinked",
            {"channel": CHANNEL_NAME, "channel_user_id": user_id_str,
             "nobla_user_id": linked.nobla_user_id},
            user_id=linked.nobla_user_id,
        )

    # ── !status ───────────────────────────────────────────

    async def _cmd_status(
        self, message: discord.Message, ctx: DiscordUserContext
    ) -> None:
        """Handle !status — show link status."""
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await message.reply(
                f"**Linked to:** `{linked.nobla_user_id}`\n"
                f"**Tier:** {linked.tier.name}\n"
                f"**Discord user:** {ctx.username or ctx.user_id_str}"
            )
        else:
            await message.reply("Not linked. Use `!start` to begin pairing.")

    # ── Regular messages ──────────────────────────────────

    async def _handle_regular_message(
        self, message: discord.Message, ctx: DiscordUserContext
    ) -> None:
        """Handle non-command messages."""
        if not should_process_guild_message(ctx):
            return

        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await message.reply(
                f"Please link your account first.\n"
                f"**Pairing code: `{code}`**\n"
                f"Enter this in the Nobla app, or use `!link <your_nobla_id>`"
            )
            return

        text = message.content
        if self._bot_user:
            text = strip_bot_mention(text, self._bot_user.id)

        # Download attachments
        attachments = await self._download_attachments(message)

        # Build ChannelMessage
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=linked.nobla_user_id,
            attachments=attachments,
            reply_to=str(message.reference.message_id)
            if message.reference else None,
            metadata={
                "channel_id": ctx.channel_id,
                "guild_id": ctx.guild_id,
                "message_id": ctx.message_id,
                "username": ctx.username,
                "is_guild": ctx.is_guild,
            },
        )

        conn = create_channel_connection(
            linked_user=linked,
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
        )

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

    # ── Interaction handler (button presses) ──────────────

    async def handle_interaction(
        self, interaction: discord.Interaction
    ) -> None:
        """Handle button interactions from inline action views."""
        if not interaction.data:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id:
            return

        user_id_str = str(interaction.user.id)
        linked = await self._linking.resolve(CHANNEL_NAME, user_id_str)

        if not linked:
            await interaction.response.send_message(
                "Session expired. Use `!start` to re-link.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        await self._emit_event(
            "channel.callback",
            {
                "action_id": custom_id,
                "metadata": {
                    "raw_data": custom_id,
                    "message_id": interaction.message.id if interaction.message else None,
                },
                "channel": CHANNEL_NAME,
                "channel_user_id": user_id_str,
            },
            user_id=linked.nobla_user_id,
        )

    # ── Helpers ───────────────────────────────────────────

    async def _download_attachments(
        self, message: discord.Message
    ) -> list[Attachment]:
        """Download all attachments from a Discord message."""
        discord_attachments = extract_attachments_info(message)
        result: list[Attachment] = []

        for disc_att in discord_attachments:
            attachment = await download_attachment(
                disc_att, max_size_mb=self._max_file_size_mb
            )
            if attachment:
                result.append(attachment)

        return result

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
