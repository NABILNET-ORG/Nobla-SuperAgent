"""Tests for Phase 6 webhook models, verification, registry, manager, and handlers."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from nobla.automation.webhooks.models import (
    DeadLetterEvent,
    SignatureScheme,
    Webhook,
    WebhookDirection,
    WebhookEvent,
    WebhookEventStatus,
    WebhookHealth,
    WebhookHealthStatus,
    WebhookStatus,
)
from nobla.automation.webhooks.verification import (
    HmacSha1Verifier,
    HmacSha256Verifier,
    NoneVerifier,
    SignatureVerifier,
    VerifierRegistry,
)
from nobla.config.settings import Settings, WebhookSettings, WorkflowSettings


# ---------------------------------------------------------------------------
# Webhook model tests
# ---------------------------------------------------------------------------


class TestWebhookModel:
    """Webhook registration dataclass."""

    def test_defaults(self):
        wh = Webhook()
        assert wh.user_id == ""
        assert wh.direction == WebhookDirection.INBOUND
        assert wh.status == WebhookStatus.ACTIVE
        assert wh.signature_scheme == SignatureScheme.HMAC_SHA256
        assert isinstance(wh.webhook_id, str)
        assert len(wh.webhook_id) == 36  # UUID4 format

    def test_custom_values(self):
        wh = Webhook(
            user_id="u1",
            name="GitHub Push",
            direction=WebhookDirection.OUTBOUND,
            url="https://example.com/hook",
            event_type_prefix="github.push",
            secret="s3cret",
            signature_scheme=SignatureScheme.HMAC_SHA1,
            status=WebhookStatus.PAUSED,
        )
        assert wh.user_id == "u1"
        assert wh.name == "GitHub Push"
        assert wh.direction == WebhookDirection.OUTBOUND
        assert wh.url == "https://example.com/hook"
        assert wh.event_type_prefix == "github.push"
        assert wh.secret == "s3cret"
        assert wh.signature_scheme == SignatureScheme.HMAC_SHA1
        assert wh.status == WebhookStatus.PAUSED

    def test_unique_ids(self):
        ids = {Webhook().webhook_id for _ in range(100)}
        assert len(ids) == 100

    def test_timestamps_are_utc(self):
        wh = Webhook()
        assert wh.created_at.tzinfo == timezone.utc
        assert wh.updated_at.tzinfo == timezone.utc


class TestWebhookEventModel:
    """Webhook event log dataclass."""

    def test_defaults(self):
        ev = WebhookEvent()
        assert ev.webhook_id == ""
        assert ev.status == WebhookEventStatus.RECEIVED
        assert ev.retry_count == 0
        assert ev.signature_valid is False
        assert ev.error is None
        assert ev.processed_at is None

    def test_custom_values(self):
        ev = WebhookEvent(
            webhook_id="wh-1",
            headers={"x-signature": "abc"},
            payload={"action": "push"},
            signature_valid=True,
            status=WebhookEventStatus.PROCESSED,
            retry_count=2,
        )
        assert ev.webhook_id == "wh-1"
        assert ev.headers == {"x-signature": "abc"}
        assert ev.payload == {"action": "push"}
        assert ev.signature_valid is True
        assert ev.status == WebhookEventStatus.PROCESSED
        assert ev.retry_count == 2

    def test_unique_event_ids(self):
        ids = {WebhookEvent().event_id for _ in range(100)}
        assert len(ids) == 100


class TestDeadLetterEventModel:
    """Dead letter event dataclass."""

    def test_defaults(self):
        dl = DeadLetterEvent()
        assert dl.webhook_id == ""
        assert dl.error == ""
        assert dl.retry_count == 0
        assert dl.user_notified is False

    def test_custom_values(self):
        dl = DeadLetterEvent(
            webhook_id="wh-1",
            event_id="ev-1",
            payload={"data": "lost"},
            error="Connection refused",
            retry_count=3,
            user_notified=True,
        )
        assert dl.webhook_id == "wh-1"
        assert dl.event_id == "ev-1"
        assert dl.payload == {"data": "lost"}
        assert dl.error == "Connection refused"
        assert dl.retry_count == 3
        assert dl.user_notified is True


class TestWebhookHealth:
    """Health summary computation."""

    def test_healthy_no_events(self):
        h = WebhookHealth(webhook_id="wh-1")
        assert h.compute_status() == WebhookHealthStatus.HEALTHY

    def test_healthy_low_failure_rate(self):
        h = WebhookHealth(
            webhook_id="wh-1",
            event_count=100,
            failure_count=5,
            failure_rate=0.05,
        )
        assert h.compute_status() == WebhookHealthStatus.HEALTHY

    def test_degraded(self):
        h = WebhookHealth(
            webhook_id="wh-1",
            event_count=100,
            failure_count=15,
            failure_rate=0.15,
        )
        assert h.compute_status() == WebhookHealthStatus.DEGRADED

    def test_failing(self):
        h = WebhookHealth(
            webhook_id="wh-1",
            event_count=100,
            failure_count=60,
            failure_rate=0.60,
        )
        assert h.compute_status() == WebhookHealthStatus.FAILING

    def test_boundary_degraded_at_ten_percent(self):
        h = WebhookHealth(
            webhook_id="wh-1", event_count=100, failure_rate=0.10
        )
        assert h.compute_status() == WebhookHealthStatus.DEGRADED

    def test_boundary_failing_at_fifty_percent(self):
        h = WebhookHealth(
            webhook_id="wh-1", event_count=100, failure_rate=0.50
        )
        assert h.compute_status() == WebhookHealthStatus.FAILING


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Enum values and string representation."""

    def test_direction_values(self):
        assert WebhookDirection.INBOUND.value == "inbound"
        assert WebhookDirection.OUTBOUND.value == "outbound"

    def test_status_values(self):
        assert WebhookStatus.ACTIVE.value == "active"
        assert WebhookStatus.PAUSED.value == "paused"
        assert WebhookStatus.DISABLED.value == "disabled"

    def test_event_status_values(self):
        assert WebhookEventStatus.RECEIVED.value == "received"
        assert WebhookEventStatus.PROCESSED.value == "processed"
        assert WebhookEventStatus.FAILED.value == "failed"
        assert WebhookEventStatus.RETRYING.value == "retrying"

    def test_health_status_values(self):
        assert WebhookHealthStatus.HEALTHY.value == "healthy"
        assert WebhookHealthStatus.DEGRADED.value == "degraded"
        assert WebhookHealthStatus.FAILING.value == "failing"

    def test_signature_scheme_values(self):
        assert SignatureScheme.HMAC_SHA256.value == "hmac-sha256"
        assert SignatureScheme.HMAC_SHA1.value == "hmac-sha1"
        assert SignatureScheme.NONE.value == "none"


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------


