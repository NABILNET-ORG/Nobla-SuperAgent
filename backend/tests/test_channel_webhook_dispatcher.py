"""Cross-channel webhook dispatcher tests (closes SCM-S3-D3 deferral).

This module covers the BASE contract + dispatcher route plumbing.
Per-adapter dispatch_webhook implementations are tested in
test_channel_webhook_per_adapter.py to keep concerns split and each
file well under the 1000-line Boy Scout test ceiling.
"""

from __future__ import annotations

import inspect

import pytest

from nobla.channels.base import BaseChannelAdapter, ChannelResponse


class _MinimalAdapter(BaseChannelAdapter):
    """Smallest concrete BaseChannelAdapter for contract assertions."""

    @property
    def name(self) -> str:
        return "test"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, channel_user_id: str, response: ChannelResponse) -> None:
        return None

    async def send_notification(self, channel_user_id: str, text: str) -> None:
        return None

    def parse_callback(self, raw_callback):
        return ("noop", {})

    async def health_check(self) -> bool:
        return True


class TestBaseDispatchWebhookContract:
    def test_webhook_signature_headers_default_empty(self):
        a = _MinimalAdapter()
        assert a.webhook_signature_headers == ()

    def test_webhook_signature_headers_overridable_via_subclass(self):
        class _SignedAdapter(_MinimalAdapter):
            webhook_signature_headers = ("X-Test-Signature",)
        a = _SignedAdapter()
        assert a.webhook_signature_headers == ("X-Test-Signature",)

    def test_dispatch_webhook_is_async(self):
        a = _MinimalAdapter()
        assert inspect.iscoroutinefunction(a.dispatch_webhook)

    @pytest.mark.asyncio
    async def test_dispatch_webhook_default_raises_not_implemented(self):
        a = _MinimalAdapter()
        with pytest.raises(NotImplementedError, match="webhook"):
            await a.dispatch_webhook(request=None)

    @pytest.mark.asyncio
    async def test_dispatch_webhook_default_error_mentions_channel_name(self):
        a = _MinimalAdapter()
        with pytest.raises(NotImplementedError) as exc_info:
            await a.dispatch_webhook(request=None)
        assert "test" in str(exc_info.value)


# ── Dispatcher route (Cycle 7) ──────────────────────────────────────


from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.testclient import TestClient


def _stub_adapter(*, response=None, raises=None):
    """Build a minimal BaseChannelAdapter subclass with a controllable dispatch_webhook."""
    class _Stub(BaseChannelAdapter):
        @property
        def name(self) -> str:
            return "stub"
        async def start(self) -> None:
            return None
        async def stop(self) -> None:
            return None
        async def send(self, channel_user_id, response_):
            return None
        async def send_notification(self, channel_user_id, text):
            return None
        def parse_callback(self, raw_callback):
            return ("noop", {})
        async def health_check(self) -> bool:
            return True
        async def dispatch_webhook(self, request):
            if raises is not None:
                raise raises
            return response if response is not None else PlainTextResponse("OK")
    return _Stub()


@pytest.fixture
def dispatcher_app():
    from nobla.gateway.channel_webhook_dispatcher import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(dispatcher_app):
    return TestClient(dispatcher_app)


def _patch_manager(monkeypatch, adapters_by_name=None):
    from nobla.gateway import channel_webhook_dispatcher
    if adapters_by_name is None:
        monkeypatch.setattr(channel_webhook_dispatcher, "get_channel_manager", lambda: None)
        return None
    manager = MagicMock()
    manager.get = MagicMock(side_effect=lambda slug: adapters_by_name.get(slug))
    monkeypatch.setattr(channel_webhook_dispatcher, "get_channel_manager", lambda: manager)
    return manager


class TestDispatcherRoute:
    def test_no_channel_manager_returns_503(self, client, monkeypatch):
        _patch_manager(monkeypatch, None)
        resp = client.post("/webhook/anything")
        assert resp.status_code == 503

    def test_unknown_channel_returns_404(self, client, monkeypatch):
        _patch_manager(monkeypatch, {})
        resp = client.post("/webhook/nonexistent")
        assert resp.status_code == 404
        assert "nonexistent" in resp.text

    def test_post_resolves_and_returns_adapter_response(self, client, monkeypatch):
        adapter = _stub_adapter(response=PlainTextResponse("dispatched-OK"))
        _patch_manager(monkeypatch, {"stub": adapter})
        resp = client.post("/webhook/stub")
        assert resp.status_code == 200
        assert resp.text == "dispatched-OK"

    def test_get_resolves_and_returns_adapter_response(self, client, monkeypatch):
        adapter = _stub_adapter(response=PlainTextResponse("get-echo-123"))
        _patch_manager(monkeypatch, {"stub": adapter})
        resp = client.get("/webhook/stub?hub.challenge=get-echo-123")
        assert resp.status_code == 200
        assert resp.text == "get-echo-123"

    def test_adapter_not_implemented_returns_405(self, client, monkeypatch):
        adapter = _stub_adapter(
            raises=NotImplementedError("'stub' channel does not support webhook dispatch"),
        )
        _patch_manager(monkeypatch, {"stub": adapter})
        resp = client.post("/webhook/stub")
        assert resp.status_code == 405
        assert "stub" in resp.text

    def test_adapter_http_exception_propagates(self, client, monkeypatch):
        adapter = _stub_adapter(
            raises=HTTPException(status_code=401, detail="bad signature"),
        )
        _patch_manager(monkeypatch, {"stub": adapter})
        resp = client.post("/webhook/stub")
        assert resp.status_code == 401
        assert "bad signature" in resp.text

    def test_204_response_from_adapter_is_returned_verbatim(self, client, monkeypatch):
        adapter = _stub_adapter(response=Response(status_code=204))
        _patch_manager(monkeypatch, {"stub": adapter})
        resp = client.post("/webhook/stub")
        assert resp.status_code == 204

    def test_unsupported_method_returns_405_via_fastapi(self, client, monkeypatch):
        adapter = _stub_adapter()
        _patch_manager(monkeypatch, {"stub": adapter})
        # The route is registered for GET + POST only; PUT yields FastAPI's 405
        resp = client.put("/webhook/stub")
        assert resp.status_code == 405
