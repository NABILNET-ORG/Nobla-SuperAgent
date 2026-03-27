"""Telegram channel adapter — polling and webhook modes (Phase 5A).

Implements ``BaseChannelAdapter`` to connect Telegram bots to the
Nobla executor pipeline via the channel bridge and event bus.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.telegram.formatter import format_response
from nobla.channels.telegram.handlers import TelegramHandlers
from nobla.channels.telegram.media import send_attachment
from nobla.config.settings import TelegramSettings

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseChannelAdapter):
    """Telegram bot adapter supporting polling and webhook modes.

    Args:
        settings: Telegram configuration (token, mode, webhook URL, etc.).
        handlers: Pre-built ``TelegramHandlers`` with linking + event bus wired.
    """

    def __init__(
        self,
        settings: TelegramSettings,
        handlers: TelegramHandlers,
    ) -> None:
        self._settings = settings
        self._handlers = handlers
        self._app: Application | None = None
        self._bot: Bot | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self) -> None:
        """Build the Application, register handlers, and start."""
        if self._running:
            logger.warning("Telegram adapter already running")
            return

        if not self._settings.bot_token:
            raise ValueError("Telegram bot_token is required")

        self._app = (
            Application.builder()
            .token(self._settings.bot_token)
            .build()
        )
        self._bot = self._app.bot

        # Detect bot username for mention handling
        bot_info = await self._bot.get_me()
        self._handlers.set_bot_username(bot_info.username)

        # Register command handlers
        self._app.add_handler(CommandHandler("start", self._handlers.cmd_start))
        self._app.add_handler(CommandHandler("link", self._handlers.cmd_link))
        self._app.add_handler(CommandHandler("unlink", self._handlers.cmd_unlink))
        self._app.add_handler(CommandHandler("status", self._handlers.cmd_status))

        # Callback query handler (inline buttons)
        self._app.add_handler(CallbackQueryHandler(self._handlers.handle_callback))

        # General message handler (text + media, excludes commands)
        self._app.add_handler(
            MessageHandler(
                filters.ALL & ~filters.COMMAND,
                self._handlers.handle_message,
            )
        )

        await self._app.initialize()

        if self._settings.mode == "webhook":
            await self._start_webhook()
        else:
            await self._start_polling()

        self._running = True
        logger.info(
            "Telegram adapter started in %s mode", self._settings.mode
        )

    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        if not self._running or not self._app:
            return

        if self._settings.mode == "webhook":
            await self._app.updater.stop()
        else:
            await self._app.updater.stop()

        await self._app.stop()
        await self._app.shutdown()

        self._running = False
        self._bot = None
        logger.info("Telegram adapter stopped")

    async def send(
        self, channel_user_id: str, response: ChannelResponse
    ) -> None:
        """Send a formatted response to a Telegram user/chat."""
        if not self._bot:
            logger.error("Cannot send — bot not initialized")
            return

        chat_id = int(channel_user_id)

        # Send attachments first
        for attachment in response.attachments:
            await send_attachment(self._bot, chat_id, attachment)

        # Format and send text messages
        if response.content:
            formatted = format_response(response)
            for msg in formatted:
                kwargs: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": msg.text,
                    "parse_mode": msg.parse_mode,
                }
                if msg.reply_markup:
                    keyboard = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    text=btn["text"],
                                    callback_data=btn["callback_data"],
                                )
                                for btn in row
                            ]
                            for row in msg.reply_markup
                        ]
                    )
                    kwargs["reply_markup"] = keyboard

                try:
                    await self._bot.send_message(**kwargs)
                except Exception:
                    logger.exception(
                        "Failed to send message to %s", channel_user_id
                    )
                    # Retry without parse_mode as fallback
                    try:
                        kwargs.pop("parse_mode", None)
                        kwargs["text"] = response.content[
                            : len(msg.text)
                        ]  # Use unescaped text
                        await self._bot.send_message(**kwargs)
                    except Exception:
                        logger.exception(
                            "Fallback send also failed for %s", channel_user_id
                        )

    async def send_notification(
        self, channel_user_id: str, text: str
    ) -> None:
        """Send a plain-text notification (no formatting)."""
        if not self._bot:
            logger.error("Cannot send notification — bot not initialized")
            return

        try:
            await self._bot.send_message(
                chat_id=int(channel_user_id), text=text
            )
        except Exception:
            logger.exception(
                "Failed to send notification to %s", channel_user_id
            )

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        """Parse a Telegram callback query into (action_id, metadata)."""
        if hasattr(raw_callback, "data"):
            data = raw_callback.data or ""
            metadata: dict[str, Any] = {
                "raw_data": data,
                "message_id": (
                    raw_callback.message.message_id
                    if raw_callback.message
                    else None
                ),
            }
            return data, metadata
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        """Check if the bot is connected and responsive."""
        if not self._bot:
            return False
        try:
            me = await self._bot.get_me()
            return me is not None
        except Exception:
            logger.exception("Telegram health check failed")
            return False

    # ── Private helpers ───────────────────────────────────

    async def _start_polling(self) -> None:
        """Start long-polling for updates."""
        await self._app.updater.start_polling(
            allowed_updates=self._settings.allowed_updates,
            drop_pending_updates=True,
        )
        await self._app.start()

    async def _start_webhook(self) -> None:
        """Start webhook listener."""
        await self._app.updater.start_webhook(
            listen="0.0.0.0",
            port=8443,
            url_path=self._settings.webhook_path,
            webhook_url=f"{self._settings.webhook_url}{self._settings.webhook_path}",
            secret_token=self._settings.webhook_secret,
            allowed_updates=self._settings.allowed_updates,
            drop_pending_updates=True,
        )
        await self._app.start()
