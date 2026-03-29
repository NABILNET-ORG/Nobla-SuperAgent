"""Slack event handlers with rate-limit queue (Phase 5-Channels).

Parses inbound Events API / Socket Mode payloads, extracts user context,
routes messages through the linking + executor pipeline, and emits
events on the bus.

Slash commands: /nobla start|link|unlink|status (space-separated)
Keyword commands: !start !link !unlink !status (fallback for consistency)

Channel policy:
  - DMs (channel_type=im): always respond
  - Channels: respond only when bot is @mentioned (<@BOT_USER_ID>)
  - app_mention events: always respond

Thread behavior:
  - If message has thread_ts, reply in-thread
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from nobla.channels.base import (
    Attachment,
    ChannelMessage,
)
from nobla.channels.slack.models import (
    CHANNEL_NAME,
    IGNORED_SUBTYPES,
    SUPPORTED_EVENT_TYPES,
    SlackUserContext,
)

logger = logging.getLogger(__name__)

# Type aliases to avoid hard import cycles.
LinkingService = Any
EventBus = Any


# -- Rate limit queue ------------------------------------------------


class RateLimitQueue:
    """Queue outbound messages with Retry-After header support.

    When Slack returns 429, call ``set_retry_after(seconds)`` to pause
    all sends until the delay elapses.

    Stores full payload dicts so that Block Kit blocks, thread_ts, and
    other fields are preserved through the queue.
    """

    def __init__(self, sender: Any) -> None:
        self._sender = sender
        self._queue: deque[dict[str, Any]] = deque()
        self._retry_after: float = 0.0

    def set_retry_after(self, seconds: float) -> None:
        """Set delay before next send (from Retry-After header)."""
        self._retry_after = time.monotonic() + seconds

    async def enqueue(self, payload: dict[str, Any]) -> None:
        """Add a message payload to the queue."""
        self._queue.append(payload)

    async def process(self) -> None:
        """Process one message from the queue, respecting rate limits."""
        if not self._queue:
            return

        now = time.monotonic()
        if now < self._retry_after:
            delay = self._retry_after - now
            await asyncio.sleep(delay)

        payload = self._queue.popleft()
        try:
            await self._sender(payload)
        except Exception:
            logger.exception(
                "Failed to send queued message to %s",
                payload.get("channel", "?"),
            )


# -- Slack handlers --------------------------------------------------


class SlackHandlers:
    """Inbound event + interaction handlers for Slack.

    Args:
        linking: UserLinkingService for resolving/creating links.
        event_bus: NoblaEventBus for emitting channel events.
        bot_token: Slack bot token (xoxb-...).
        bot_user_id: The bot's Slack user ID (U...).
        max_file_size_mb: Max attachment size to download.
    """

    def __init__(
        self,
        linking: LinkingService,
        event_bus: EventBus,
        bot_token: str = "",
        bot_user_id: str = "",
        max_file_size_mb: int = 100,
    ) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._bot_token = bot_token
        self._bot_user_id = bot_user_id
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._send_text_fn: Any = None

    def set_send_fn(self, fn: Any) -> None:
        """Register the adapter's raw send function for handler replies."""
        self._send_text_fn = fn

    # -- Event entry point -------------------------------------------

    async def handle_event(self, payload: dict[str, Any]) -> None:
        """Process a Slack Events API callback or Socket Mode event."""
        event = payload.get("event")
        if not event:
            return

        event_type = event.get("type", "")
        if event_type not in SUPPORTED_EVENT_TYPES:
            return

        # Skip ignored subtypes (bot messages, edits, etc.)
        subtype = event.get("subtype")
        if subtype and subtype in IGNORED_SUBTYPES:
            return

        user_id = event.get("user", "")
        # Ignore bot's own messages
        if user_id == self._bot_user_id:
            return

        text = event.get("text", "")
        channel_id = event.get("channel", "")
        channel_type = event.get("channel_type", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts")
        team_id = payload.get("team_id", "")

        is_dm = channel_type == "im"
        is_mention = f"<@{self._bot_user_id}>" in text
        is_app_mention = event_type == "app_mention"

        # Channel policy: respond only on mention in channels, always in DMs
        if not is_dm and not is_mention and not is_app_mention:
            return

        # Strip bot mention from text
        if is_mention:
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()

        ctx = SlackUserContext(
            user_id=user_id,
            display_name=user_id,  # Slack doesn't send name in events
            team_id=team_id,
            channel_id=channel_id,
            message_ts=ts,
            thread_ts=thread_ts,
            is_dm=is_dm,
            is_thread=thread_ts is not None,
            is_bot_mentioned=is_mention or is_app_mention,
        )

        await self._handle_message(ctx, text, event)

    # -- Message handling --------------------------------------------

    async def _handle_message(
        self, ctx: SlackUserContext, text: str, raw_event: dict[str, Any],
    ) -> None:
        """Process a single inbound message."""
        # Check for keyword commands
        stripped = text.strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_keyword_command(ctx, stripped, text)
            return

        # Resolve linked user
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_pairing_prompt(ctx, code)
            return

        # Build ChannelMessage
        reply_to = ctx.thread_ts if ctx.is_thread else None
        channel_msg = ChannelMessage(
            channel=CHANNEL_NAME,
            channel_user_id=ctx.user_id_str,
            content=text,
            nobla_user_id=linked.nobla_user_id,
            conversation_id=getattr(linked, "conversation_id", None),
            reply_to=reply_to,
            metadata={
                "channel_id": ctx.channel_id,
                "message_ts": ctx.message_ts,
                "thread_ts": ctx.thread_ts,
                "team_id": ctx.team_id,
                "is_dm": ctx.is_dm,
            },
        )

        await self._emit_event(
            "channel.message.in",
            {
                "channel": CHANNEL_NAME,
                "user_id": linked.nobla_user_id,
                "channel_user_id": ctx.user_id_str,
                "content": text,
                "has_attachments": False,
            },
            user_id=linked.nobla_user_id,
        )

    # -- Keyword commands (! prefix) ---------------------------------

    async def _dispatch_keyword_command(
        self, ctx: SlackUserContext, stripped: str, raw_text: str,
    ) -> None:
        """Route keyword commands (!start, !link, !unlink, !status)."""
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

    async def _cmd_start(self, ctx: SlackUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.channel_id_str,
                f"Welcome back! You're linked to Nobla. Send any message to chat.",
            )
            return

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        await self._send_text(
            ctx.channel_id_str,
            f"Welcome to *Nobla Agent*!\n\n"
            f"To link your account, use code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n\n"
            f"Code expires in 5 minutes.",
        )

    async def _cmd_link(self, ctx: SlackUserContext, args: str) -> None:
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            await self._send_text(
                ctx.channel_id_str,
                f"Your pairing code: `{code}`\n"
                f"Enter this in the Nobla app, or type: `!link <user_id>`",
            )
            return

        nobla_user_id = args.strip()
        try:
            await self._linking.link(
                CHANNEL_NAME, ctx.user_id_str, nobla_user_id
            )
            await self._send_text(
                ctx.channel_id_str,
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
            await self._send_text(
                ctx.channel_id_str, "Link failed. Check your user ID."
            )

    async def _cmd_unlink(self, ctx: SlackUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await self._send_text(ctx.channel_id_str, "Not currently linked.")
            return

        nobla_user_id = linked.nobla_user_id
        await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
        await self._send_text(ctx.channel_id_str, "Account unlinked.")
        await self._emit_event(
            "channel.user.unlinked",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            },
            user_id=nobla_user_id,
        )

    async def _cmd_status(self, ctx: SlackUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(
                ctx.channel_id_str,
                f"*Status:* Linked\n"
                f"*Nobla ID:* `{linked.nobla_user_id}`\n"
                f"*Channel:* Slack ({ctx.user_id_str})",
            )
        else:
            await self._send_text(
                ctx.channel_id_str,
                "*Status:* Not linked\nUse `!link` to connect your account.",
            )

    # -- Slash command entry point -----------------------------------

    async def handle_slash_command(
        self,
        command: str,
        text: str,
        user_id: str,
        channel_id: str,
    ) -> str:
        """Handle a /nobla slash command. Returns response text."""
        parts = text.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        ctx = SlackUserContext(
            user_id=user_id,
            display_name=user_id,
            team_id="",
            channel_id=channel_id,
            message_ts="",
        )

        if subcmd == "start":
            return await self._slash_start(ctx, args)
        elif subcmd == "link":
            return await self._slash_link(ctx, args)
        elif subcmd == "unlink":
            return await self._slash_unlink(ctx)
        elif subcmd == "status":
            return await self._slash_status(ctx)
        else:
            return (
                "Usage: `/nobla start|link|unlink|status`\n"
                "  `start` - Welcome + pairing\n"
                "  `link [user_id]` - Link account\n"
                "  `unlink` - Unlink account\n"
                "  `status` - Show link status"
            )

    async def _slash_start(self, ctx: SlackUserContext, args: str) -> str:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            return "Welcome back! You're already linked to Nobla."

        code = await self._linking.create_pairing_code(
            CHANNEL_NAME, ctx.user_id_str
        )
        return (
            f"Welcome to *Nobla Agent*!\n\n"
            f"Pairing code: `{code}`\n"
            f"Or type: `/nobla link <your_nobla_user_id>`\n\n"
            f"Code expires in 5 minutes."
        )

    async def _slash_link(self, ctx: SlackUserContext, args: str) -> str:
        if not args:
            code = await self._linking.create_pairing_code(
                CHANNEL_NAME, ctx.user_id_str
            )
            return (
                f"Your pairing code: `{code}`\n"
                f"Enter in the Nobla app, or: `/nobla link <user_id>`"
            )

        nobla_user_id = args.strip()
        try:
            await self._linking.link(
                CHANNEL_NAME, ctx.user_id_str, nobla_user_id
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
            return f"Linked to Nobla account `{nobla_user_id}`."
        except Exception:
            logger.exception("Slash link failed for %s", ctx.user_id_str)
            return "Link failed. Please check your user ID."

    async def _slash_unlink(self, ctx: SlackUserContext) -> str:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            return "Not currently linked."

        nobla_user_id = linked.nobla_user_id
        await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
        await self._emit_event(
            "channel.user.unlinked",
            {
                "channel": CHANNEL_NAME,
                "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            },
            user_id=nobla_user_id,
        )
        return "Account unlinked."

    async def _slash_status(self, ctx: SlackUserContext) -> str:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            return (
                f"*Status:* Linked\n"
                f"*Nobla ID:* `{linked.nobla_user_id}`\n"
                f"*Channel:* Slack ({ctx.user_id_str})"
            )
        return "*Status:* Not linked\nUse `/nobla link` to connect."

    # -- Interaction callbacks (button presses) ----------------------

    async def handle_interaction(
        self, interaction: dict[str, Any]
    ) -> None:
        """Handle a Slack block_actions interaction payload."""
        itype = interaction.get("type", "")
        if itype != "block_actions":
            return

        user_id = interaction.get("user", {}).get("id", "")
        channel_id = interaction.get("channel", {}).get("id", "")

        linked = await self._linking.resolve(CHANNEL_NAME, user_id)
        if not linked:
            return

        for action in interaction.get("actions", []):
            action_id = action.get("action_id", "")
            await self._emit_event(
                "channel.callback",
                {
                    "channel": CHANNEL_NAME,
                    "action_id": action_id,
                    "user_id": linked.nobla_user_id,
                    "channel_user_id": user_id,
                    "channel_id": channel_id,
                },
                user_id=linked.nobla_user_id,
            )

    # -- Helpers -----------------------------------------------------

    async def _send_text(self, channel: str, text: str) -> None:
        """Send a plain text message via the registered send function."""
        if self._send_text_fn:
            await self._send_text_fn(channel, text)
        else:
            logger.warning(
                "No send function registered - cannot reply to %s", channel
            )

    async def _send_pairing_prompt(
        self, ctx: SlackUserContext, code: str
    ) -> None:
        await self._send_text(
            ctx.channel_id_str,
            f"Hi! To use Nobla, link your account.\n\n"
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
