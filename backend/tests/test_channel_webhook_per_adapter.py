"""Per-adapter dispatch_webhook tests for Mission B (cross-channel webhook dispatcher).

Each TestX class covers one channel's webhook dispatch contract:
  - WhatsApp / Messenger: Meta-style (GET URL verification + POST HMAC body).
  - Slack: signing-secret HMAC + URL verification in POST body + Events API.
  - Teams / Telegram: per-channel quirks documented in their TestX class.

Per the v2.1.6 Boy Scout test ceiling (1,000 lines), this file groups
per-adapter assertions; the dispatcher route plumbing lives in
test_channel_webhook_dispatcher.py.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# ── WhatsApp (Meta-style) ───────────────────────────────────────────


@dataclass
class _FakeWhatsAppSettings:
    """Duck-typed mirror of WhatsAppSettings for dispatch_webhook tests."""

    access_token: str = "tok"
    phone_number_id: str = "phone-123"
    app_secret: str = "wa-secret"
    verify_token: str = "VT-WA"
    api_version: str = "v21.0"
    download_timeout: int = 30


class TestWhatsAppDispatchWebhook:
    @pytest.fixture
    def adapter(self):
        from nobla.channels.whatsapp.adapter import WhatsAppAdapter
        h = MagicMock()
        h.handle_webhook = AsyncMock()
        h.set_send_fn = MagicMock()
        h.set_bot_phone = MagicMock()
        return WhatsAppAdapter(settings=_FakeWhatsAppSettings(), handlers=h)

    def test_webhook_signature_headers_set(self, adapter):
        assert adapter.webhook_signature_headers == ("X-Hub-Signature-256",)

    @pytest.mark.asyncio
    async def test_get_returns_challenge_echo(self, adapter):
        req = MagicMock(method="GET")
        req.query_params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "VT-WA",
            "hub.challenge": "abc123",
        }
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        assert resp.body == b"abc123"

    @pytest.mark.asyncio
    async def test_get_invalid_token_returns_403(self, adapter):
        req = MagicMock(method="GET")
        req.query_params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "WRONG",
            "hub.challenge": "abc",
        }
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_wrong_mode_returns_403(self, adapter):
        req = MagicMock(method="GET")
        req.query_params = {
            "hub.mode": "unsubscribe",
            "hub.verify_token": "VT-WA",
            "hub.challenge": "abc",
        }
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_post_valid_signature_returns_200(self, adapter):
        body = b'{"entry":[{"messaging":[]}]}'
        sig = "sha256=" + hmac.new(b"wa-secret", body, hashlib.sha256).hexdigest()
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Hub-Signature-256": sig}
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        adapter._handlers.handle_webhook.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_invalid_signature_returns_401(self, adapter):
        body = b'{"entry":[]}'
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Hub-Signature-256": "sha256=BADSIG"}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401
        adapter._handlers.handle_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_post_missing_signature_header_returns_401(self, adapter):
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=b'{}')
        req.headers = {}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_post_invalid_json_returns_401(self, adapter):
        body = b'NOT JSON'
        sig = "sha256=" + hmac.new(b"wa-secret", body, hashlib.sha256).hexdigest()
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Hub-Signature-256": sig}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_other_method_returns_405(self, adapter):
        req = MagicMock(method="DELETE")
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 405


# ── Messenger (Meta-style — identical contract to WhatsApp) ─────────


@dataclass
class _FakeMessengerSettings:
    page_access_token: str = "page-tok"
    page_id: str = "page-123"
    app_secret: str = "msg-secret"
    verify_token: str = "VT-MSG"
    api_version: str = "v21.0"
    download_timeout: int = 30
    max_file_size_mb: int = 25


class TestMessengerDispatchWebhook:
    @pytest.fixture
    def adapter(self):
        from nobla.channels.messenger.adapter import MessengerAdapter
        h = MagicMock()
        h.handle_webhook = AsyncMock()
        h.set_send_fn = MagicMock()
        return MessengerAdapter(settings=_FakeMessengerSettings(), handlers=h)

    def test_webhook_signature_headers_set(self, adapter):
        assert adapter.webhook_signature_headers == ("X-Hub-Signature-256",)

    @pytest.mark.asyncio
    async def test_get_returns_challenge_echo(self, adapter):
        req = MagicMock(method="GET")
        req.query_params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "VT-MSG",
            "hub.challenge": "msg-challenge-99",
        }
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        assert resp.body == b"msg-challenge-99"

    @pytest.mark.asyncio
    async def test_get_invalid_token_returns_403(self, adapter):
        req = MagicMock(method="GET")
        req.query_params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "WRONG",
            "hub.challenge": "abc",
        }
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_post_valid_signature_returns_200(self, adapter):
        body = b'{"object":"page","entry":[{"messaging":[]}]}'
        sig = "sha256=" + hmac.new(b"msg-secret", body, hashlib.sha256).hexdigest()
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Hub-Signature-256": sig}
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        adapter._handlers.handle_webhook.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_invalid_signature_returns_401(self, adapter):
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=b'{}')
        req.headers = {"X-Hub-Signature-256": "sha256=BADSIG"}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401
        adapter._handlers.handle_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_post_missing_signature_returns_401(self, adapter):
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=b'{}')
        req.headers = {}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_post_invalid_json_returns_401(self, adapter):
        body = b'NOT JSON'
        sig = "sha256=" + hmac.new(b"msg-secret", body, hashlib.sha256).hexdigest()
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Hub-Signature-256": sig}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_other_method_returns_405(self, adapter):
        req = MagicMock(method="PUT")
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 405


# ── Slack (POST-only: signing-secret HMAC + URL verification in body) ─


@dataclass
class _FakeSlackSettings:
    bot_token: str = "xoxb-test"
    app_token: str = ""
    signing_secret: str = "slack-secret"
    bot_user_id: str = "U_BOT"
    socket_mode: bool = False
    download_timeout: int = 30
    enterprise_grid: bool = False
    org_token: str = ""
    team_ids: list[str] = field(default_factory=list)


def _slack_signature(secret: bytes, timestamp: str, body: bytes) -> str:
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    return "v0=" + hmac.new(secret, sig_basestring, hashlib.sha256).hexdigest()


class TestSlackDispatchWebhook:
    @pytest.fixture
    def adapter(self):
        from nobla.channels.slack.adapter import SlackAdapter
        from nobla.channels.slack.handlers import SlackHandlers
        h = SlackHandlers(
            linking=AsyncMock(), event_bus=AsyncMock(),
            bot_token="xoxb-test", bot_user_id="U_BOT",
        )
        h.set_send_fn(AsyncMock())
        h.handle_event = AsyncMock()
        return SlackAdapter(settings=_FakeSlackSettings(), handlers=h)

    def test_webhook_signature_headers_set(self, adapter):
        assert adapter.webhook_signature_headers == (
            "X-Slack-Signature", "X-Slack-Request-Timestamp",
        )

    @pytest.mark.asyncio
    async def test_get_returns_405(self, adapter):
        req = MagicMock(method="GET")
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 405

    @pytest.mark.asyncio
    async def test_post_url_verification_returns_challenge(self, adapter):
        import time
        body = b'{"type":"url_verification","challenge":"slack-challenge-XYZ"}'
        ts = str(int(time.time()))
        sig = _slack_signature(b"slack-secret", ts, body)
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts}
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        assert resp.body == b"slack-challenge-XYZ"

    @pytest.mark.asyncio
    async def test_post_event_callback_returns_200(self, adapter):
        import time
        body = b'{"type":"event_callback","event":{"type":"message","text":"hi"}}'
        ts = str(int(time.time()))
        sig = _slack_signature(b"slack-secret", ts, body)
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts}
        resp = await adapter.dispatch_webhook(req)
        assert resp.status_code == 200
        adapter._handlers.handle_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_invalid_signature_returns_401(self, adapter):
        import time
        body = b'{"type":"event_callback","event":{}}'
        ts = str(int(time.time()))
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": "v0=BADSIG", "X-Slack-Request-Timestamp": ts}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401
        adapter._handlers.handle_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_post_missing_timestamp_returns_401(self, adapter):
        body = b'{"type":"event_callback"}'
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": "v0=anything"}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_post_old_timestamp_returns_401(self, adapter):
        body = b'{"type":"event_callback"}'
        ts = "1000000000"  # ~year 2001, far past 300s replay window
        sig = _slack_signature(b"slack-secret", ts, body)
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_post_invalid_json_returns_400(self, adapter):
        import time
        body = b'NOT JSON'
        ts = str(int(time.time()))
        sig = _slack_signature(b"slack-secret", ts, body)
        req = MagicMock(method="POST")
        req.body = AsyncMock(return_value=body)
        req.headers = {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts}
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_other_method_returns_405(self, adapter):
        req = MagicMock(method="PATCH")
        with pytest.raises(HTTPException) as exc:
            await adapter.dispatch_webhook(req)
        assert exc.value.status_code == 405