class TestHmacSha256Verifier:
    """HMAC-SHA256 verification and signing."""

    def setup_method(self):
        self.verifier = HmacSha256Verifier()
        self.secret = "test-secret-key"
        self.payload = b'{"event": "push", "ref": "refs/heads/main"}'

    def test_sign_produces_hex_digest(self):
        sig = self.verifier.sign(self.payload, self.secret)
        assert len(sig) == 64  # SHA256 hex digest = 64 chars
        assert all(c in "0123456789abcdef" for c in sig)

    def test_verify_valid_signature(self):
        sig = self.verifier.sign(self.payload, self.secret)
        assert self.verifier.verify(self.payload, sig, self.secret) is True

    def test_verify_with_sha256_prefix(self):
        sig = self.verifier.sign(self.payload, self.secret)
        prefixed = f"sha256={sig}"
        assert self.verifier.verify(self.payload, prefixed, self.secret) is True

    def test_verify_wrong_signature(self):
        assert (
            self.verifier.verify(self.payload, "bad" * 20, self.secret)
            is False
        )

    def test_verify_wrong_secret(self):
        sig = self.verifier.sign(self.payload, self.secret)
        assert self.verifier.verify(self.payload, sig, "wrong-secret") is False

    def test_verify_modified_payload(self):
        sig = self.verifier.sign(self.payload, self.secret)
        modified = b'{"event": "push", "ref": "refs/heads/dev"}'
        assert self.verifier.verify(modified, sig, self.secret) is False

    def test_matches_stdlib_hmac(self):
        expected = hmac.new(
            self.secret.encode("utf-8"), self.payload, hashlib.sha256
        ).hexdigest()
        assert self.verifier.sign(self.payload, self.secret) == expected

    def test_empty_payload(self):
        sig = self.verifier.sign(b"", self.secret)
        assert self.verifier.verify(b"", sig, self.secret) is True


class TestHmacSha1Verifier:
    """HMAC-SHA1 verification and signing."""

    def setup_method(self):
        self.verifier = HmacSha1Verifier()
        self.secret = "legacy-secret"
        self.payload = b'{"action": "opened"}'

    def test_sign_produces_hex_digest(self):
        sig = self.verifier.sign(self.payload, self.secret)
        assert len(sig) == 40  # SHA1 hex digest = 40 chars

    def test_verify_valid_signature(self):
        sig = self.verifier.sign(self.payload, self.secret)
        assert self.verifier.verify(self.payload, sig, self.secret) is True

    def test_verify_with_sha1_prefix(self):
        sig = self.verifier.sign(self.payload, self.secret)
        prefixed = f"sha1={sig}"
        assert self.verifier.verify(self.payload, prefixed, self.secret) is True

    def test_verify_wrong_signature(self):
        assert (
            self.verifier.verify(self.payload, "bad" * 10, self.secret)
            is False
        )

    def test_matches_stdlib_hmac(self):
        expected = hmac.new(
            self.secret.encode("utf-8"), self.payload, hashlib.sha1
        ).hexdigest()
        assert self.verifier.sign(self.payload, self.secret) == expected


