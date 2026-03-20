# backend/tests/test_circuit_breaker.py
import pytest
from nobla.brain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


def test_initial_state_is_closed():
    cb = CircuitBreaker(provider_name="test")
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True


def test_stays_closed_under_threshold():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.is_available() is False


def test_success_resets_failure_count():
    cb = CircuitBreaker(provider_name="test", config=CircuitBreakerConfig(failure_threshold=3))
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    import time
    time.sleep(0.02)
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_success_closes():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    import time
    time.sleep(0.02)
    cb.is_available()  # triggers HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
    )
    cb.record_failure()
    import time
    time.sleep(0.02)
    cb.is_available()  # triggers HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_rolling_window_expires_old_failures():
    cb = CircuitBreaker(
        provider_name="test",
        config=CircuitBreakerConfig(failure_threshold=3, rolling_window=0.01),
    )
    cb.record_failure()
    cb.record_failure()
    import time
    time.sleep(0.02)
    # Old failures expired, one new failure should not open
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
