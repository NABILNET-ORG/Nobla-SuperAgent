"""Pluggable webhook signature verification (Phase 6).

Architecture:
    SignatureVerifier ABC defines the contract.
    Concrete verifiers (HmacSha256Verifier, HmacSha1Verifier) implement it.
    VerifierRegistry maps scheme names to verifier instances.
    WebhookManager uses the registry to verify inbound / sign outbound.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SignatureVerifier(ABC):
    """Abstract base for webhook signature verification.

    Implementations must handle both verification (inbound) and
    signing (outbound) via the same secret + algorithm.
    """

    @abstractmethod
    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify that *signature* matches *payload* signed with *secret*.

        Args:
            payload: Raw request body bytes.
            signature: The signature string from the webhook header.
            secret: Shared secret for this webhook.

        Returns:
            True if the signature is valid.
        """

    @abstractmethod
    def sign(self, payload: bytes, secret: str) -> str:
        """Produce a signature for *payload* using *secret*.

        Args:
            payload: Raw request body bytes.
            secret: Shared secret for this webhook.

        Returns:
            Hex-encoded signature string.
        """


class HmacSha256Verifier(SignatureVerifier):
    """HMAC-SHA256 signature verification — the industry standard.

    Used by GitHub, Stripe, Slack, and most modern webhook providers.
    Expects the signature as a hex digest, optionally prefixed with
    ``sha256=`` (stripped automatically).
    """

    _PREFIX = "sha256="

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        sig = signature.removeprefix(self._PREFIX)
        expected = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig)

    def sign(self, payload: bytes, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()


class HmacSha1Verifier(SignatureVerifier):
    """HMAC-SHA1 signature verification — legacy compatibility.

    Some older webhook providers still use SHA-1.  Not recommended for
    new integrations but necessary for backward compatibility.
    """

    _PREFIX = "sha1="

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        sig = signature.removeprefix(self._PREFIX)
        expected = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha1
        ).hexdigest()
        return hmac.compare_digest(expected, sig)

    def sign(self, payload: bytes, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha1
        ).hexdigest()


class NoneVerifier(SignatureVerifier):
    """No-op verifier for webhooks that don't use signatures.

    Always returns True for verification.  Signing returns an empty string.
    """

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        return True

    def sign(self, payload: bytes, secret: str) -> str:
        return ""


class VerifierRegistry:
    """Maps signature scheme names to verifier instances.

    Ships with built-in verifiers for hmac-sha256, hmac-sha1, and none.
    Users can register custom verifiers for unusual providers.

    Usage::

        registry = VerifierRegistry()
        verifier = registry.get("hmac-sha256")
        is_valid = verifier.verify(body, sig_header, secret)
    """

    def __init__(self) -> None:
        self._verifiers: dict[str, SignatureVerifier] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the default verifier set."""
        self.register("hmac-sha256", HmacSha256Verifier())
        self.register("hmac-sha1", HmacSha1Verifier())
        self.register("none", NoneVerifier())

    def register(self, scheme: str, verifier: SignatureVerifier) -> None:
        """Register a verifier under *scheme*.

        Args:
            scheme: Scheme name (e.g. "hmac-sha256", "ed25519").
            verifier: Verifier instance.

        Raises:
            TypeError: If *verifier* is not a SignatureVerifier.
        """
        if not isinstance(verifier, SignatureVerifier):
            raise TypeError(
                f"Expected SignatureVerifier, got {type(verifier).__name__}"
            )
        self._verifiers[scheme] = verifier
        logger.debug("Registered signature verifier: %s", scheme)

    def get(self, scheme: str) -> SignatureVerifier:
        """Retrieve the verifier for *scheme*.

        Args:
            scheme: Scheme name.

        Returns:
            The registered verifier.

        Raises:
            KeyError: If no verifier is registered for *scheme*.
        """
        try:
            return self._verifiers[scheme]
        except KeyError:
            available = ", ".join(sorted(self._verifiers))
            raise KeyError(
                f"No verifier registered for scheme '{scheme}'. "
                f"Available: {available}"
            ) from None

    def list_schemes(self) -> list[str]:
        """Return all registered scheme names."""
        return sorted(self._verifiers)

    def has_scheme(self, scheme: str) -> bool:
        """Check whether a scheme is registered."""
        return scheme in self._verifiers
