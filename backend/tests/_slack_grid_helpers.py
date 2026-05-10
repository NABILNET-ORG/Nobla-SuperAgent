"""Shared helpers for the Slack Enterprise Grid test modules.

Underscore-prefixed so pytest does NOT collect this file as a test module.
Imported by the four test_slack_grid_*.py files to keep each focused on
assertions rather than re-deriving payload builders + fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock


# -- Settings + linked-user fakes ------------------------------------


@dataclass
class FakeLinkedUser:
    nobla_user_id: str = "user-123"
    conversation_id: str = "conv-456"


@dataclass
class FakeSlackSettings:
    """Duck-typed mirror of SlackSettings + adapter-internal fields.

    Includes the production Pydantic SlackSettings fields plus the extra
    bot_user_id / socket_mode / download_timeout fields the adapter reads
    directly from settings (a wider Fake/real drift documented as carryover
    in the v2.1.6 Foundation Fix retrospective).
    """

    enabled: bool = True
    bot_token: str = "xoxb-test-token"
    app_token: str = "xapp-test-app-token"
    signing_secret: str = "test-signing-secret"
    bot_user_id: str = "U_BOT"
    webhook_path: str = "/webhook/slack"
    socket_mode: bool = True
    max_file_size_mb: int = 100
    download_timeout: int = 30
    enterprise_grid: bool = False
    org_token: str = ""
    team_ids: list[str] = field(default_factory=list)


# -- Event payload builder -------------------------------------------


def make_slack_event(
    text: str = "hello",
    user: str = "U123",
    channel: str = "C789",
    ts: str = "1700000000.000100",
    event_type: str = "message",
    thread_ts: str | None = None,
    channel_type: str = "channel",
    team_id: str = "T_TEST",
) -> dict[str, Any]:
    """Build a minimal Slack Events API envelope around a single event."""
    event: dict[str, Any] = {
        "type": event_type,
        "text": text,
        "user": user,
        "channel": channel,
        "channel_type": channel_type,
        "ts": ts,
    }
    if thread_ts is not None:
        event["thread_ts"] = thread_ts
    return {"team_id": team_id, "event": event}


# -- HTTP response fakes ---------------------------------------------


def ok_response(payload: dict[str, Any] | None = None):
    """MagicMock that mimics httpx.Response with ok=True + extra payload."""
    resp = MagicMock()
    resp.json = MagicMock(return_value={"ok": True, **(payload or {})})
    resp.status_code = 200
    return resp


def err_response(error_code: str = "invalid_auth"):
    """MagicMock that mimics a Slack error envelope (ok=False)."""
    resp = MagicMock()
    resp.json = MagicMock(return_value={"ok": False, "error": error_code})
    resp.status_code = 200
    return resp
