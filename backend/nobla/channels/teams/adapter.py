"""Microsoft Teams channel adapter with Bot Framework REST API (Phase 5-Channels).

Implements ``BaseChannelAdapter`` for Microsoft Teams.
  - Inbound: Webhook with JWT validation (OpenID Connect)
  - Outbound: REST API with OAuth2 client_credentials token
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from nobla.channels.base import BaseChannelAdapter, ChannelResponse
from nobla.channels.teams.formatter import format_response
from nobla.channels.teams.handlers import TeamsHandlers
from nobla.channels.teams.media import send_attachment
from nobla.channels.teams.models import (
    BOT_FRAMEWORK_OPENID_URL,
    BOT_FRAMEWORK_TOKEN_SCOPE,
    BOT_FRAMEWORK_TOKEN_URL,
)

logger = logging.getLogger(__name__)


class TokenManager:
    """OAuth2 client_credentials token manager for Bot Framework API."""

    def __init__(self, app_id: str, app_password: str,
                 client: httpx.AsyncClient | Any, refresh_margin: int = 300) -> None:
        self._app_id = app_id
        self._app_password = app_password
        self._client = client
        self._refresh_margin = refresh_margin
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def has_valid_token(self) -> bool:
        return self._token is not None and time.time() < self._expires_at - self._refresh_margin

    async def get_token(self) -> str:
        if self.has_valid_token:
            return self._token
        async with self._lock:
            if self.has_valid_token:
                return self._token
            return await self._refresh()

    async def _refresh(self) -> str:
        resp = await self._client.post(BOT_FRAMEWORK_TOKEN_URL, data={
            "grant_type": "client_credentials", "client_id": self._app_id,
            "client_secret": self._app_password, "scope": BOT_FRAMEWORK_TOKEN_SCOPE,
        })
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._token


class JWTValidator:
    """Validates inbound JWT tokens from Bot Framework. Security-first: rejects ALL when JWKS unavailable."""

    def __init__(self, app_id: str, tenant_id: str = "") -> None:
        self._app_id = app_id
        self._tenant_id = tenant_id
        self._jwks: dict[str, Any] = {}
        self._jwks_available = False
        self._jwks_fetched_at: float = 0.0

    async def fetch_jwks(self, client: httpx.AsyncClient) -> None:
        try:
            resp = await client.get(BOT_FRAMEWORK_OPENID_URL)
            resp.raise_for_status()
            config = resp.json()
            jwks_uri = config.get("jwks_uri", "")
            if not jwks_uri:
                logger.error("No jwks_uri in OpenID config")
                self._jwks_available = False
                return
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            self._jwks = resp.json()
            self._jwks_available = True
            self._jwks_fetched_at = time.time()
            logger.info("JWKS fetched: %d keys", len(self._jwks.get("keys", [])))
        except Exception:
            logger.exception("Failed to fetch JWKS")
            self._jwks_available = False

    def validate_token(self, auth_header: str) -> dict[str, Any] | None:
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        if not self._jwks_available:
            logger.warning("JWKS unavailable — rejecting request (503)")
            return None
        token = auth_header[7:]
        try:
            claims = self._decode_and_verify(token)
        except Exception:
            logger.warning("JWT decode/verify failed")
            return None
        if not claims:
            return None
        now = time.time()
        if claims.get("exp", 0) < now:
            logger.warning("JWT expired")
            return None
        if claims.get("aud") != self._app_id:
            logger.warning("JWT audience mismatch: %s != %s", claims.get("aud"), self._app_id)
            return None
        iss = claims.get("iss", "")
        if not iss.startswith("https://api.botframework.com"):
            logger.warning("JWT issuer invalid: %s", iss)
            return None
        if self._tenant_id and claims.get("tid") != self._tenant_id:
            logger.warning("JWT tenant mismatch: %s != %s", claims.get("tid"), self._tenant_id)
            return None
        return claims

    def _decode_and_verify(self, token: str) -> dict[str, Any] | None:
        try:
            import jwt
            from jwt import PyJWKClient
            jwk_client = PyJWKClient("")
            jwk_client.fetch_data = lambda: self._jwks
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                                options={"verify_aud": False, "verify_iss": False})
            return claims
        except Exception:
            logger.debug("JWT decode failed", exc_info=True)
            return None


class TeamsAdapter(BaseChannelAdapter):
    """Microsoft Teams adapter using Bot Framework REST API."""

    def __init__(self, settings: Any, handlers: TeamsHandlers) -> None:
        self._settings = settings
        self._handlers = handlers
        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._token_manager: TokenManager | None = None
        self._jwt_validator: JWTValidator | None = None
        self._jwks_task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return "teams"

    async def start(self) -> None:
        if self._running:
            logger.warning("Teams adapter already running")
            return
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token_manager = TokenManager(
            app_id=self._settings.app_id, app_password=self._settings.app_password,
            client=self._client, refresh_margin=self._settings.token_refresh_margin_seconds)
        self._jwt_validator = JWTValidator(
            app_id=self._settings.app_id, tenant_id=self._settings.tenant_id)
        self._handlers.set_send_fn(self._send_raw_text)
        self._running = True
        self._fetch_jwks_background()
        logger.info("Teams adapter started (app_id=%s, tenant=%s)",
                     self._settings.app_id, self._settings.tenant_id or "multi-tenant")

    def _fetch_jwks_background(self) -> None:
        self._jwks_task = asyncio.create_task(self._jwks_fetch_loop())

    async def _jwks_fetch_loop(self) -> None:
        backoff = 1.0
        max_backoff = 60.0
        while self._running:
            try:
                if self._client and self._jwt_validator:
                    await self._jwt_validator.fetch_jwks(self._client)
                    if self._jwt_validator._jwks_available:
                        await asyncio.sleep(86400)
                        backoff = 1.0
                        continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("JWKS fetch loop error")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def stop(self) -> None:
        if not self._running:
            return
        if self._jwks_task and not self._jwks_task.done():
            self._jwks_task.cancel()
            try:
                await self._jwks_task
            except asyncio.CancelledError:
                pass
            self._jwks_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self._token_manager = None
        self._jwt_validator = None
        self._running = False
        logger.info("Teams adapter stopped")

    async def handle_webhook(self, body: bytes, auth_header: str) -> dict[str, Any] | None:
        if not self._jwt_validator:
            return None
        claims = self._jwt_validator.validate_token(auth_header)
        if not claims:
            return None
        try:
            activity = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid JSON in Teams webhook body")
            return None
        await self._handlers.handle_activity(activity)
        return activity

    async def send(self, channel_user_id: str, response: ChannelResponse) -> None:
        if not self._client or not self._token_manager:
            logger.error("Cannot send - client not initialized")
            return
        ref = self._handlers.get_conversation_ref(channel_user_id)
        if not ref:
            logger.warning("No conversation ref for %s", channel_user_id)
            return
        token = await self._token_manager.get_token()
        service_url = ref["service_url"]
        conversation_id = ref["conversation_id"]
        for attachment in response.attachments:
            await send_attachment(service_url=service_url, conversation_id=conversation_id,
                                  attachment=attachment, bot_token=token, client=self._client)
        if response.content:
            activity = format_response(response)
            await self._post_to_conversation(service_url, conversation_id, activity, token)

    async def send_notification(self, channel_user_id: str, text: str) -> None:
        await self._send_raw_text(channel_user_id, text)

    def parse_callback(self, raw_callback: Any) -> tuple[str, dict]:
        if isinstance(raw_callback, dict):
            return raw_callback.get("action_id", ""), raw_callback
        return str(raw_callback), {}

    async def health_check(self) -> bool:
        if not self._running or not self._client:
            return False
        token_ok = self._token_manager is not None and self._token_manager.has_valid_token
        jwks_ok = self._jwt_validator is not None and self._jwt_validator._jwks_available
        return token_ok and jwks_ok

    async def _send_raw_text(self, channel_user_id: str, text: str) -> None:
        if not self._client or not self._token_manager:
            logger.error("Cannot send - client not initialized")
            return
        ref = self._handlers.get_conversation_ref(channel_user_id)
        if not ref:
            logger.warning("No conversation ref for %s — cannot send", channel_user_id)
            return
        token = await self._token_manager.get_token()
        activity = {"type": "message", "text": text}
        await self._post_to_conversation(ref["service_url"], ref["conversation_id"], activity, token)

    async def _post_to_conversation(self, service_url: str, conversation_id: str,
                                     activity: dict[str, Any], token: str) -> None:
        if not self._client:
            return
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        try:
            resp = await self._client.post(url, json=activity, headers={
                "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                logger.warning("Teams rate limited, retry after %ds", retry_after)
                await asyncio.sleep(retry_after)
                resp = await self._client.post(url, json=activity, headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to post activity to %s", conversation_id)
