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
