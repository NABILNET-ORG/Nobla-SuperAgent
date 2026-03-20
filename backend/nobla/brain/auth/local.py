from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LocalEndpoint:
    base_url: str
    models: list[str] = field(default_factory=list)
    is_healthy: bool = False


class LocalModelManager:
    def __init__(self, default_url: str = "http://localhost:11434") -> None:
        self.default_url = default_url
        self._endpoints: dict[str, LocalEndpoint] = {}

    def register(
        self, user_id: str, base_url: str, models: list[str] | None = None
    ) -> LocalEndpoint:
        endpoint = LocalEndpoint(base_url=base_url, models=models or [])
        self._endpoints[user_id] = endpoint
        logger.info("local.registered", user_id=user_id, base_url=base_url)
        return endpoint

    def get(self, user_id: str) -> LocalEndpoint | None:
        return self._endpoints.get(user_id)

    def remove(self, user_id: str) -> None:
        self._endpoints.pop(user_id, None)
        logger.info("local.removed", user_id=user_id)

    def update_models(self, user_id: str, models: list[str]) -> None:
        endpoint = self._endpoints.get(user_id)
        if endpoint:
            endpoint.models = models
