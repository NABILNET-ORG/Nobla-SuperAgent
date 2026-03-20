from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet
import structlog

logger = structlog.get_logger(__name__)

_KEY_PATTERNS: dict[str, re.Pattern] = {
    "openai": re.compile(r"^sk-(proj-)?[A-Za-z0-9_-]{20,}$"),
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$"),
    "groq": re.compile(r"^gsk_[A-Za-z0-9_-]{20,}$"),
    "deepseek": re.compile(r"^sk-[A-Za-z0-9_-]{20,}$"),
}


@dataclass
class ApiKeyRecord:
    provider: str
    user_id: str
    api_key: str


class ApiKeyManager:
    def __init__(self, encryption_key: str) -> None:
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
        self._store: dict[tuple[str, str], bytes] = {}

    def store(self, provider: str, user_id: str, api_key: str) -> None:
        self._store[(provider, user_id)] = self._fernet.encrypt(api_key.encode())
        logger.info("api_key.stored", provider=provider, user_id=user_id)

    def get(self, provider: str, user_id: str) -> ApiKeyRecord | None:
        encrypted = self._store.get((provider, user_id))
        if encrypted is None:
            return None
        decrypted = self._fernet.decrypt(encrypted).decode()
        return ApiKeyRecord(provider=provider, user_id=user_id, api_key=decrypted)

    def delete(self, provider: str, user_id: str) -> None:
        self._store.pop((provider, user_id), None)
        logger.info("api_key.deleted", provider=provider, user_id=user_id)

    def _get_raw(self, provider: str, user_id: str) -> str | None:
        encrypted = self._store.get((provider, user_id))
        return encrypted.decode() if encrypted else None

    def validate_format(self, provider: str, key: str) -> bool:
        pattern = _KEY_PATTERNS.get(provider)
        if pattern is None:
            return True
        return bool(pattern.match(key))

    def list_providers(self, user_id: str) -> list[str]:
        return [provider for (provider, uid) in self._store if uid == user_id]
