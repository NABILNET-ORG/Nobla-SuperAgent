"""Microsoft Teams event handlers (Phase 5-Channels).

Parses inbound Bot Framework Activity objects, extracts user context,
routes messages through the linking + executor pipeline, and emits
events on the bus.

Keyword commands: !start !link !unlink !status
Channel policy:
  - DMs (personal): always respond
  - Channels: respond only when bot is @mentioned
"""

from __future__ import annotations

import logging
import re
from typing import Any

from nobla.channels.base import ChannelMessage
from nobla.channels.teams.models import (
    CHANNEL_NAME,
    IGNORED_ACTIVITY_TYPES,
    SUPPORTED_ACTIVITY_TYPES,
    TeamsUserContext,
)

logger = logging.getLogger(__name__)

LinkingService = Any
EventBus = Any

_AT_TAG_RE = re.compile(r"<at>.*?</at>\s*", re.IGNORECASE)


class TeamsHandlers:
    """Inbound activity handlers for Microsoft Teams."""

    def __init__(self, linking: LinkingService, event_bus: EventBus,
                 app_id: str, max_file_size_mb: int = 100) -> None:
        self._linking = linking
        self._event_bus = event_bus
        self._app_id = app_id
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._send_fn: Any = None
        self._conversation_refs: dict[str, dict[str, str]] = {}

    def set_send_fn(self, fn: Any) -> None:
        self._send_fn = fn

    def get_conversation_ref(self, channel_user_id: str) -> dict[str, str] | None:
        return self._conversation_refs.get(channel_user_id)

    async def handle_activity(self, activity: dict[str, Any]) -> None:
        activity_type = activity.get("type", "")
        if activity_type in IGNORED_ACTIVITY_TYPES:
            return
        if activity_type not in SUPPORTED_ACTIVITY_TYPES:
            return
        if activity_type == "message":
            await self._handle_message(activity)
        elif activity_type == "invoke":
            await self._handle_invoke(activity)
        elif activity_type == "conversationUpdate":
            await self._handle_conversation_update(activity)
        elif activity_type == "messageReaction":
            await self._handle_reaction(activity)

    async def _handle_message(self, activity: dict[str, Any]) -> None:
        ctx = self._extract_user_context(activity)
        text = activity.get("text", "")
        self._store_conversation_ref(ctx)
        if not ctx.is_dm and not ctx.is_bot_mentioned:
            return
        text = _AT_TAG_RE.sub("", text).strip()
        stripped = text.strip().lower()
        if stripped.startswith("!"):
            await self._dispatch_keyword_command(ctx, stripped, text)
            return
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            code = await self._linking.create_pairing_code(CHANNEL_NAME, ctx.user_id_str)
            await self._send_pairing_prompt(ctx, code)
            return
        await self._emit_event("channel.message.in", {
            "channel": CHANNEL_NAME, "user_id": linked.nobla_user_id,
            "channel_user_id": ctx.user_id_str, "content": text,
            "has_attachments": bool(activity.get("attachments")),
        }, user_id=linked.nobla_user_id)

    async def _dispatch_keyword_command(self, ctx: TeamsUserContext, stripped: str, raw_text: str) -> None:
        parts = stripped.split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        handlers = {"!start": self._cmd_start, "!link": self._cmd_link,
                     "!unlink": self._cmd_unlink, "!status": self._cmd_status}
        handler = handlers.get(cmd)
        if handler:
            await handler(ctx, args)

    async def _cmd_start(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(ctx.channel_id_str,
                "Welcome back! You're linked to Nobla. Send any message to chat.")
            return
        code = await self._linking.create_pairing_code(CHANNEL_NAME, ctx.user_id_str)
        await self._send_text(ctx.channel_id_str,
            f"Welcome to **Nobla Agent**!\n\nTo link your account, use code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\n\nCode expires in 5 minutes.")

    async def _cmd_link(self, ctx: TeamsUserContext, args: str) -> None:
        if not args:
            code = await self._linking.create_pairing_code(CHANNEL_NAME, ctx.user_id_str)
            await self._send_text(ctx.channel_id_str,
                f"Your pairing code: `{code}`\nEnter this in the Nobla app, or type: `!link <user_id>`")
            return
        nobla_user_id = args.strip()
        try:
            await self._linking.link(CHANNEL_NAME, ctx.user_id_str, nobla_user_id)
            await self._send_text(ctx.channel_id_str, f"Linked to Nobla account `{nobla_user_id}`.")
            await self._emit_event("channel.user.linked", {
                "channel": CHANNEL_NAME, "channel_user_id": ctx.user_id_str,
                "nobla_user_id": nobla_user_id,
            }, user_id=nobla_user_id)
        except Exception:
            logger.exception("Link failed for %s", ctx.user_id_str)
            await self._send_text(ctx.channel_id_str, "Link failed. Check your user ID.")

    async def _cmd_unlink(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if not linked:
            await self._send_text(ctx.channel_id_str, "Not currently linked.")
            return
        nobla_user_id = linked.nobla_user_id
        await self._linking.unlink(CHANNEL_NAME, ctx.user_id_str)
        await self._send_text(ctx.channel_id_str, "Account unlinked.")
        await self._emit_event("channel.user.unlinked", {
            "channel": CHANNEL_NAME, "channel_user_id": ctx.user_id_str,
            "nobla_user_id": nobla_user_id,
        }, user_id=nobla_user_id)

    async def _cmd_status(self, ctx: TeamsUserContext, args: str) -> None:
        linked = await self._linking.resolve(CHANNEL_NAME, ctx.user_id_str)
        if linked:
            await self._send_text(ctx.channel_id_str,
                f"**Status:** Linked\n**Nobla ID:** `{linked.nobla_user_id}`\n"
                f"**Channel:** Teams ({ctx.user_id_str})")
        else:
            await self._send_text(ctx.channel_id_str,
                "**Status:** Not linked\nUse `!link` to connect your account.")

    async def _handle_invoke(self, activity: dict[str, Any]) -> None:
        user_id = activity.get("from", {}).get("id", "")
        linked = await self._linking.resolve(CHANNEL_NAME, user_id)
        if not linked:
            return
        value = activity.get("value", {})
        action_data = value
        if "action" in value and isinstance(value["action"], dict):
            action_data = value["action"].get("data", value)
        action_id = action_data.get("action_id", "")
        if action_id:
            await self._emit_event("channel.callback", {
                "channel": CHANNEL_NAME, "action_id": action_id,
                "user_id": linked.nobla_user_id, "channel_user_id": user_id,
            }, user_id=linked.nobla_user_id)

    async def _handle_conversation_update(self, activity: dict[str, Any]) -> None:
        members_added = activity.get("membersAdded", [])
        for member in members_added:
            if member.get("id") == self._app_id:
                conv_id = activity.get("conversation", {}).get("id", "")
                await self._send_text(conv_id,
                    "Hi! I'm **Nobla Agent**. Type `!start` to get started.")
                return

    async def _handle_reaction(self, activity: dict[str, Any]) -> None:
        user_id = activity.get("from", {}).get("id", "")
        linked = await self._linking.resolve(CHANNEL_NAME, user_id)
        if not linked:
            return
        for reaction in activity.get("reactionsAdded", []):
            await self._emit_event("channel.reaction", {
                "channel": CHANNEL_NAME, "user_id": linked.nobla_user_id,
                "reaction": reaction.get("type", ""),
            }, user_id=linked.nobla_user_id)

    def _extract_user_context(self, activity: dict[str, Any]) -> TeamsUserContext:
        from_obj = activity.get("from", {})
        conv = activity.get("conversation", {})
        channel_data = activity.get("channelData", {})
        tenant_id = channel_data.get("tenant", {}).get("id", "")
        channel_id = channel_data.get("channel", {}).get("id") if "channel" in channel_data else None
        is_dm = conv.get("conversationType") == "personal"
        is_mentioned = self._check_mention(activity.get("entities", []))
        return TeamsUserContext(
            user_id=from_obj.get("id", ""), display_name=from_obj.get("name", ""),
            tenant_id=tenant_id, conversation_id=conv.get("id", ""),
            service_url=activity.get("serviceUrl", ""), message_id=activity.get("id", ""),
            channel_id=channel_id, is_dm=is_dm, is_bot_mentioned=is_mentioned,
        )

    def _check_mention(self, entities: list[dict[str, Any]]) -> bool:
        for entity in entities:
            if entity.get("type") == "mention":
                if entity.get("mentioned", {}).get("id") == self._app_id:
                    return True
        return False

    def _store_conversation_ref(self, ctx: TeamsUserContext) -> None:
        self._conversation_refs[ctx.user_id] = {
            "service_url": ctx.service_url, "conversation_id": ctx.conversation_id,
            "tenant_id": ctx.tenant_id, "channel_id": ctx.channel_id or "",
        }

    async def _send_text(self, conversation_id: str, text: str) -> None:
        if self._send_fn:
            await self._send_fn(conversation_id, text)
        else:
            logger.warning("No send function registered - cannot reply to %s", conversation_id)

    async def _send_pairing_prompt(self, ctx: TeamsUserContext, code: str) -> None:
        await self._send_text(ctx.channel_id_str,
            f"Hi! To use Nobla, link your account.\n\nPairing code: `{code}`\n"
            f"Or type: `!link <your_nobla_user_id>`\nCode expires in 5 minutes.")

    async def _emit_event(self, event_type: str, payload: dict[str, Any],
                           user_id: str | None = None) -> None:
        if not self._event_bus:
            return
        try:
            from nobla.events.models import NoblaEvent
            event = NoblaEvent(event_type=event_type, source=CHANNEL_NAME,
                               payload=payload, user_id=user_id)
            await self._event_bus.publish(event)
        except Exception:
            logger.exception("Failed to emit %s event", event_type)
