from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Any
import structlog

logger = structlog.get_logger()

SENSITIVE_KEYS = {"passphrase", "password", "token", "secret", "api_key"}


@dataclass
class AuditEntry:
    user_id: str | None
    action: str
    method: str
    tier: int
    status: str
    latency_ms: int | None = None
    ip_address: str | None = None
    metadata: dict = field(default_factory=dict)


def sanitize_params(params: dict, max_content_length: int = 500) -> dict:
    """Remove sensitive fields and truncate long values."""
    if not isinstance(params, dict):
        return params
    result = {}
    for key, value in params.items():
        if key.lower() in SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_params(value, max_content_length)
        elif isinstance(value, str) and len(value) > max_content_length:
            result[key] = value[:max_content_length] + "..."
        else:
            result[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
    return result
