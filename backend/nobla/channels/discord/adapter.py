"""Discord channel adapter — persistent WebSocket gateway (Phase 5A).

Implements ``BaseChannelAdapter`` to connect Discord bots to the
Nobla executor pipeline via the channel bridge and event bus.

Discord bots maintain a persistent WebSocket connection to Discord's
gateway, unlike Telegram's polling/webhook model.
"""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Any

import discord
from discord import ButtonStyle, Intents

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.discord.formatter import format_response
from nobla.channels.discord.handlers import DiscordHandlers
from nobla.channels.discord.media import attachment_to_file
from nobla.config.settings import DiscordSettings

logger = logging.getLogger(__name__)

# Map InlineAction style strings to discord.ButtonStyle
_BUTTON_STYLE_MAP = {
    "primary": ButtonStyle.primary,
    "secondary": ButtonStyle.secondary,
    "danger": ButtonStyle.danger,
}


class _ActionView(discord.ui.View):
    """Dynamic button view built from formatted button specs."""

    def __init__(self, buttons: list, handler_callback, timeout: float = 300):
        super().__init__(timeout=timeout)
        for btn in buttons[:25]:
            style = _BUTTON_STYLE_MAP.get(btn.style, ButtonStyle.primary)
            button = discord.ui.Button(
                label=btn.label,
                custom_id=btn.custom_id,
                style=style,
            )
            button.callback = handler_callback
            self.add_item(button)


class DiscordAdapter(BaseChannelAdapter):
    """Discord bot adapter using a persistent gateway WebSocket.

    Args:
        settings: Discord configuration (token, prefix, etc.).
        handlers: Pre-built ``DiscordHandlers`` with linking + event bus wired.
    """

    def __init__(
        self,
        settings: DiscordSettings,
        handlers: DiscordHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: discord.Client | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return "discord"

    async def start(self) -> None:
        """Create the Discord client, register events, start in background."""
        if self._running:
            logger.warning("Discord adapter already running")
            return

        if not self._settings.bot_token:
            raise ValueError("Discord bot_token is required")

        intents = Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.dm_messages = True

        self._client = discord.Client(intents=intents)

        # Register event handlers
        @self._client.event
        async def on_ready():
            logger.info(
                "Discord bot ready as %s (id: %s)",
                self._client.user.name,
                self._client.user.id,
            )
            self._handlers.set_bot_user(self._client.user)

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return
            await self._handlers.handle_message(message)

        @self._client.event
        async def on_interaction(interaction: discord.Interaction):
            if interaction.type == discord.InteractionType.component:
                await self._handlers.handle_interaction(interaction)

        # Run client in background task
        self._task = asyncio.create_task(
            self._client.start(self._settings.bot_token)
        )
        self._running = True
        logger.info("Discord adapter started")

    async def stop(self) -> None:
        """Gracefully shut down the Discord client."""
        if not self._running or not self._client:
            return

        await self._client.close()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

        self._running = False
        self._client = None
        self._task = None
        logger.info("Discord adapter stopped")

    async def send(
        self, channel_user_id: str, response: ChannelResponse
    ) -> None:
        """Send a formatted response to a Discord user/channel."""
        if not self._client:
            logger.error("Cannot send — client not initialized")
            return

        channel = self._client.get_channel(int(channel_user_id))
        if not channel:
            # Try as user DM
            try:
                user = await self._client.fetch_user(int(channel_user_id))
                channel = await user.create_dm()
            except Exception:
                logger.exception(
                    "Cannot find channel or user %s", channel_user_id
                )
                return

        # Send attachments as files
        files = []
        for att in response.attachments:
            file_kwargs = attachment_to_file(att)
            if file_kwargs:
                files.append(discord.File(**file_kwargs))

        # Format and send text messages
        if response.content:
            formatted = format_response(response)
            for i, msg in enumerate(formatted):
                kwargs: dict[str, Any] = {"content": msg.content}

                # Attach files to the first message only
                if i == 0 and files:
                    kwargs["files"] = files
                    files = []  # Don't re-send

                # Attach buttons to the last message
                if msg.buttons:
                    view = _ActionView(
                        msg.buttons,
                        self._handlers.handle_interaction,
                    )
                    kwargs["view"] = view

                try:
                    await channel.send(**kwargs)
                except Exception:
                    logger.exception(
                        "Failed to send message to %s", channel_user_id
                    )
        elif files:
            # Media only, no text
            try:
                await channel.send(files=files)
            except Exception:
                logger.exception(
                    "Failed to send files to %s", channel_user_id
                )

    async def send_notification(
        self, channel_user_id: str, text: str
    ) -> None:
        """Send a plain-text notification."""
        if not self._client:
            logger.error("Cannot send notification — client not initialized")
            return

        channel = self._client.get_channel(int(channel_user_id))
        if not channel:
            try:
                user = await self._client.fetch_user(int(channel_user_id))
                channel = await user.create_dm()
            except Exception:
                logger.exception(
                    "Cannot find channel or user %s", channel_user_id
                )
                return

        try:
            await channel.send(text)
        except Exception:
            logger.exception(
                "Failed to send notification to %s", channel_user_id
            )

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a Discord interaction into (action_id, metadata)."""
        if hasattr(raw_callback, "data") and raw_callback.data:
            custom_id = raw_callback.data.get("custom_id", "")
            metadata: dict[str, Any] = {
                "raw_data": custom_id,
                "message_id": (
                    raw_callback.message.id
                    if raw_callback.message
                    else None
                ),
            }
            return custom_id, metadata
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check if the Discord client is connected and ready."""
        if not self._client:
            return False
        return self._client.is_ready()