class TestNoneVerifier:
    """No-op verifier for unsigned webhooks."""

    def setup_method(self):
        self.verifier = NoneVerifier()

    def test_verify_always_true(self):
        assert self.verifier.verify(b"anything", "anything", "anything") is True

    def test_verify_empty_inputs(self):
        assert self.verifier.verify(b"", "", "") is True

    def test_sign_returns_empty(self):
        assert self.verifier.sign(b"payload", "secret") == ""


# ---------------------------------------------------------------------------
# Verifier registry tests
# ---------------------------------------------------------------------------


class TestVerifierRegistry:
    """VerifierRegistry — scheme mapping and extensibility."""

    def setup_method(self):
        self.registry = VerifierRegistry()

    def test_builtin_schemes_registered(self):
        schemes = self.registry.list_schemes()
        assert "hmac-sha256" in schemes
        assert "hmac-sha1" in schemes
        assert "none" in schemes

    def test_get_hmac_sha256(self):
        v = self.registry.get("hmac-sha256")
        assert isinstance(v, HmacSha256Verifier)

    def test_get_hmac_sha1(self):
        v = self.registry.get("hmac-sha1")
        assert isinstance(v, HmacSha1Verifier)

    def test_get_none(self):
        v = self.registry.get("none")
        assert isinstance(v, NoneVerifier)

    def test_get_unknown_scheme_raises(self):
        with pytest.raises(KeyError, match="No verifier registered"):
            self.registry.get("ed25519")

    def test_register_custom_verifier(self):
        class Ed25519Verifier(SignatureVerifier):
            def verify(self, payload, signature, secret):
                return True

            def sign(self, payload, secret):
                return "ed25519-sig"

        self.registry.register("ed25519", Ed25519Verifier())
        v = self.registry.get("ed25519")
        assert isinstance(v, Ed25519Verifier)
        assert v.sign(b"x", "s") == "ed25519-sig"

    def test_register_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Expected SignatureVerifier"):
            self.registry.register("bad", "not a verifier")  # type: ignore

    def test_has_scheme(self):
        assert self.registry.has_scheme("hmac-sha256") is True
        assert self.registry.has_scheme("nonexistent") is False

    def test_register_overwrites(self):
        original = self.registry.get("hmac-sha256")
        new = HmacSha256Verifier()
        self.registry.register("hmac-sha256", new)
        assert self.registry.get("hmac-sha256") is new
        assert self.registry.get("hmac-sha256") is not original

    def test_list_schemes_sorted(self):
        schemes = self.registry.list_schemes()
        assert schemes == sorted(schemes)

    def test_end_to_end_sign_and_verify(self):
        """Full round-trip: sign with registry verifier, verify with same."""
        verifier = self.registry.get("hmac-sha256")
        payload = b'{"repo": "nobla-agent", "action": "push"}'
        secret = "webhook-secret-123"
        sig = verifier.sign(payload, secret)
        assert verifier.verify(payload, sig, secret) is True
        assert verifier.verify(payload, sig, "wrong") is False


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


class TestWebhookSettings:
    """WebhookSettings defaults and integration with Settings."""

    def test_defaults(self):
        s = WebhookSettings()
        assert s.enabled is True
        assert s.max_webhooks_per_user == 50
        assert s.default_signature_scheme == "hmac-sha256"
        assert s.max_retries == 3
        assert s.dead_letter_retention_days == 30
        assert s.max_payload_bytes == 1_048_576

    def test_custom_values(self):
        s = WebhookSettings(
            enabled=False,
            max_webhooks_per_user=10,
            max_retries=5,
        )
        assert s.enabled is False
        assert s.max_webhooks_per_user == 10
        assert s.max_retries == 5

    def test_in_global_settings(self):
        settings = Settings()
        assert hasattr(settings, "webhooks")
        assert isinstance(settings.webhooks, WebhookSettings)
        assert settings.webhooks.enabled is True


class TestWorkflowSettings:
    """WorkflowSettings defaults and integration with Settings."""

    def test_defaults(self):
        s = WorkflowSettings()
        assert s.enabled is True
        assert s.max_workflows_per_user == 100
        assert s.max_steps_per_workflow == 50
        assert s.max_triggers_per_workflow == 10
        assert s.max_concurrent_executions == 5
        assert s.deduplication_window_seconds == 5.0

    def test_in_global_settings(self):
        settings = Settings()
        assert hasattr(settings, "workflows")
        assert isinstance(settings.workflows, WorkflowSettings)
        assert settings.workflows.enabled is True


