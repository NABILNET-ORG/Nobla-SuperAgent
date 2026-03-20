"""
Per-provider circuit breaker: Closed -> Open -> Half-Open.

Prevents cascading failures by temporarily disabling providers
that are returning errors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    rolling_window: float = 60.0


class CircuitBreaker:
    """Circuit breaker for a single LLM provider."""

    def __init__(
        self,
        provider_name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._opened_at: float = 0.0
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        self._prune_old_failures()
        return len(self._failure_timestamps)

    def _prune_old_failures(self) -> None:
        cutoff = time.monotonic() - self.config.rolling_window
        self._failure_timestamps = [
            t for t in self._failure_timestamps if t > cutoff
        ]

    def is_available(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(
                    "circuit_breaker.half_open",
                    provider=self.provider_name,
                )
                return True
            return False

        # HALF_OPEN: allow limited test calls
        return self._half_open_calls < self.config.half_open_max_calls

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                "circuit_breaker.recovered",
                provider=self.provider_name,
            )
        self._state = CircuitState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_calls = 0

    def record_failure(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker.reopened",
                provider=self.provider_name,
            )
            return

        self._failure_timestamps.append(time.monotonic())
        self._prune_old_failures()

        if len(self._failure_timestamps) >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker.opened",
                provider=self.provider_name,
                failures=len(self._failure_timestamps),
            )

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_calls = 0
