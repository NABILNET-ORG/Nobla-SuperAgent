import pytest
from nobla.security.sandbox import SandboxConfig, SandboxResult, SandboxManager


def test_sandbox_config_defaults():
    cfg = SandboxConfig()
    assert cfg.runtime == "docker"
    assert cfg.memory_limit == "256m"
    assert cfg.timeout_seconds == 30
    assert cfg.network_enabled is False


def test_sandbox_result_success():
    result = SandboxResult(stdout="hello\n", stderr="", exit_code=0, execution_time_ms=150, timed_out=False)
    assert result.exit_code == 0
    assert result.timed_out is False


def test_sandbox_result_timeout():
    result = SandboxResult(stdout="", stderr="", exit_code=-1, execution_time_ms=30000, timed_out=True)
    assert result.timed_out is True


def test_sandbox_manager_creation():
    cfg = SandboxConfig()
    mgr = SandboxManager(cfg)
    assert mgr.config.runtime == "docker"


def test_sandbox_validate_language():
    cfg = SandboxConfig()
    mgr = SandboxManager(cfg)
    assert mgr.get_image("python") == "python:3.12-slim"
    assert mgr.get_image("unknown") is None