# ---------------------------------------------------------------------------
# WebhookManager tests
# ---------------------------------------------------------------------------


class _FakeEventBus:
    """Minimal event bus stub for manager tests."""

    def __init__(self):
        self.emitted: list = []

    async def emit(self, event):
        self.emitted.append(event)


class TestWebhookManagerCRUD:
    """WebhookManager registration, listing, deletion."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus, max_webhooks_per_user=3)

    def _make_webhook(self, **kwargs) -> Webhook:
        defaults = dict(
            user_id="u1",
            name="test-hook",
            event_type_prefix="test.event",
            secret="secret-key-12345678",
        )
        defaults.update(kwargs)
        return Webhook(**defaults)

    def test_register_and_get(self):
        wh = self._make_webhook()
        self.mgr.register(wh)
        assert self.mgr.get(wh.webhook_id) is wh

    def test_register_returns_webhook(self):
        wh = self._make_webhook()
        result = self.mgr.register(wh)
        assert result.webhook_id == wh.webhook_id

    def test_list_for_user(self):
        self.mgr.register(self._make_webhook(user_id="u1", name="a"))
        self.mgr.register(self._make_webhook(user_id="u1", name="b"))
        self.mgr.register(self._make_webhook(user_id="u2", name="c"))
        assert len(self.mgr.list_for_user("u1")) == 2
        assert len(self.mgr.list_for_user("u2")) == 1
        assert len(self.mgr.list_for_user("u3")) == 0

    def test_delete_removes_webhook(self):
        wh = self._make_webhook()
        self.mgr.register(wh)
        self.mgr.delete(wh.webhook_id)
        with pytest.raises(KeyError):
            self.mgr.get(wh.webhook_id)

    def test_delete_nonexistent_raises(self):
        with pytest.raises(KeyError, match="Webhook not found"):
            self.mgr.delete("no-such-id")

    def test_get_nonexistent_raises(self):
        with pytest.raises(KeyError, match="Webhook not found"):
            self.mgr.get("no-such-id")

    def test_max_webhooks_per_user(self):
        for i in range(3):
            self.mgr.register(self._make_webhook(name=f"hook-{i}"))
        with pytest.raises(ValueError, match="maximum"):
            self.mgr.register(self._make_webhook(name="hook-4"))

    def test_max_limit_per_user_independent(self):
        for i in range(3):
            self.mgr.register(self._make_webhook(user_id="u1", name=f"h{i}"))
        # Different user should still be able to register
        wh = self._make_webhook(user_id="u2", name="other")
        self.mgr.register(wh)
        assert self.mgr.get(wh.webhook_id) is wh

    def test_update_status(self):
        wh = self._make_webhook()
        self.mgr.register(wh)
        updated = self.mgr.update_status(wh.webhook_id, WebhookStatus.PAUSED)
        assert updated.status == WebhookStatus.PAUSED

    def test_update_status_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.mgr.update_status("no-such-id", WebhookStatus.PAUSED)

    def test_invalid_signature_scheme_raises(self):
        wh = self._make_webhook()
        wh.signature_scheme = SignatureScheme("hmac-sha256")  # valid
        self.mgr.register(wh)  # OK

    def test_register_creates_event_list(self):
        wh = self._make_webhook()
        self.mgr.register(wh)
        assert self.mgr.get_events(wh.webhook_id) == []


class TestWebhookManagerInbound:
    """WebhookManager inbound processing — signature verify, log, emit."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus)

    def _register_inbound(self, **kwargs) -> Webhook:
        defaults = dict(
            user_id="u1",
            name="gh-push",
            direction=WebhookDirection.INBOUND,
            event_type_prefix="github.push",
            secret="my-secret-key-1234",
        )
        defaults.update(kwargs)
        wh = Webhook(**defaults)
        self.mgr.register(wh)
        return wh

    def _sign(self, payload: bytes, secret: str) -> str:
        from nobla.automation.webhooks.verification import HmacSha256Verifier
        return HmacSha256Verifier().sign(payload, secret)

    @pytest.mark.asyncio
    async def test_process_valid_inbound(self):
        wh = self._register_inbound()
        body = b'{"ref": "refs/heads/main"}'
        sig = self._sign(body, wh.secret)
        event = await self.mgr.process_inbound(
            wh.webhook_id, body, {"content-type": "application/json"}, sig
        )
        assert event.signature_valid is True
        assert event.status == WebhookEventStatus.PROCESSED
        assert event.processed_at is not None

    @pytest.mark.asyncio
    async def test_process_emits_event(self):
        wh = self._register_inbound()
        body = b'{"action": "push"}'
        sig = self._sign(body, wh.secret)
        await self.mgr.process_inbound(wh.webhook_id, body, {}, sig)
        assert len(self.bus.emitted) == 1
        ev = self.bus.emitted[0]
        assert ev.event_type == "webhook.github.push.received"
        assert ev.payload["webhook_id"] == wh.webhook_id

    @pytest.mark.asyncio
    async def test_process_invalid_signature_raises(self):
        wh = self._register_inbound()
        body = b'{"ref": "main"}'
        with pytest.raises(PermissionError, match="signature"):
            await self.mgr.process_inbound(wh.webhook_id, body, {}, "bad-sig")

    @pytest.mark.asyncio
    async def test_process_logs_failed_signature_event(self):
        wh = self._register_inbound()
        body = b'{"ref": "main"}'
        with pytest.raises(PermissionError):
            await self.mgr.process_inbound(wh.webhook_id, body, {}, "bad")
        events = self.mgr.get_events(wh.webhook_id)
        assert len(events) == 1
        assert events[0].status == WebhookEventStatus.FAILED
        assert events[0].signature_valid is False

    @pytest.mark.asyncio
    async def test_process_nonexistent_webhook_raises(self):
        with pytest.raises(KeyError):
            await self.mgr.process_inbound("no-such", b"{}", {}, "")

    @pytest.mark.asyncio
    async def test_process_paused_webhook_raises(self):
        wh = self._register_inbound()
        self.mgr.update_status(wh.webhook_id, WebhookStatus.PAUSED)
        with pytest.raises(ValueError, match="not active"):
            await self.mgr.process_inbound(wh.webhook_id, b"{}", {}, "")

    @pytest.mark.asyncio
    async def test_process_outbound_webhook_raises(self):
        wh = Webhook(
            user_id="u1", name="out", direction=WebhookDirection.OUTBOUND,
            event_type_prefix="notify", secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        with pytest.raises(ValueError, match="outbound"):
            await self.mgr.process_inbound(wh.webhook_id, b"{}", {}, "")

    @pytest.mark.asyncio
    async def test_process_oversized_payload_raises(self):
        from nobla.automation.webhooks.manager import WebhookManager
        mgr = WebhookManager(event_bus=self.bus, max_payload_bytes=10)
        wh = Webhook(
            user_id="u1", name="small", direction=WebhookDirection.INBOUND,
            event_type_prefix="test", secret="secret-key-12345678",
        )
        mgr.register(wh)
        with pytest.raises(ValueError, match="Payload size"):
            await mgr.process_inbound(wh.webhook_id, b"x" * 20, {}, "")

    @pytest.mark.asyncio
    async def test_process_invalid_json_still_works(self):
        wh = self._register_inbound()
        body = b"not-json"
        sig = self._sign(body, wh.secret)
        event = await self.mgr.process_inbound(wh.webhook_id, body, {}, sig)
        assert event.status == WebhookEventStatus.PROCESSED
        assert "raw" in event.payload


class TestWebhookManagerHealth:
    """WebhookManager health computation."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus)

    @pytest.mark.asyncio
    async def test_health_no_events(self):
        wh = Webhook(
            user_id="u1", name="h", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        health = self.mgr.get_health(wh.webhook_id)
        assert health.event_count == 0
        assert health.status == WebhookHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_after_successful_events(self):
        from nobla.automation.webhooks.verification import HmacSha256Verifier
        wh = Webhook(
            user_id="u1", name="h", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        v = HmacSha256Verifier()
        for _ in range(5):
            body = b'{"ok": true}'
            sig = v.sign(body, wh.secret)
            await self.mgr.process_inbound(wh.webhook_id, body, {}, sig)
        health = self.mgr.get_health(wh.webhook_id)
        assert health.event_count == 5
        assert health.failure_rate == 0.0
        assert health.status == WebhookHealthStatus.HEALTHY

    def test_health_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.mgr.get_health("no-such")


class TestWebhookManagerTestEvent:
    """WebhookManager.send_test_event."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus)

    @pytest.mark.asyncio
    async def test_send_test_event(self):
        wh = Webhook(
            user_id="u1", name="test-h", event_type_prefix="test",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        event = await self.mgr.send_test_event(wh.webhook_id)
        assert event.signature_valid is True
        assert event.status == WebhookEventStatus.PROCESSED
        assert len(self.bus.emitted) == 1

    @pytest.mark.asyncio
    async def test_send_test_nonexistent_raises(self):
        with pytest.raises(KeyError):
            await self.mgr.send_test_event("no-such")


class TestWebhookManagerDeadLetter:
    """WebhookManager dead letter operations."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus)

    def test_add_dead_letter(self):
        wh = Webhook(
            user_id="u1", name="dl", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        dl = self.mgr.add_dead_letter(
            wh.webhook_id, "ev-1", {"data": "lost"}, "timeout", 3
        )
        assert dl.webhook_id == wh.webhook_id
        assert dl.retry_count == 3
        assert dl.error == "timeout"

    def test_get_dead_letters(self):
        wh = Webhook(
            user_id="u1", name="dl", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        self.mgr.add_dead_letter(wh.webhook_id, "ev-1", {}, "err1", 3)
        self.mgr.add_dead_letter(wh.webhook_id, "ev-2", {}, "err2", 3)
        dls = self.mgr.get_dead_letters(wh.webhook_id)
        assert len(dls) == 2

    @pytest.mark.asyncio
    async def test_notify_dead_letter(self):
        wh = Webhook(
            user_id="u1", name="dl", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        dl = self.mgr.add_dead_letter(wh.webhook_id, "ev-1", {}, "err", 3)
        assert dl.user_notified is False
        await self.mgr.notify_dead_letter(dl)
        assert dl.user_notified is True
        assert len(self.bus.emitted) == 1
        assert self.bus.emitted[0].event_type == "webhook.dead_letter"
        assert self.bus.emitted[0].priority == 5

    def test_dead_letters_appear_in_health(self):
        wh = Webhook(
            user_id="u1", name="dl", event_type_prefix="t",
            secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        self.mgr.add_dead_letter(wh.webhook_id, "ev-1", {}, "err", 3)
        health = self.mgr.get_health(wh.webhook_id)
        assert health.dead_letter_count == 1


# ---------------------------------------------------------------------------
# Gateway handler tests (FastAPI TestClient)
# ---------------------------------------------------------------------------


class TestWebhookHandlers:
    """REST API routes via FastAPI TestClient."""

    def setup_method(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from nobla.automation.webhooks.manager import WebhookManager
        from nobla.gateway.webhook_handlers import (
            create_webhook_router,
            set_webhook_manager,
        )

        self.bus = _FakeEventBus()
        self.mgr = WebhookManager(event_bus=self.bus)
        set_webhook_manager(self.mgr)

        app = FastAPI()
        app.include_router(create_webhook_router())
        self.client = TestClient(app)

    def test_register_webhook(self):
        resp = self.client.post("/api/webhooks", json={
            "name": "GitHub Push",
            "event_type_prefix": "github.push",
            "secret": "secret-key-12345678",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "GitHub Push"
        assert data["direction"] == "inbound"
        assert data["status"] == "active"

    def test_register_short_secret_rejected(self):
        resp = self.client.post("/api/webhooks", json={
            "name": "bad",
            "event_type_prefix": "test",
            "secret": "short",
        })
        assert resp.status_code == 422  # Pydantic validation

    def test_list_webhooks(self):
        self.client.post("/api/webhooks", json={
            "name": "h1", "event_type_prefix": "t1", "secret": "secret-key-12345678",
        })
        self.client.post("/api/webhooks", json={
            "name": "h2", "event_type_prefix": "t2", "secret": "secret-key-12345678",
        })
        resp = self.client.get("/api/webhooks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_delete_webhook(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "del", "event_type_prefix": "t", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.delete(f"/api/webhooks/{wh_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_nonexistent_returns_404(self):
        resp = self.client.delete("/api/webhooks/no-such")
        assert resp.status_code == 404

    def test_update_status(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "s", "event_type_prefix": "t", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.put(
            f"/api/webhooks/{wh_id}/status",
            json={"status": "paused"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_get_health(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "h", "event_type_prefix": "t", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.get(f"/api/webhooks/{wh_id}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_count"] == 0
        assert data["status"] == "healthy"

    def test_get_events_empty(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "e", "event_type_prefix": "t", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.get(f"/api/webhooks/{wh_id}/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_inbound_valid_signature(self):
        from nobla.automation.webhooks.verification import HmacSha256Verifier
        secret = "secret-key-12345678"
        reg = self.client.post("/api/webhooks", json={
            "name": "in", "event_type_prefix": "github.push", "secret": secret,
        })
        wh_id = reg.json()["webhook_id"]
        body = b'{"ref": "refs/heads/main"}'
        sig = HmacSha256Verifier().sign(body, secret)
        resp = self.client.post(
            f"/webhooks/inbound/{wh_id}",
            content=body,
            headers={"x-hub-signature-256": f"sha256={sig}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_inbound_invalid_signature(self):
        secret = "secret-key-12345678"
        reg = self.client.post("/api/webhooks", json={
            "name": "in", "event_type_prefix": "test", "secret": secret,
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.post(
            f"/webhooks/inbound/{wh_id}",
            content=b'{"data": 1}',
            headers={"x-hub-signature-256": "sha256=invalid"},
        )
        assert resp.status_code == 401

    def test_inbound_nonexistent_returns_404(self):
        resp = self.client.post(
            "/webhooks/inbound/no-such",
            content=b"{}",
        )
        assert resp.status_code == 404

    def test_test_webhook(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "test-h", "event_type_prefix": "test", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        resp = self.client.post(f"/api/webhooks/{wh_id}/test")
        assert resp.status_code == 200
        assert resp.json()["signature_valid"] is True

    def test_dead_letters_endpoint(self):
        reg = self.client.post("/api/webhooks", json={
            "name": "dl", "event_type_prefix": "t", "secret": "secret-key-12345678",
        })
        wh_id = reg.json()["webhook_id"]
        self.mgr.add_dead_letter(wh_id, "ev-1", {}, "err", 3)
        resp = self.client.get(f"/api/webhooks/{wh_id}/dead-letters")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["error"] == "err"


# ---------------------------------------------------------------------------
# Outbound webhook handler tests
# ---------------------------------------------------------------------------


class _FakeEventBusWithSubscribe:
    """Event bus stub that supports subscribe/unsubscribe + emit tracking."""

    def __init__(self):
        self.emitted: list = []
        self._handlers: dict[str, Any] = {}
        self._next_id = 0

    async def emit(self, event):
        self.emitted.append(event)

    async def subscribe(self, pattern, handler):
        self._next_id += 1
        sub_id = str(self._next_id)
        self._handlers[sub_id] = (pattern, handler)
        return sub_id

    async def unsubscribe(self, sub_id):
        self._handlers.pop(sub_id, None)

    async def fire(self, event):
        """Simulate event dispatch to all matching handlers."""
        for _, (pattern, handler) in self._handlers.items():
            import fnmatch
            if fnmatch.fnmatch(event.event_type, pattern):
                await handler(event)


def _make_outbound_webhook(**kwargs) -> Webhook:
    defaults = dict(
        user_id="u1",
        name="notify-slack",
        direction=WebhookDirection.OUTBOUND,
        url="https://hooks.slack.com/test",
        event_type_prefix="workflow.completed",
        secret="outbound-secret-key-1234",
    )
    defaults.update(kwargs)
    return Webhook(**defaults)


def _make_event(event_type: str = "webhook.workflow.completed.done", **kwargs):
    from nobla.events.models import NoblaEvent
    defaults = dict(
        event_type=event_type,
        source="test",
        payload={"result": "ok"},
    )
    defaults.update(kwargs)
    return NoblaEvent(**defaults)


class TestOutboundWebhookHandler:
    """OutboundWebhookHandler — delivery, retry, dead letter."""

    def setup_method(self):
        from nobla.automation.webhooks.manager import WebhookManager
        from nobla.automation.webhooks.outbound import OutboundWebhookHandler

        self.bus = _FakeEventBusWithSubscribe()
        self.mgr = WebhookManager(event_bus=self.bus)
        self.post_calls: list[dict] = []
        self.post_responses: list[dict] = []

        async def mock_post(url, payload, headers, timeout=10.0):
            self.post_calls.append({
                "url": url, "payload": payload, "headers": headers,
            })
            if self.post_responses:
                return self.post_responses.pop(0)
            return {"success": True, "status_code": 200, "error": ""}

        self.handler = OutboundWebhookHandler(
            webhook_manager=self.mgr,
            event_bus=self.bus,
            max_retries=2,
            retry_backoff_base=0.01,  # Tiny for fast tests
            retry_backoff_multiplier=2.0,
            http_post=mock_post,
        )

    @pytest.mark.asyncio
    async def test_start_subscribes(self):
        await self.handler.start()
        assert len(self.bus._handlers) == 1

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self):
        await self.handler.start()
        await self.handler.stop()
        assert len(self.bus._handlers) == 0

    @pytest.mark.asyncio
    async def test_successful_delivery(self):
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        event = _make_event()
        await self.bus.fire(event)
        await asyncio.sleep(0.05)  # Let task complete

        assert len(self.post_calls) == 1
        assert self.post_calls[0]["url"] == wh.url
        # Check event logged
        events = self.mgr.get_events(wh.webhook_id)
        assert len(events) == 1
        assert events[0].status == WebhookEventStatus.PROCESSED

    @pytest.mark.asyncio
    async def test_delivery_includes_signature_header(self):
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.05)

        headers = self.post_calls[0]["headers"]
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Event"] == "webhook.workflow.completed.done"
        assert headers["X-Webhook-Id"] == wh.webhook_id

    @pytest.mark.asyncio
    async def test_delivery_payload_structure(self):
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event(payload={"key": "val"}))
        await asyncio.sleep(0.05)

        import json as _json
        sent = _json.loads(self.post_calls[0]["payload"])
        assert sent["event_type"] == "webhook.workflow.completed.done"
        assert sent["data"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self):
        self.post_responses = [
            {"success": False, "status_code": 500, "error": "Internal Server Error"},
            {"success": True, "status_code": 200, "error": ""},
        ]
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.1)

        assert len(self.post_calls) == 2
        events = self.mgr.get_events(wh.webhook_id)
        assert len(events) == 1
        assert events[0].status == WebhookEventStatus.PROCESSED
        assert events[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_dead_letter_after_max_retries(self):
        self.post_responses = [
            {"success": False, "status_code": 500, "error": "fail-1"},
            {"success": False, "status_code": 502, "error": "fail-2"},
            {"success": False, "status_code": 503, "error": "fail-3"},
        ]
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.2)

        # Should have attempted 3 times (initial + 2 retries)
        assert len(self.post_calls) == 3
        # Event logged as failed
        events = self.mgr.get_events(wh.webhook_id)
        assert len(events) == 1
        assert events[0].status == WebhookEventStatus.FAILED
        # Dead letter created
        dls = self.mgr.get_dead_letters(wh.webhook_id)
        assert len(dls) == 1
        assert dls[0].user_notified is True

    @pytest.mark.asyncio
    async def test_dead_letter_emits_notification(self):
        self.post_responses = [
            {"success": False, "status_code": 500, "error": "err"},
            {"success": False, "status_code": 500, "error": "err"},
            {"success": False, "status_code": 500, "error": "err"},
        ]
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.2)

        # Find dead_letter and outbound.failed events
        dl_events = [e for e in self.bus.emitted if e.event_type == "webhook.dead_letter"]
        fail_events = [
            e for e in self.bus.emitted
            if "outbound.failed" in e.event_type
        ]
        assert len(dl_events) == 1
        assert len(fail_events) == 1
        assert fail_events[0].priority == 5

    @pytest.mark.asyncio
    async def test_emits_success_event(self):
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.05)

        sent_events = [
            e for e in self.bus.emitted if "outbound.sent" in e.event_type
        ]
        assert len(sent_events) == 1

    @pytest.mark.asyncio
    async def test_ignores_non_matching_events(self):
        wh = _make_outbound_webhook(event_type_prefix="github.push")
        self.mgr.register(wh)
        await self.handler.start()

        # This event doesn't match "github.push" prefix
        await self.bus.fire(_make_event(event_type="webhook.stripe.payment.received"))
        await asyncio.sleep(0.05)

        assert len(self.post_calls) == 0

    @pytest.mark.asyncio
    async def test_ignores_paused_webhooks(self):
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        self.mgr.update_status(wh.webhook_id, WebhookStatus.PAUSED)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.05)

        assert len(self.post_calls) == 0

    @pytest.mark.asyncio
    async def test_ignores_inbound_webhooks(self):
        wh = Webhook(
            user_id="u1", name="in", direction=WebhookDirection.INBOUND,
            event_type_prefix="workflow.completed", secret="secret-key-12345678",
        )
        self.mgr.register(wh)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.05)

        assert len(self.post_calls) == 0

    @pytest.mark.asyncio
    async def test_exception_in_post_handled_gracefully(self):
        async def exploding_post(url, payload, headers, timeout=10.0):
            raise ConnectionError("Network down")

        from nobla.automation.webhooks.outbound import OutboundWebhookHandler
        handler = OutboundWebhookHandler(
            webhook_manager=self.mgr,
            event_bus=self.bus,
            max_retries=0,
            retry_backoff_base=0.01,
            http_post=exploding_post,
        )
        wh = _make_outbound_webhook()
        self.mgr.register(wh)
        await handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.1)

        # Should have dead-lettered after the exception
        dls = self.mgr.get_dead_letters(wh.webhook_id)
        assert len(dls) == 1
        assert "Network down" in dls[0].error

    def test_compute_backoff(self):
        from nobla.automation.webhooks.outbound import OutboundWebhookHandler
        handler = OutboundWebhookHandler(
            webhook_manager=self.mgr,
            event_bus=self.bus,
            retry_backoff_base=2.0,
            retry_backoff_multiplier=4.0,
        )
        assert handler.compute_backoff(0) == 2.0
        assert handler.compute_backoff(1) == 8.0
        assert handler.compute_backoff(2) == 32.0

    @pytest.mark.asyncio
    async def test_multiple_outbound_webhooks_both_receive(self):
        wh1 = _make_outbound_webhook(name="slack")
        wh2 = _make_outbound_webhook(
            name="discord", url="https://discord.com/hook",
        )
        self.mgr.register(wh1)
        self.mgr.register(wh2)
        await self.handler.start()

        await self.bus.fire(_make_event())
        await asyncio.sleep(0.1)

        assert len(self.post_calls) == 2
        urls = {c["url"] for c in self.post_calls}
        assert wh1.url in urls
        assert wh2.url in urls
