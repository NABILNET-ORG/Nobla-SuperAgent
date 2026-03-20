from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from cryptography.fernet import Fernet
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OAuthConfig:
    provider: str
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    scopes: list[str]
    redirect_uri: str


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: int
    provider: str

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class OAuthManager:
    def __init__(self, configs: dict[str, OAuthConfig], encryption_key: str) -> None:
        self._configs = configs
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
        self._pending_states: dict[str, str] = {}
        self._tokens: dict[tuple[str, str], OAuthTokens] = {}

    def supported_providers(self) -> list[str]:
        return list(self._configs.keys())

    def get_auth_url(self, provider: str, user_id: str) -> tuple[str, str]:
        config = self._configs.get(provider)
        if not config:
            raise ValueError(f"No OAuth config for provider: {provider}")
        state = secrets.token_urlsafe(32)
        self._pending_states[state] = user_id
        params = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(config.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{config.auth_url}?{urlencode(params)}", state

    def validate_state(self, state: str) -> str | None:
        return self._pending_states.pop(state, None)

    def store_tokens(self, provider: str, user_id: str, tokens: OAuthTokens) -> None:
        self._tokens[(provider, user_id)] = tokens
        logger.info("oauth.tokens_stored", provider=provider, user_id=user_id)

    def get_tokens(self, provider: str, user_id: str) -> OAuthTokens | None:
        return self._tokens.get((provider, user_id))

    def revoke(self, provider: str, user_id: str) -> None:
        self._tokens.pop((provider, user_id), None)
        logger.info("oauth.revoked", provider=provider, user_id=user_id)
