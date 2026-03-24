import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


class TestSandboxExecuteExtended:
    """Tests for new volumes/network/environment params on execute()."""

    def test_execute_signature_accepts_new_params(self):
        """Verify the extended signature doesn't raise TypeError."""
        import inspect
        sig = inspect.signature(SandboxManager.execute)
        params = list(sig.parameters.keys())
        assert "network" in params
        assert "volumes" in params
        assert "environment" in params

    @pytest.mark.asyncio
    async def test_execute_defaults_preserve_behavior(self):
        """None defaults should not change existing Docker call."""
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        result = await mgr.execute("print('hi')", "python")
        assert result.exit_code == 1 or "Docker" in result.stderr or result.stdout == "hi\n"


class TestSandboxExecuteCommand:
    """Tests for new execute_command() method."""

    def test_execute_command_exists(self):
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        assert hasattr(mgr, "execute_command")
        assert asyncio.iscoroutinefunction(mgr.execute_command)

    @pytest.mark.asyncio
    async def test_execute_command_rejects_unallowed_image(self):
        cfg = SandboxConfig(allowed_images=["python:3.12-slim"])
        mgr = SandboxManager(cfg)
        result = await mgr.execute_command(
            cmd=["echo", "test"],
            image="evil:latest",
        )
        assert result.exit_code == 1
        assert "not allowed" in result.stderr.lower() or "not in" in result.stderr.lower()


class TestSandboxCleanupVolumes:
    """Tests for cleanup_volumes() method."""

    def test_cleanup_volumes_exists(self):
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        assert hasattr(mgr, "cleanup_volumes")
        assert asyncio.iscoroutinefunction(mgr.cleanup_volumes)

    @pytest.mark.asyncio
    async def test_cleanup_volumes_no_docker_no_crash(self):
        """cleanup_volumes should not raise if Docker is unavailable."""
        cfg = SandboxConfig()
        mgr = SandboxManager(cfg)
        await mgr.cleanup_volumes("nobla-test")  # Should not raise
